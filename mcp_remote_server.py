"""
Remote MCP Server with Streamable HTTP Transport

This server implements the MCP (Model Context Protocol) specification version 2025-03-26
with Streamable HTTP transport including SSE (Server-Sent Events) support.

Features:
- Streamable HTTP transport with POST/GET/DELETE methods
- Server-Sent Events for streaming command output
- Session management with Mcp-Session-Id headers
- API key authentication
- Origin validation for security
"""

import os
import sys
import asyncio
import uuid
import json
from typing import Optional, Dict, Any, AsyncIterator
from datetime import datetime, timedelta

from fastapi import FastAPI, Request, Response, HTTPException, Header, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from loguru import logger
import httpx

# Configure logging
logger.remove()
logger.add(sys.stderr, format="{time} {level} {message}", level="INFO")

# Environment configuration
MCP_API_KEY = os.environ.get("MCP_API_KEY", "")
MCP_REMOTE_PORT = int(os.environ.get("MCP_REMOTE_PORT", "8888"))
MCP_PORT = os.environ.get("MCP_PORT", "8181")
USE_DOCKER = os.environ.get("USE_DOCKER", "True") == "True"

# Backend URLs
BACKEND_BASE_URL = f"http://localhost:{MCP_PORT}"
execute_url = f"{BACKEND_BASE_URL}/api/sync/execute/"
async_url = f"{BACKEND_BASE_URL}/api/async/execute/background/"
file_operations_base_url = f"{BACKEND_BASE_URL}/api/files/"

# Session storage (in production, use Redis or similar)
sessions: Dict[str, Dict[str, Any]] = {}
SESSION_TIMEOUT = timedelta(hours=1)


# Models
class JSONRPCRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[int | str] = None
    method: str
    params: Optional[Dict[str, Any]] = None


class JSONRPCResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[int | str]
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


class Session(BaseModel):
    session_id: str
    created_at: datetime
    last_accessed: datetime
    initialized: bool = False
    client_info: Optional[Dict[str, Any]] = None


# FastAPI app
app = FastAPI(
    title="Remote MCP Server",
    description="MCP Server with Streamable HTTP Transport",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:*", "http://127.0.0.1:*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Authentication
async def verify_api_key(authorization: Optional[str] = Header(None)) -> bool:
    """Verify API key from Authorization header"""
    if not MCP_API_KEY:
        # If no API key is configured, allow access (development mode)
        logger.warning("No MCP_API_KEY configured - authentication disabled")
        return True

    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Provide Authorization header with Bearer token."
        )

    # Support both "Bearer token" and just "token"
    token = authorization.replace("Bearer ", "").strip()

    if token != MCP_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )

    return True


def validate_origin(origin: Optional[str]) -> bool:
    """Validate Origin header to prevent DNS rebinding attacks"""
    if not origin:
        return True  # Allow requests without Origin header

    # Allow localhost and 127.0.0.1
    allowed_patterns = [
        "http://localhost",
        "https://localhost",
        "http://127.0.0.1",
        "https://127.0.0.1",
    ]

    for pattern in allowed_patterns:
        if origin.startswith(pattern):
            return True

    logger.warning(f"Rejected request from origin: {origin}")
    return False


def create_session() -> Session:
    """Create a new session with secure ID"""
    session_id = str(uuid.uuid4())
    session = Session(
        session_id=session_id,
        created_at=datetime.now(),
        last_accessed=datetime.now()
    )
    sessions[session_id] = session.model_dump()
    logger.info(f"Created new session: {session_id}")
    return session


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Get session by ID, checking for expiration"""
    session = sessions.get(session_id)
    if not session:
        return None

    # Check expiration
    last_accessed = session["last_accessed"]
    if isinstance(last_accessed, str):
        last_accessed = datetime.fromisoformat(last_accessed)

    if datetime.now() - last_accessed > SESSION_TIMEOUT:
        # Session expired
        sessions.pop(session_id, None)
        logger.info(f"Session expired: {session_id}")
        return None

    # Update last accessed time
    session["last_accessed"] = datetime.now()
    return session


def delete_session(session_id: str) -> bool:
    """Delete a session"""
    if session_id in sessions:
        sessions.pop(session_id)
        logger.info(f"Deleted session: {session_id}")
        return True
    return False


async def execute_mcp_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute an MCP tool by calling the backend"""
    from remote_server_lib.core import CommandRequest

    if tool_name == "execute_linux_shell_command":
        cmd = arguments.get("cmd", "")
        req = CommandRequest(command=cmd)
        httpx_timeout = httpx.Timeout(60)
        async with httpx.AsyncClient() as client:
            response = await client.post(execute_url, data=req.model_dump_json(), timeout=httpx_timeout)
        response.raise_for_status()
        return response.json()

    elif tool_name == "execute_background_linux_shell_command":
        cmd = arguments.get("cmd", "")
        req = CommandRequest(command=cmd)
        async with httpx.AsyncClient() as client:
            response = await client.post(async_url, data=req.model_dump_json())
            response.raise_for_status()
            return response.json()

    elif tool_name == "view_file":
        path = arguments.get("path", "")
        view_range = arguments.get("view_range")
        payload = {
            "command": "view",
            "path": path,
            "view_range": json.dumps(view_range)
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{file_operations_base_url}operation/", json=payload)
            return response.json()

    elif tool_name == "create_a_file":
        payload = {
            "command": "create",
            "path": arguments.get("path", ""),
            "file_text": json.dumps(arguments.get("file_text", "")),
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{file_operations_base_url}operation/", json=payload)
            return response.json()

    elif tool_name == "string_replace":
        payload = {
            "command": "str_replace",
            "path": arguments.get("path", ""),
            "old_str": json.dumps(arguments.get("old_str", "")),
            "new_str": json.dumps(arguments.get("new_str", ""))
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{file_operations_base_url}operation/", json=payload)
            return response.json()

    elif tool_name == "insert_at":
        payload = {
            "command": "insert",
            "path": arguments.get("path", ""),
            "insert_line": json.dumps(arguments.get("insert_line", 0)),
            "new_str": json.dumps(arguments.get("new_str", ""))
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{file_operations_base_url}operation/", json=payload)
            return response.json()

    elif tool_name == "undo_file_edit":
        payload = {
            "command": "undo_edit",
            "path": arguments.get("path", "")
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{file_operations_base_url}operation/", json=payload)
            return response.json()

    else:
        raise ValueError(f"Unknown tool: {tool_name}")


async def stream_command_output(cmd: str, request_id: int | str) -> AsyncIterator[str]:
    """
    Stream command output as SSE events
    Yields stdout/stderr as they happen, then final result
    """
    try:
        # Start the process
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        output_lines = []
        error_lines = []

        # Stream stdout
        if proc.stdout:
            async for line in proc.stdout:
                decoded_line = line.decode('utf-8')
                output_lines.append(decoded_line)
                # Send as SSE event
                event_data = {"content": decoded_line.rstrip()}
                yield f"event: stdout\ndata: {json.dumps(event_data)}\n\n"

        # Stream stderr
        if proc.stderr:
            async for line in proc.stderr:
                decoded_line = line.decode('utf-8')
                error_lines.append(decoded_line)
                # Send as SSE event
                event_data = {"content": decoded_line.rstrip()}
                yield f"event: stderr\ndata: {json.dumps(event_data)}\n\n"

        # Wait for process to complete
        await proc.wait()

        # Send final result as JSON-RPC response
        result = {
            "command": cmd,
            "output": "".join(output_lines),
            "error": "".join(error_lines),
            "return_code": proc.returncode,
            "pid": proc.pid
        }

        jsonrpc_response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result
        }

        yield f"event: message\ndata: {json.dumps(jsonrpc_response)}\n\n"

    except Exception as e:
        # Send error as JSON-RPC error response
        error_response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32000,
                "message": str(e)
            }
        }
        yield f"event: message\ndata: {json.dumps(error_response)}\n\n"


async def handle_mcp_request(request: JSONRPCRequest, session: Dict[str, Any]) -> Dict[str, Any]:
    """Handle MCP JSON-RPC request and return response"""

    method = request.method
    params = request.params or {}

    if method == "initialize":
        # Handle initialization
        session["initialized"] = True
        session["client_info"] = params.get("clientInfo", {})

        result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
                "streaming": True
            },
            "serverInfo": {
                "name": "remote-mcp-server",
                "version": "1.0.0"
            }
        }
        return {"jsonrpc": "2.0", "id": request.id, "result": result}

    elif method == "tools/list":
        # Return available tools
        tools = [
            {
                "name": "execute_linux_shell_command",
                "description": "Execute a Linux shell command synchronously",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "cmd": {"type": "string", "description": "The command to execute"}
                    },
                    "required": ["cmd"]
                }
            },
            {
                "name": "execute_background_linux_shell_command",
                "description": "Execute a Linux shell command asynchronously in the background",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "cmd": {"type": "string", "description": "The command to execute"}
                    },
                    "required": ["cmd"]
                }
            },
            {
                "name": "view_file",
                "description": "View the contents of a file or directory",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "view_range": {"type": "array", "items": {"type": "integer"}}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "create_a_file",
                "description": "Create a new file with specified content",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "file_text": {"type": "string"}
                    },
                    "required": ["path", "file_text"]
                }
            },
            {
                "name": "string_replace",
                "description": "Replace text in a file",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "old_str": {"type": "string"},
                        "new_str": {"type": "string"}
                    },
                    "required": ["path", "old_str", "new_str"]
                }
            },
            {
                "name": "insert_at",
                "description": "Insert text at a specific line in a file",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "insert_line": {"type": "integer"},
                        "new_str": {"type": "string"}
                    },
                    "required": ["path", "insert_line", "new_str"]
                }
            },
            {
                "name": "undo_file_edit",
                "description": "Revert the last edit made to a file",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"}
                    },
                    "required": ["path"]
                }
            }
        ]
        return {"jsonrpc": "2.0", "id": request.id, "result": {"tools": tools}}

    elif method == "tools/call":
        # This will be handled by SSE streaming
        # Return indicator that streaming is needed
        return {"_stream_required": True}

    else:
        # Unknown method
        return {
            "jsonrpc": "2.0",
            "id": request.id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}"
            }
        }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


@app.post("/mcp")
async def mcp_endpoint(
    request: Request,
    accept: Optional[str] = Header(None),
    mcp_session_id: Optional[str] = Header(None, alias="Mcp-Session-Id"),
    origin: Optional[str] = Header(None),
    authenticated: bool = Depends(verify_api_key)
):
    """
    Main MCP endpoint for Streamable HTTP transport
    Handles POST requests with JSON-RPC messages
    """

    # Validate Origin header
    if not validate_origin(origin):
        raise HTTPException(status_code=403, detail="Invalid origin")

    # Validate Accept header
    if not accept or not any(
        mime in accept for mime in ["application/json", "text/event-stream"]
    ):
        raise HTTPException(
            status_code=400,
            detail="Accept header must include 'application/json' and/or 'text/event-stream'"
        )

    # Parse request body
    try:
        body = await request.json()
        jsonrpc_request = JSONRPCRequest(**body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON-RPC request: {str(e)}")

    # Handle session
    session = None
    is_initialize = jsonrpc_request.method == "initialize"

    if is_initialize:
        # Create new session for initialize request
        session_obj = create_session()
        session = sessions[session_obj.session_id]
        session_id = session_obj.session_id
    else:
        # Require session ID for non-initialize requests
        if not mcp_session_id:
            raise HTTPException(
                status_code=400,
                detail="Mcp-Session-Id header required for non-initialize requests"
            )

        session = get_session(mcp_session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found or expired")

        session_id = mcp_session_id

    # Handle the request
    response_data = await handle_mcp_request(jsonrpc_request, session)

    # Check if streaming is required (for tool calls)
    if response_data.get("_stream_required"):
        # Return SSE stream
        tool_name = jsonrpc_request.params.get("name")
        arguments = jsonrpc_request.params.get("arguments", {})

        # For shell commands, use streaming
        if tool_name == "execute_linux_shell_command":
            cmd = arguments.get("cmd", "")

            async def event_generator():
                async for event in stream_command_output(cmd, jsonrpc_request.id):
                    yield event

            headers = {"Mcp-Session-Id": session_id} if is_initialize else {}
            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers=headers
            )
        else:
            # For other tools, execute and return result
            try:
                result = await execute_mcp_tool(tool_name, arguments)
                response_data = {
                    "jsonrpc": "2.0",
                    "id": jsonrpc_request.id,
                    "result": result
                }
            except Exception as e:
                response_data = {
                    "jsonrpc": "2.0",
                    "id": jsonrpc_request.id,
                    "error": {
                        "code": -32000,
                        "message": str(e)
                    }
                }

    # Return JSON response
    headers = {}
    if is_initialize:
        headers["Mcp-Session-Id"] = session_id

    return JSONResponse(content=response_data, headers=headers)


@app.delete("/mcp")
async def delete_mcp_session(
    mcp_session_id: Optional[str] = Header(None, alias="Mcp-Session-Id"),
    authenticated: bool = Depends(verify_api_key)
):
    """Delete/terminate an MCP session"""
    if not mcp_session_id:
        raise HTTPException(status_code=400, detail="Mcp-Session-Id header required")

    if delete_session(mcp_session_id):
        return Response(status_code=204)
    else:
        raise HTTPException(status_code=404, detail="Session not found")


@app.get("/mcp")
async def mcp_sse_endpoint(
    mcp_session_id: Optional[str] = Header(None, alias="Mcp-Session-Id"),
    authenticated: bool = Depends(verify_api_key)
):
    """
    Optional GET endpoint for server-initiated SSE streams
    Returns 405 if not implemented for this use case
    """
    # For now, we don't support server-initiated streams via GET
    # All streaming happens through POST responses
    raise HTTPException(
        status_code=405,
        detail="Server-initiated SSE streams not supported. Use POST with streaming responses."
    )


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting Remote MCP Server on port {MCP_REMOTE_PORT}")
    logger.info(f"API Key authentication: {'enabled' if MCP_API_KEY else 'disabled (development mode)'}")
    logger.info(f"Backend URL: {BACKEND_BASE_URL}")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=MCP_REMOTE_PORT,
        log_level="info"
    )
