import pytest
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from httpx import AsyncClient, ASGITransport
from fastapi import status
from fastapi.testclient import TestClient


# Test fixtures
@pytest.fixture
def api_key():
    """Test API key"""
    return "test-api-key-12345"


@pytest.fixture
def mock_env_vars(monkeypatch, api_key):
    """Set up environment variables for testing"""
    monkeypatch.setenv("MCP_API_KEY", api_key)
    monkeypatch.setenv("MCP_REMOTE_PORT", "8888")
    monkeypatch.setenv("MCP_PORT", "8181")
    monkeypatch.setenv("USE_DOCKER", "True")


@pytest.fixture
def valid_initialize_request():
    """Valid MCP initialize request"""
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "test-client",
                "version": "1.0.0"
            }
        }
    }


@pytest.fixture
def valid_tools_list_request():
    """Valid MCP tools/list request"""
    return {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }


@pytest.fixture
def valid_tool_call_request():
    """Valid MCP tool call request"""
    return {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "execute_linux_shell_command",
            "arguments": {
                "cmd": "echo 'Hello World'"
            }
        }
    }


@pytest.fixture
def long_running_command_request():
    """Tool call request for long-running command"""
    return {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "execute_linux_shell_command",
            "arguments": {
                "cmd": "for i in {1..5}; do echo $i; sleep 1; done"
            }
        }
    }


def get_test_client():
    """Helper to get test client with ASGI transport"""
    from mcp_remote_server import app
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestRemoteMCPServerEndpoints:
    """Tests for remote MCP server HTTP endpoints"""

    @pytest.mark.asyncio
    async def test_post_endpoint_requires_api_key(self, mock_env_vars, valid_initialize_request):
        """Test that POST endpoint requires API key authentication"""
        async with get_test_client() as client:
            # Request without API key should fail
            response = await client.post(
                "/mcp",
                json=valid_initialize_request,
                headers={"Accept": "application/json, text/event-stream"}
            )
            assert response.status_code == status.HTTP_401_UNAUTHORIZED
            assert "API key" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_post_endpoint_with_valid_api_key(self, mock_env_vars, api_key, valid_initialize_request):
        """Test that POST endpoint accepts valid API key"""
        async with get_test_client() as client:
            response = await client.post(
                "/mcp",
                json=valid_initialize_request,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Authorization": f"Bearer {api_key}"
                }
            )
            # Should not return 401
            assert response.status_code != status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_post_endpoint_requires_accept_header(self, mock_env_vars, api_key, valid_initialize_request):
        """Test that POST endpoint requires proper Accept header"""
        async with get_test_client() as client:
            response = await client.post(
                "/mcp",
                json=valid_initialize_request,
                headers={"Authorization": f"Bearer {api_key}"}
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "Accept header" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_initialize_creates_session(self, mock_env_vars, api_key, valid_initialize_request):
        """Test that initialize request creates a session and returns session ID"""
        async with get_test_client() as client:
            response = await client.post(
                "/mcp",
                json=valid_initialize_request,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Authorization": f"Bearer {api_key}"
                }
            )

            assert response.status_code == status.HTTP_200_OK
            assert "Mcp-Session-Id" in response.headers

            session_id = response.headers["Mcp-Session-Id"]
            # Session ID should be a valid UUID or secure token
            assert len(session_id) > 20
            assert session_id.replace("-", "").replace("_", "").isalnum()

            # Response should be valid JSON-RPC
            data = response.json()
            assert data["jsonrpc"] == "2.0"
            assert data["id"] == 1
            assert "result" in data

    @pytest.mark.asyncio
    async def test_subsequent_requests_require_session_id(self, mock_env_vars, api_key, valid_initialize_request, valid_tools_list_request):
        """Test that requests after initialize require session ID"""
        async with get_test_client() as client:
            # First initialize to get session
            init_response = await client.post(
                "/mcp",
                json=valid_initialize_request,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Authorization": f"Bearer {api_key}"
                }
            )
            session_id = init_response.headers["Mcp-Session-Id"]

            # Request without session ID should fail
            response = await client.post(
                "/mcp",
                json=valid_tools_list_request,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Authorization": f"Bearer {api_key}"
                }
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST

            # Request with session ID should succeed
            response = await client.post(
                "/mcp",
                json=valid_tools_list_request,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Authorization": f"Bearer {api_key}",
                    "Mcp-Session-Id": session_id
                }
            )
            assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_invalid_session_id_returns_404(self, mock_env_vars, api_key, valid_tools_list_request):
        """Test that invalid session ID returns 404"""
        async with get_test_client() as client:
            response = await client.post(
                "/mcp",
                json=valid_tools_list_request,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Authorization": f"Bearer {api_key}",
                    "Mcp-Session-Id": "invalid-session-id"
                }
            )
            assert response.status_code == status.HTTP_404_NOT_FOUND


class TestSSEStreaming:
    """Tests for Server-Sent Events streaming"""

    @pytest.mark.asyncio
    async def test_sse_stream_for_tool_call(self, mock_env_vars, api_key, valid_initialize_request, valid_tool_call_request):
        """Test that tool calls return SSE stream"""
        async with get_test_client() as client:
            # Initialize session
            init_response = await client.post(
                "/mcp",
                json=valid_initialize_request,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Authorization": f"Bearer {api_key}"
                }
            )
            session_id = init_response.headers["Mcp-Session-Id"]

            # Make tool call - should return SSE stream
            response = await client.post(
                "/mcp",
                json=valid_tool_call_request,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Authorization": f"Bearer {api_key}",
                    "Mcp-Session-Id": session_id
                },
                follow_redirects=False
            )

            # Should return SSE stream for tool calls
            assert response.status_code == status.HTTP_200_OK
            assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    @pytest.mark.asyncio
    async def test_sse_stream_contains_valid_events(self, mock_env_vars, api_key, valid_initialize_request, valid_tool_call_request):
        """Test that SSE stream contains properly formatted events"""
        async with get_test_client() as client:
            # Initialize session
            init_response = await client.post(
                "/mcp",
                json=valid_initialize_request,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Authorization": f"Bearer {api_key}"
                }
            )
            session_id = init_response.headers["Mcp-Session-Id"]

            # Make tool call
            response = await client.post(
                "/mcp",
                json=valid_tool_call_request,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Authorization": f"Bearer {api_key}",
                    "Mcp-Session-Id": session_id
                },
                follow_redirects=False
            )

            # Parse SSE events
            content = response.text
            events = []
            for line in content.split('\n\n'):
                if line.strip():
                    event_data = {}
                    for event_line in line.split('\n'):
                        if event_line.startswith('event:'):
                            event_data['event'] = event_line.split(':', 1)[1].strip()
                        elif event_line.startswith('data:'):
                            data_str = event_line.split(':', 1)[1].strip()
                            event_data['data'] = json.loads(data_str)
                    if event_data:
                        events.append(event_data)

            # Should have at least one event with the final response
            assert len(events) > 0

            # Last event should contain the JSON-RPC response
            last_event = events[-1]
            assert 'data' in last_event
            assert last_event['data']['jsonrpc'] == '2.0'
            assert last_event['data']['id'] == valid_tool_call_request['id']

    @pytest.mark.asyncio
    async def test_streaming_output_from_long_running_command(self, mock_env_vars, api_key, valid_initialize_request, long_running_command_request):
        """Test that long-running commands stream output progressively"""
        async with get_test_client() as client:
            # Initialize session
            init_response = await client.post(
                "/mcp",
                json=valid_initialize_request,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Authorization": f"Bearer {api_key}"
                }
            )
            session_id = init_response.headers["Mcp-Session-Id"]

            # Make long-running tool call
            response = await client.post(
                "/mcp",
                json=long_running_command_request,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Authorization": f"Bearer {api_key}",
                    "Mcp-Session-Id": session_id
                },
                timeout=30.0  # Allow time for command to complete
            )

            assert response.status_code == status.HTTP_200_OK

            # Parse events
            content = response.text
            stdout_events = []
            for line in content.split('\n\n'):
                if 'event: stdout' in line or 'event: stderr' in line:
                    stdout_events.append(line)

            # Should have multiple stdout events (progressive output)
            assert len(stdout_events) > 0


class TestSessionManagement:
    """Tests for session management functionality"""

    @pytest.mark.asyncio
    async def test_session_persists_across_requests(self, mock_env_vars, api_key, valid_initialize_request, valid_tools_list_request):
        """Test that session data persists across multiple requests"""
        async with get_test_client() as client:
            # Initialize
            init_response = await client.post(
                "/mcp",
                json=valid_initialize_request,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Authorization": f"Bearer {api_key}"
                }
            )
            session_id = init_response.headers["Mcp-Session-Id"]

            # Make multiple requests with same session
            for i in range(3):
                response = await client.post(
                    "/mcp",
                    json={**valid_tools_list_request, "id": 10 + i},
                    headers={
                        "Accept": "application/json, text/event-stream",
                        "Authorization": f"Bearer {api_key}",
                        "Mcp-Session-Id": session_id
                    }
                )
                assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_delete_session_endpoint(self, mock_env_vars, api_key, valid_initialize_request, valid_tools_list_request):
        """Test DELETE endpoint to terminate session"""
        async with get_test_client() as client:
            # Initialize
            init_response = await client.post(
                "/mcp",
                json=valid_initialize_request,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Authorization": f"Bearer {api_key}"
                }
            )
            session_id = init_response.headers["Mcp-Session-Id"]

            # Delete session
            delete_response = await client.delete(
                "/mcp",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Mcp-Session-Id": session_id
                }
            )
            assert delete_response.status_code in [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT]

            # Subsequent requests should fail with 404
            response = await client.post(
                "/mcp",
                json=valid_tools_list_request,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Authorization": f"Bearer {api_key}",
                    "Mcp-Session-Id": session_id
                }
            )
            assert response.status_code == status.HTTP_404_NOT_FOUND


class TestOriginValidation:
    """Tests for Origin header validation (security)"""

    @pytest.mark.asyncio
    async def test_localhost_origin_allowed(self, mock_env_vars, api_key, valid_initialize_request):
        """Test that localhost origins are allowed"""
        async with get_test_client() as client:
            response = await client.post(
                "/mcp",
                json=valid_initialize_request,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Authorization": f"Bearer {api_key}",
                    "Origin": "http://localhost:3000"
                }
            )
            # Should not be rejected for origin
            assert response.status_code != status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_validates_origin_header(self, mock_env_vars, api_key, valid_initialize_request):
        """Test that Origin header is validated for security"""
        # This test ensures we have origin validation logic
        # Implementation will determine exact behavior
        async with get_test_client() as client:
            response = await client.post(
                "/mcp",
                json=valid_initialize_request,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Authorization": f"Bearer {api_key}",
                    "Origin": "http://127.0.0.1:8888"
                }
            )
            # Should allow localhost IPs
            assert response.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]


class TestHealthEndpoint:
    """Tests for health check endpoint"""

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_ok(self):
        """Test that health endpoint is accessible without auth"""
        async with get_test_client() as client:
            response = await client.get("/health")
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "healthy"
