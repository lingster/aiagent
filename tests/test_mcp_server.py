import pytest
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch, Mock
import httpx
import anyio
from pydantic import ValidationError

# Import the functions to test
from mcp_server import (
    execute_linux_shell_command,
    execute_background_linux_shell_command,
    view_file,
    create_a_file,
    string_replace,
    insert_at,
    undo_file_edit,
)


# Helper function to validate JSON
def validate_json(data):
    """Validate that data is valid JSON"""
    if isinstance(data, str):
        json.loads(data)
        return True
    return False


# Fixtures for environment variables
@pytest.fixture
def env_docker_enabled(monkeypatch):
    """Set environment to use Docker mode"""
    monkeypatch.setenv("USE_DOCKER", "True")
    monkeypatch.setenv("MCP_PORT", "8888")
    monkeypatch.setenv("mcp_sync", "http://localhost:8888/api/sync/execute/")
    monkeypatch.setenv("mcp_async", "http://localhost:8888/api/async/execute/background/")
    monkeypatch.setenv("str_replace", "http://localhost:8888/api/files/")
    # Reload the module to pick up new env vars
    import importlib
    import mcp_server
    importlib.reload(mcp_server)


@pytest.fixture
def env_docker_disabled(monkeypatch):
    """Set environment to use non-Docker mode"""
    monkeypatch.setenv("USE_DOCKER", "False")
    monkeypatch.setenv("MCP_PORT", "8888")
    # Reload the module to pick up new env vars
    import importlib
    import mcp_server
    importlib.reload(mcp_server)


# Mock fixtures for httpx
@pytest.fixture
def mock_httpx_success():
    """Mock successful HTTP response"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    # Return dict directly, not as a coroutine
    mock_response.json = MagicMock(return_value={
        "command": "echo test",
        "output": "test output",
        "error": "",
        "return_code": 0
    })
    # raise_for_status should be a regular method (it doesn't return anything)
    mock_response.raise_for_status = MagicMock()
    return mock_response


@pytest.fixture
def mock_httpx_error():
    """Mock HTTP error response"""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.json = MagicMock(return_value={"error": "Internal server error"})

    def mock_raise_for_status():
        raise httpx.HTTPStatusError("Error", request=Mock(), response=mock_response)

    mock_response.raise_for_status = mock_raise_for_status
    return mock_response


# Mock fixture for anyio
@pytest.fixture
def mock_anyio_process():
    """Mock anyio process execution"""
    mock_process = MagicMock()
    mock_process.pid = 12345
    mock_process.returncode = 0
    mock_process.stdout = b"test output"
    mock_process.stderr = b""
    return mock_process


# Tests for execute_linux_shell_command


class TestExecuteLinuxShellCommand:
    """Tests for execute_linux_shell_command function"""

    async def test_docker_mode_success(self, env_docker_enabled, mock_httpx_success):
        """Test successful command execution in Docker mode"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.return_value = mock_httpx_success

            result = await execute_linux_shell_command("echo test")

            # Verify the result
            assert "output" in result or "error" not in result

            # Verify HTTP call was made
            assert mock_client_instance.post.called
            call_args = mock_client_instance.post.call_args

            # Validate that the payload is valid JSON
            posted_data = call_args.kwargs.get("data")
            assert posted_data is not None
            validate_json(posted_data)

            # Validate the JSON structure
            parsed_data = json.loads(posted_data)
            assert "command" in parsed_data
            assert parsed_data["command"] == "echo test"

    async def test_docker_mode_http_error(self, env_docker_enabled, mock_httpx_error):
        """Test HTTP error in Docker mode"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.return_value = mock_httpx_error

            result = await execute_linux_shell_command("echo test")

            # Should return error in result
            assert "error" in result

    async def test_docker_mode_network_exception(self, env_docker_enabled):
        """Test network exception in Docker mode"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.side_effect = httpx.ConnectError("Connection failed")

            result = await execute_linux_shell_command("echo test")

            # Should return error in result
            assert "error" in result
            assert "failed to run linux command" in result["error"]

    async def test_docker_mode_timeout(self, env_docker_enabled):
        """Test timeout in Docker mode"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.side_effect = httpx.TimeoutException("Timeout")

            result = await execute_linux_shell_command("sleep 100")

            # Should return error in result
            assert "error" in result

    async def test_non_docker_mode_success(self, env_docker_disabled, mock_anyio_process):
        """Test successful command execution in non-Docker mode"""
        with patch("anyio.run_process", return_value=mock_anyio_process) as mock_run:
            result = await execute_linux_shell_command("echo test")

            # Verify the result
            assert "command" in result
            assert "output" in result
            assert "return_code" in result
            assert result["command"] == "echo test"
            assert result["output"] == "test output"
            assert result["return_code"] == 0

            # Verify anyio.run_process was called
            assert mock_run.called

    async def test_non_docker_mode_exception(self, env_docker_disabled):
        """Test exception in non-Docker mode"""
        with patch("anyio.run_process") as mock_run:
            mock_run.side_effect = Exception("Process execution failed")

            result = await execute_linux_shell_command("echo test")

            # Should return error in result
            assert "error" in result
            assert "failed to run linux command" in result["error"]


# Tests for execute_background_linux_shell_command


class TestExecuteBackgroundLinuxShellCommand:
    """Tests for execute_background_linux_shell_command function"""

    async def test_docker_mode_success(self, env_docker_enabled, mock_httpx_success):
        """Test successful background command execution in Docker mode"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.return_value = mock_httpx_success

            result = await execute_background_linux_shell_command("python server.py")

            # Verify the result
            assert "output" in result or "error" not in result

            # Verify HTTP call was made
            assert mock_client_instance.post.called
            call_args = mock_client_instance.post.call_args

            # Validate that the payload is valid JSON
            posted_data = call_args.kwargs.get("data")
            assert posted_data is not None
            validate_json(posted_data)

    async def test_docker_mode_error(self, env_docker_enabled, mock_httpx_error):
        """Test error in Docker mode"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.return_value = mock_httpx_error

            result = await execute_background_linux_shell_command("python server.py")

            # Should return error in result
            assert "error" in result

    async def test_docker_mode_exception(self, env_docker_enabled):
        """Test exception in Docker mode"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.side_effect = Exception("Network error")

            result = await execute_background_linux_shell_command("python server.py")

            # Should return error in result
            assert "error" in result
            assert "failed to run async linux command" in result["error"]

    async def test_non_docker_mode_success(self, env_docker_disabled):
        """Test successful background command in non-Docker mode"""
        mock_process = MagicMock()
        mock_process.pid = 12345

        with patch("asyncio.create_subprocess_shell", return_value=mock_process) as mock_subprocess:
            result = await execute_background_linux_shell_command("python server.py")

            # Verify the result
            assert "pid" in result
            assert result["pid"] == 12345

            # Verify asyncio.create_subprocess_shell was called
            assert mock_subprocess.called

    async def test_non_docker_mode_exception(self, env_docker_disabled):
        """Test exception in non-Docker mode"""
        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_subprocess.side_effect = Exception("Process start failed")

            result = await execute_background_linux_shell_command("python server.py")

            # Should return error in result
            assert "error" in result


# Helper function to create mock HTTP responses for file operations
def create_mock_response(status_code, json_data):
    """Create a mock HTTP response with proper json() method"""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json = MagicMock(return_value=json_data)
    return mock_response


# Tests for file operations


class TestViewFile:
    """Tests for view_file function"""

    async def test_view_file_success(self):
        """Test successful file view"""
        mock_response = create_mock_response(200, {
            "success": True,
            "content": "file content here",
            "message": "File viewed successfully"
        })

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.return_value = mock_response

            result = await view_file("/path/to/file.txt")

            # Verify the result
            assert result["success"] is True
            assert "content" in result
            assert result["content"] == "file content here"

            # Verify HTTP call was made
            assert mock_client_instance.post.called
            call_args = mock_client_instance.post.call_args

            # Validate JSON payload
            posted_json = call_args.kwargs.get("json")
            assert posted_json is not None
            assert "command" in posted_json
            assert "path" in posted_json

            # Validate that path is valid JSON
            validate_json(posted_json["path"])
            path_value = json.loads(posted_json["path"])
            assert path_value == "/path/to/file.txt"

    async def test_view_file_with_range(self):
        """Test file view with line range"""
        mock_response = create_mock_response(200, {
            "success": True,
            "content": "partial content",
            "message": "Partial file viewed"
        })

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.return_value = mock_response

            result = await view_file("/path/to/file.txt", view_range=[10, 20])

            # Verify the result
            assert result["success"] is True

            # Verify JSON payload includes view_range
            call_args = mock_client_instance.post.call_args
            posted_json = call_args.kwargs.get("json")
            assert "view_range" in posted_json
            validate_json(posted_json["view_range"])

    async def test_view_file_not_found(self):
        """Test viewing non-existent file"""
        mock_response = create_mock_response(200, {
            "success": False,
            "message": "File not found"
        })

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.return_value = mock_response

            result = await view_file("/nonexistent/file.txt")

            # Should return error
            assert result["success"] is False
            assert "error" in result

    async def test_view_file_http_error(self):
        """Test HTTP error when viewing file"""
        mock_response = create_mock_response(500, {})

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.return_value = mock_response

            result = await view_file("/path/to/file.txt")

            # Should return error
            assert result["success"] is False
            assert "error" in result

    async def test_view_file_exception(self):
        """Test exception when viewing file"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.side_effect = Exception("Network error")

            result = await view_file("/path/to/file.txt")

            # Should return error
            assert result["success"] is False
            assert "error" in result


class TestCreateFile:
    """Tests for create_a_file function"""

    async def test_create_file_success(self):
        """Test successful file creation"""
        mock_response = create_mock_response(200, {
            "success": True,
            "message": "File created successfully"
        })

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.return_value = mock_response

            result = await create_a_file("/path/to/new_file.txt", "file content")

            # Verify the result
            assert result["success"] is True

            # Verify HTTP call and JSON validation
            assert mock_client_instance.post.called
            call_args = mock_client_instance.post.call_args
            posted_json = call_args.kwargs.get("json")

            assert "command" in posted_json
            assert posted_json["command"] == "create"
            assert "path" in posted_json
            assert "file_text" in posted_json

            # Validate JSON fields
            validate_json(posted_json["path"])
            validate_json(posted_json["file_text"])

            path_value = json.loads(posted_json["path"])
            content_value = json.loads(posted_json["file_text"])
            assert path_value == "/path/to/new_file.txt"
            assert content_value == "file content"

    async def test_create_file_already_exists(self):
        """Test creating file that already exists"""
        mock_response = create_mock_response(200, {
            "success": False,
            "message": "File already exists"
        })

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.return_value = mock_response

            result = await create_a_file("/path/to/existing.txt", "content")

            # Should return failure
            assert result["success"] is False

    async def test_create_file_http_error(self):
        """Test HTTP error when creating file"""
        mock_response = create_mock_response(403, {})

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.return_value = mock_response

            result = await create_a_file("/path/to/file.txt", "content")

            # Should return error
            assert result["success"] is False
            assert "error" in result

    async def test_create_file_exception(self):
        """Test exception when creating file"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.side_effect = Exception("Disk error")

            result = await create_a_file("/path/to/file.txt", "content")

            # Should return error
            assert result["success"] is False
            assert "error" in result


class TestStringReplace:
    """Tests for string_replace function"""

    async def test_string_replace_success(self):
        """Test successful string replacement"""
        mock_response = create_mock_response(200, {
            "success": True,
            "message": "String replaced successfully"
        })

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.return_value = mock_response

            result = await string_replace("/path/to/file.txt", "old text", "new text")

            # Verify the result
            assert result["success"] is True

            # Verify JSON payload
            call_args = mock_client_instance.post.call_args
            posted_json = call_args.kwargs.get("json")

            assert posted_json["command"] == "str_replace"
            assert "path" in posted_json
            assert "old_str" in posted_json
            assert "new_str" in posted_json

            # Validate JSON fields
            validate_json(posted_json["path"])
            validate_json(posted_json["old_str"])
            validate_json(posted_json["new_str"])

            old_str_value = json.loads(posted_json["old_str"])
            new_str_value = json.loads(posted_json["new_str"])
            assert old_str_value == "old text"
            assert new_str_value == "new text"

    async def test_string_replace_not_found(self):
        """Test replacement when string not found"""
        mock_response = create_mock_response(200, {
            "success": False,
            "message": "String not found in file"
        })

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.return_value = mock_response

            result = await string_replace("/path/to/file.txt", "nonexistent", "new")

            # Should return failure
            assert result["success"] is False

    async def test_string_replace_http_error(self):
        """Test HTTP error during string replacement"""
        mock_response = create_mock_response(500, {})

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.return_value = mock_response

            result = await string_replace("/path/to/file.txt", "old", "new")

            # Should return error
            assert result["success"] is False
            assert "error" in result

    async def test_string_replace_exception(self):
        """Test exception during string replacement"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.side_effect = Exception("IO error")

            result = await string_replace("/path/to/file.txt", "old", "new")

            # Should return error
            assert result["success"] is False
            assert "error" in result


class TestInsertAt:
    """Tests for insert_at function"""

    async def test_insert_at_success(self):
        """Test successful line insertion"""
        mock_response = create_mock_response(200, {
            "success": True,
            "message": "Text inserted successfully"
        })

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.return_value = mock_response

            result = await insert_at("/path/to/file.txt", 10, "new line content")

            # Verify the result
            assert result["success"] is True

            # Verify JSON payload
            call_args = mock_client_instance.post.call_args
            posted_json = call_args.kwargs.get("json")

            assert posted_json["command"] == "insert"
            assert "path" in posted_json
            assert "insert_line" in posted_json
            assert "new_str" in posted_json

            # Validate JSON fields
            validate_json(posted_json["path"])
            validate_json(posted_json["insert_line"])
            validate_json(posted_json["new_str"])

            insert_line_value = json.loads(posted_json["insert_line"])
            assert insert_line_value == 10

    async def test_insert_at_invalid_line(self):
        """Test insertion at invalid line number"""
        mock_response = create_mock_response(200, {
            "success": False,
            "message": "Invalid line number"
        })

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.return_value = mock_response

            result = await insert_at("/path/to/file.txt", -1, "content")

            # Should return failure
            assert result["success"] is False

    async def test_insert_at_http_error(self):
        """Test HTTP error during insertion"""
        mock_response = create_mock_response(404, {})

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.return_value = mock_response

            result = await insert_at("/path/to/file.txt", 5, "content")

            # Should return error
            assert result["success"] is False
            assert "error" in result

    async def test_insert_at_exception(self):
        """Test exception during insertion"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.side_effect = Exception("Write error")

            result = await insert_at("/path/to/file.txt", 5, "content")

            # Should return error
            assert result["success"] is False
            assert "error" in result


class TestUndoFileEdit:
    """Tests for undo_file_edit function"""

    async def test_undo_edit_success(self):
        """Test successful undo operation"""
        mock_response = create_mock_response(200, {
            "success": True,
            "message": "Edit undone successfully"
        })

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.return_value = mock_response

            result = await undo_file_edit("/path/to/file.txt")

            # Verify the result
            assert result["success"] is True

            # Verify JSON payload
            call_args = mock_client_instance.post.call_args
            posted_json = call_args.kwargs.get("json")

            assert posted_json["command"] == "undo_edit"
            assert "path" in posted_json

            # Validate JSON field
            validate_json(posted_json["path"])

    async def test_undo_edit_no_history(self):
        """Test undo when no edit history exists"""
        mock_response = create_mock_response(200, {
            "success": False,
            "message": "No edit history available"
        })

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.return_value = mock_response

            result = await undo_file_edit("/path/to/file.txt")

            # Should return failure
            assert result["success"] is False

    async def test_undo_edit_http_error(self):
        """Test HTTP error during undo"""
        mock_response = create_mock_response(500, {})

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.return_value = mock_response

            result = await undo_file_edit("/path/to/file.txt")

            # Should return error
            assert result["success"] is False
            assert "error" in result

    async def test_undo_edit_exception(self):
        """Test exception during undo"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.side_effect = Exception("Undo error")

            result = await undo_file_edit("/path/to/file.txt")

            # Should return error
            assert result["success"] is False
            assert "error" in result
