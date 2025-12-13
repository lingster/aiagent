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

from remote_server_lib.command_executor import CommandExecutor
from remote_server_lib.process_registry import get_process_registry

# Configure logging
#logger.remove()
#logger.add(sys.stderr, format="{time} {level} {message}", level="INFO")

# Environment configuration
MCP_API_KEY = os.environ.get("MCP_API_KEY", "")
MCP_REMOTE_PORT = int(os.environ.get("MCP_REMOTE_PORT", "8888"))
MCP_REMOTE_HOST = str(os.environ.get("MCP_REMOTE_HOST", "127.0.0.1"))
MCP_PORT = os.environ.get("MCP_PORT", "8181")
USE_DOCKER = os.environ.get("USE_DOCKER", "True") == "True"
TERMINATION_TIMEOUT = int(os.environ.get("TERMINATION_TIMEOUT", "30"))

# Initialize the command executor
executor = CommandExecutor(
    use_docker=USE_DOCKER,
    mcp_port=MCP_PORT
)

# Initialize the process registry
process_registry = get_process_registry(termination_timeout=TERMINATION_TIMEOUT)

# Backend URL for logging
BACKEND_BASE_URL = f"http://localhost:{MCP_PORT}"

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
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
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
    """Execute an MCP tool using the shared executor and return MCP-formatted response"""
    logger.info(f"Tool called: {tool_name} with arguments: {arguments}")

    if tool_name == "execute_linux_shell_command":
        cmd = arguments.get("cmd", "")
        logger.info(f"exec {cmd}")

        # Use the shared executor
        backend_result = await executor.execute_linux_shell_command(cmd)
        logger.info(f"Backend response type: {type(backend_result)}, value: {backend_result}")

        # Handle double-encoded JSON
        if isinstance(backend_result, str):
            backend_result = json.loads(backend_result)
            logger.info(f"Parsed string to dict: {backend_result}")

        # Format as MCP tool result with content array
        output_text = backend_result.get("output", "")
        error_text = backend_result.get("error", "")
        return_code = backend_result.get("return_code", 0)

        # Combine output and error if both exist
        result_text = output_text
        if error_text:
            result_text = f"{output_text}\nSTDERR:\n{error_text}" if output_text else error_text

        result_payload = {
            "content": [
                {
                    "type": "text",
                    "text": result_text if result_text else f"Command completed with return code {return_code}"
                }
            ],
            "isError": return_code != 0 or bool(backend_result.get("error"))
        }
        logger.info(f"Tool {tool_name} completed successfully")
        return result_payload

    elif tool_name == "execute_background_linux_shell_command":
        cmd = arguments.get("cmd", "")
        logger.info(f"bkg: {cmd}")

        # Use the shared executor
        backend_result = await executor.execute_background_linux_shell_command(cmd)

        # Handle double-encoded JSON
        if isinstance(backend_result, str):
            backend_result = json.loads(backend_result)

        # Format as MCP tool result
        message = backend_result.get("message", "Command started in background")
        task_id = backend_result.get("task_id", "")
        pid = backend_result.get("pid", "")
        result_text = f"{message}"
        if task_id:
            result_text += f"\nTask ID: {task_id}"
        if pid:
            result_text += f"\nPID: {pid}"

        result_payload = {
            "content": [
                {
                    "type": "text",
                    "text": result_text
                }
            ],
            "isError": bool(backend_result.get("error"))
        }
        logger.info(f"Tool {tool_name} completed successfully")
        return result_payload

    elif tool_name == "view_file":
        path = arguments.get("path", "")
        view_range = arguments.get("view_range")

        # Use the shared executor
        backend_result = await executor.view_file(path, view_range)

        # Format as MCP tool result
        content = backend_result.get("content", "")
        is_error = not backend_result.get("success", True)
        result_payload = {
            "content": [
                {
                    "type": "text",
                    "text": content if content else backend_result.get("error", "")
                }
            ],
            "isError": is_error
        }
        logger.info(f"Tool {tool_name} completed successfully")
        return result_payload

    elif tool_name == "create_a_file":
        path = arguments.get("path", "")
        file_text = arguments.get("file_text", "")

        # Use the shared executor
        backend_result = await executor.create_a_file(path, file_text)

        # Format as MCP tool result
        message = backend_result.get("message", "File created successfully")
        is_error = not backend_result.get("success", True)
        result_payload = {
            "content": [
                {
                    "type": "text",
                    "text": message if not is_error else backend_result.get("error", message)
                }
            ],
            "isError": is_error
        }
        logger.info(f"Tool {tool_name} completed successfully")
        return result_payload

    elif tool_name == "string_replace":
        path = arguments.get("path", "")
        old_str = arguments.get("old_str", "")
        new_str = arguments.get("new_str", "")

        # Use the shared executor
        backend_result = await executor.string_replace(path, old_str, new_str)

        # Format as MCP tool result
        message = backend_result.get("message", "String replaced successfully")
        is_error = not backend_result.get("success", True)
        result_payload = {
            "content": [
                {
                    "type": "text",
                    "text": message if not is_error else backend_result.get("error", message)
                }
            ],
            "isError": is_error
        }
        logger.info(f"Tool {tool_name} completed successfully")
        return result_payload

    elif tool_name == "insert_at":
        path = arguments.get("path", "")
        insert_line = arguments.get("insert_line", 0)
        new_str = arguments.get("new_str", "")

        # Use the shared executor
        backend_result = await executor.insert_at(path, insert_line, new_str)

        # Format as MCP tool result
        message = backend_result.get("message", "Text inserted successfully")
        is_error = not backend_result.get("success", True)
        result_payload = {
            "content": [
                {
                    "type": "text",
                    "text": message if not is_error else backend_result.get("error", message)
                }
            ],
            "isError": is_error
        }
        logger.info(f"Tool {tool_name} completed successfully")
        return result_payload

    elif tool_name == "undo_file_edit":
        path = arguments.get("path", "")

        # Use the shared executor
        backend_result = await executor.undo_file_edit(path)

        # Format as MCP tool result
        message = backend_result.get("message", "Edit undone successfully")
        is_error = not backend_result.get("success", True)
        result_payload = {
            "content": [
                {
                    "type": "text",
                    "text": message if not is_error else backend_result.get("error", message)
                }
            ],
            "isError": is_error
        }
        logger.info(f"Tool {tool_name} completed successfully")
        return result_payload

    elif tool_name == "terminate_process":
        pid = arguments.get("pid", 0)

        logger.info(f"Terminating process {pid}")

        # Terminate the process gracefully
        if USE_DOCKER:
            # Call backend API
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"http://localhost:{MCP_PORT}/api/async/process/terminate_by_pid/",
                        params={"pid": pid}
                    )
                    if response.status_code == 200:
                        backend_result = response.json()
                        result = {
                            "success": True,
                            "request_id": backend_result.get("request_id"),
                            "signal": backend_result.get("signal"),
                            "reason": backend_result.get("message")
                        }
                    else:
                        result = {"success": False, "error": response.json().get("detail", "Unknown error")}
            except Exception as e:
                result = {"success": False, "error": str(e)}
        else:
            # Use local process registry
            result = await process_registry.terminate_gracefully(
                pid=pid,
                reason="Manual termination via terminate_process tool"
            )

        # Format as MCP tool result
        is_error = not result.get("success", False)
        if is_error:
            message = result.get("error", "Failed to terminate process")
        else:
            message = f"Process {pid} terminated successfully\n"
            message += f"Request ID: {result.get('request_id')}\n"
            message += f"Signal: {result.get('signal')}\n"
            message += f"Reason: {result.get('reason', 'Manual termination')}"

        result_payload = {
            "content": [
                {
                    "type": "text",
                    "text": message
                }
            ],
            "isError": is_error
        }
        logger.info(f"Tool {tool_name} completed")
        return result_payload

    elif tool_name == "list_processes":
        logger.info("Listing all background processes")

        # Get all processes from registry
        if USE_DOCKER:
            # Call backend API
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"http://localhost:{MCP_PORT}/api/async/processes/list/"
                    )
                    if response.status_code == 200:
                        backend_result = response.json()
                        processes_data = backend_result.get("processes", [])
                        # Convert to ProcessInfo-like objects for formatting
                        from datetime import datetime
                        from types import SimpleNamespace
                        processes = [
                            SimpleNamespace(
                                pid=p["pid"],
                                request_id=p["request_id"],
                                command=p["command"],
                                status=p["status"],
                                started_at=datetime.fromisoformat(p["started_at"]),
                                exit_code=p["exit_code"]
                            )
                            for p in processes_data
                        ]
                    else:
                        processes = []
            except Exception as e:
                logger.error(f"Failed to list processes from backend: {str(e)}")
                processes = []
        else:
            # Use local process registry
            processes = await process_registry.list_all()

        if not processes:
            message = "No background processes running"
        else:
            message = f"Background Processes ({len(processes)}):\n\n"
            for proc_info in processes:
                message += f"PID: {proc_info.pid}\n"
                message += f"  Request ID: {proc_info.request_id}\n"
                message += f"  Command: {proc_info.command}\n"
                message += f"  Status: {proc_info.status}\n"
                message += f"  Started: {proc_info.started_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
                if proc_info.exit_code is not None:
                    message += f"  Exit Code: {proc_info.exit_code}\n"
                message += "\n"

        result_payload = {
            "content": [
                {
                    "type": "text",
                    "text": message
                }
            ],
            "isError": False
        }
        logger.info(f"Tool {tool_name} completed successfully")
        return result_payload

    else:
        logger.error(f"Unknown tool requested: {tool_name}")
        raise ValueError(f"Unknown tool: {tool_name}")


async def stream_command_output(cmd: str, request_id: int) -> AsyncIterator[str]:
    """
    Stream command output as SSE events
    Yields stdout/stderr as they happen, then final result
    """
    logger.info(f"Starting streaming execution of command: {cmd}")
    try:
        # Start the process
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        logger.info(f"Process started with PID: {proc.pid}")

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
        logger.info(f"Process {proc.pid} completed with return code: {proc.returncode}")

        # Send final result as JSON-RPC response
        result = {
            "command": cmd,
            "output": "".join(output_lines),
            "error": "".join(error_lines),
            "return_code": proc.returncode,
            "pid": proc.pid
        }
        logger.info(f"Command output: {result}")

        jsonrpc_response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result
        }

        logger.info(f"Sending final SSE event with result")
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


async def stream_background_command(cmd: str, request_id: int) -> AsyncIterator[str]:
    """
    Stream background command output as SSE events with MCP tool response format.
    Yields stdout/stderr as they happen, then final MCP-formatted tool result.
    Supports cancellation via process registry.
    """
    logger.info(f"Starting streaming background execution of command: {cmd}")
    proc = None
    try:
        # Start the process
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        logger.info(f"Background process started with PID: {proc.pid}")

        # Register process in registry
        await process_registry.register(
            request_id=request_id,
            pid=proc.pid,
            command=cmd
        )

        # Send initial notification with PID
        initial_data = {"pid": proc.pid, "status": "started", "request_id": request_id}
        yield f"event: process_started\ndata: {json.dumps(initial_data)}\n\n"

        output_lines = []
        error_lines = []
        was_cancelled = False

        # Stream stdout
        if proc.stdout:
            async for line in proc.stdout:
                decoded_line = line.decode('utf-8')
                output_lines.append(decoded_line)
                event_data = {"content": decoded_line.rstrip()}
                yield f"event: stdout\ndata: {json.dumps(event_data)}\n\n"

        # Stream stderr
        if proc.stderr:
            async for line in proc.stderr:
                decoded_line = line.decode('utf-8')
                error_lines.append(decoded_line)
                event_data = {"content": decoded_line.rstrip()}
                yield f"event: stderr\ndata: {json.dumps(event_data)}\n\n"

        # Wait for process to complete
        await proc.wait()
        logger.info(f"Background process {proc.pid} completed with return code: {proc.returncode}")

        # Check if process was cancelled (exit code -15 is SIGTERM, -9 is SIGKILL)
        if proc.returncode in (-15, -9):
            was_cancelled = True
            logger.info(f"Process {proc.pid} was terminated by signal")

        # Update registry status
        await process_registry.update_status(
            pid=proc.pid,
            status="completed" if not was_cancelled else "terminated",
            exit_code=proc.returncode
        )

        # Unregister from registry
        await process_registry.unregister(pid=proc.pid)

        # Format as MCP tool result with content array
        output_text = "".join(output_lines)
        error_text = "".join(error_lines)

        # Combine output and error if both exist
        result_text = output_text
        if error_text:
            result_text = f"{output_text}\nSTDERR:\n{error_text}" if output_text else error_text

        if was_cancelled:
            result_text = f"[Process was terminated]\n{result_text}" if result_text else "[Process was terminated]"

        # MCP tool response format
        tool_result = {
            "content": [
                {
                    "type": "text",
                    "text": result_text if result_text else f"Command completed with return code {proc.returncode}\nPID: {proc.pid}"
                }
            ],
            "isError": (proc.returncode != 0 and not was_cancelled) or bool(error_text)
        }

        # Send final result as JSON-RPC response
        jsonrpc_response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": tool_result
        }

        logger.info(f"Sending final MCP tool result via SSE")
        yield f"event: message\ndata: {json.dumps(jsonrpc_response)}\n\n"

    except Exception as e:
        logger.error(f"Error in stream_background_command: {str(e)}")

        # Clean up registry if process was started
        if proc:
            await process_registry.unregister(pid=proc.pid)

        # Send error as MCP tool error response
        tool_error_result = {
            "content": [
                {
                    "type": "text",
                    "text": f"Error executing command: {str(e)}"
                }
            ],
            "isError": True
        }
        error_response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": tool_error_result
        }
        yield f"event: message\ndata: {json.dumps(error_response)}\n\n"


async def handle_mcp_request(request: JSONRPCRequest, session: Dict[str, Any]) -> Dict[str, Any]:
    """Handle MCP JSON-RPC request and return response"""

    method = request.method
    params = request.params or {}
    logger.info(f"Handling MCP request - method: {method}, params: {params}")

    if method == "initialize":
        # Handle initialization
        session["initialized"] = True
        session["client_info"] = params.get("clientInfo", {})

        result = {
            "protocolVersion": "2025-03-26",
            "capabilities": {
                "tools": {
                    "listChanged": False
                }
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
            },
            {
                "name": "terminate_process",
                "description": "Terminate a background process by PID (only processes started by this server)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "pid": {"type": "integer", "description": "Process ID to terminate"}
                    },
                    "required": ["pid"]
                }
            },
            {
                "name": "list_processes",
                "description": "List all running background processes started by this server",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        ]
        return {"jsonrpc": "2.0", "id": request.id, "result": {"tools": tools}}

    elif method == "tools/call":
        # This will be handled by SSE streaming
        # Return indicator that streaming is needed
        logger.info(f"Received tools/call request - will handle via streaming")
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
        logger.info(f"Received MCP request body: {body}")

        # Handle notifications/cancelled separately (notifications don't have id field)
        if body.get("method") == "notifications/cancelled":
            # Handle cancellation notification
            request_id_to_cancel = body.get("params", {}).get("requestId")
            reason = body.get("params", {}).get("reason", "Client requested cancellation")

            if request_id_to_cancel:
                logger.info(f"Received cancellation for request {request_id_to_cancel}: {reason}")
                # Terminate the process gracefully
                # Ensure request_id is int for security and type consistency
                result = await process_registry.terminate_gracefully(
                    request_id=int(request_id_to_cancel),
                    reason=reason
                )
                if result.get("success"):
                    logger.info(f"Successfully cancelled request {request_id_to_cancel}, terminated PID {result.get('pid')}")
                else:
                    logger.warning(f"Failed to cancel request {request_id_to_cancel}: {result.get('error')}")

            # Notifications don't get a response per MCP spec
            return Response(status_code=204)

        jsonrpc_request = JSONRPCRequest(**body)
    except Exception as e:
        logger.error(f"Failed to parse JSON-RPC request: {str(e)}")
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
        logger.info(f"Processing tool call request: {tool_name} in session {session_id}")

        # Check if this tool requires SSE streaming
        if tool_name == "execute_background_linux_shell_command" and not USE_DOCKER:
            # Use SSE streaming for background commands (local mode only)
            cmd = arguments.get("cmd", "")
            logger.info(f"Starting SSE stream for background command: {cmd}")

            # Return streaming response
            headers = {}
            if is_initialize:
                headers["Mcp-Session-Id"] = session_id

            return StreamingResponse(
                stream_background_command(cmd, int(jsonrpc_request.id)),
                media_type="text/event-stream",
                headers=headers
            )
        else:
            # Execute tool and return result (no streaming)
            try:
                result = await execute_mcp_tool(tool_name, arguments)
                response_data = {
                    "jsonrpc": "2.0",
                    "id": jsonrpc_request.id,
                    "result": result
                }
            except Exception as e:
                logger.error(f"Tool {tool_name} failed with error: {str(e)}")
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

    logger.info(f"Returning response: {response_data}")
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
        host=MCP_REMOTE_HOST,
        port=MCP_REMOTE_PORT,
        log_level="info"
    )
