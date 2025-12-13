# MCP Process Management Implementation

## Overview

Comprehensive process management system for MCP remote server with support for:
- ✅ SSE streaming for background commands
- ✅ Process registry tracking (request_id ↔ PID mapping)
- ✅ MCP standard `notifications/cancelled`
- ✅ Graceful termination (SIGTERM → wait → SIGKILL)
- ✅ `terminate_process` MCP tool
- ✅ `list_processes` MCP tool
- ✅ Docker mode support

## Architecture

### Process Registry

**File**: `remote_server_lib/process_registry.py`

The `ProcessRegistry` class maintains bidirectional mappings between MCP request IDs and process IDs:

```python
class ProcessRegistry:
    - register(request_id, pid, command) → ProcessInfo
    - unregister(request_id/pid) → ProcessInfo
    - get_by_request_id(request_id) → ProcessInfo
    - get_by_pid(pid) → ProcessInfo
    - list_all() → List[ProcessInfo]
    - terminate_gracefully(request_id/pid, reason) → Dict
```

**Graceful Termination Flow**:
1. Send SIGTERM to process
2. Wait up to 30 seconds (configurable via `TERMINATION_TIMEOUT`)
3. If still running, send SIGKILL
4. Update registry and clean up

### Local Mode vs Docker Mode

**Local Mode** (`USE_DOCKER=False`):
- Process registry runs in `mcp_remote_server.py`
- Direct process management via OS signals
- SSE streaming supported

**Docker Mode** (`USE_DOCKER=True`):
- Process registry runs in backend (`remote_server_lib/api/async_process.py`)
- Remote MCP server proxies to backend APIs
- SSE streaming not yet supported (falls back to executor)

## New MCP Tools

### 1. `terminate_process`

Terminate a background process by PID (only processes started by this server).

**Input Schema**:
```json
{
  "pid": 12345
}
```

**Response**:
```
Process 12345 terminated successfully
Request ID: 550e8400-e29b-41d4-a716-446655440000
Signal: SIGTERM
Reason: Manual termination via terminate_process tool
```

### 2. `list_processes`

List all running background processes started by this server.

**Input Schema**:
```json
{}
```

**Response**:
```
Background Processes (2):

PID: 12345
  Request ID: 550e8400-e29b-41d4-a716-446655440000
  Command: sleep 60
  Status: running
  Started: 2025-12-13 10:30:15

PID: 12346
  Request ID: 6ba7b810-9dad-11d1-80b4-00c04fd430c8
  Command: long-running-task.sh
  Status: running
  Started: 2025-12-13 10:31:20
```

## MCP Standard: notifications/cancelled

Implements MCP protocol standard for cancelling in-progress requests.

**Client sends**:
```json
{
  "jsonrpc": "2.0",
  "method": "notifications/cancelled",
  "params": {
    "requestId": "3",
    "reason": "User cancelled operation"
  }
}
```

**Server behavior**:
1. Looks up PID by request ID in registry
2. Terminates process gracefully (SIGTERM → SIGKILL)
3. Returns HTTP 204 (no content) per MCP spec
4. Streaming response for original request will show termination

## SSE Streaming Enhancements

### Background Command Streaming

When `execute_background_linux_shell_command` is called (local mode):

**1. Process Started Event**:
```
event: process_started
data: {"pid": 12345, "status": "started", "request_id": "3"}
```

**2. Stdout Events** (real-time):
```
event: stdout
data: {"content": "Processing line 1..."}

event: stdout
data: {"content": "Processing line 2..."}
```

**3. Stderr Events** (real-time):
```
event: stderr
data: {"content": "Warning: deprecated feature"}
```

**4. Final MCP Tool Result**:
```
event: message
data: {
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Processing line 1...\nProcessing line 2...\n\nSTDERR:\nWarning: deprecated feature"
      }
    ],
    "isError": false
  }
}
```

## Configuration

### Environment Variables

```bash
# Termination timeout (seconds to wait before SIGKILL)
TERMINATION_TIMEOUT=30  # Default: 30

# Docker mode toggle
USE_DOCKER=False  # True for Docker backend, False for local

# MCP server ports
MCP_REMOTE_PORT=8888  # Remote MCP server
MCP_PORT=8181         # Backend API (Docker mode)
```

## Backend API Endpoints (Docker Mode)

### POST `/api/async/process/terminate_by_pid/`

Terminate process by PID.

**Request**:
```
POST /api/async/process/terminate_by_pid/?pid=12345
```

**Response**:
```json
{
  "success": true,
  "pid": 12345,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "signal": "SIGTERM",
  "message": "Process terminated with SIGTERM"
}
```

### GET `/api/async/processes/list/`

List all tracked processes.

**Response**:
```json
{
  "processes": [
    {
      "pid": 12345,
      "request_id": "550e8400-e29b-41d4-a716-446655440000",
      "command": "sleep 60",
      "status": "running",
      "started_at": "2025-12-13T10:30:15.123456",
      "exit_code": null,
      "terminated_at": null,
      "termination_signal": null
    }
  ],
  "count": 1
}
```

## Testing

### Quick Test

```bash
# Terminal 1: Start server (local mode)
USE_DOCKER=False MCP_REMOTE_PORT=8888 python mcp_remote_server.py

# Terminal 2: Run comprehensive test
python test_process_management.py
```

### Manual Testing

```bash
# 1. Start a background process
curl -X POST http://localhost:8888/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -H "Mcp-Session-Id: YOUR_SESSION_ID" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "execute_background_linux_shell_command",
      "arguments": {"cmd": "sleep 60"}
    }
  }'

# 2. List processes
curl -X POST http://localhost:8888/mcp \
  -H "Content-Type: application/json" \
  -H "Mcp-Session-Id: YOUR_SESSION_ID" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "list_processes",
      "arguments": {}
    }
  }'

# 3. Cancel via notifications/cancelled
curl -X POST http://localhost:8888/mcp \
  -H "Content-Type: application/json" \
  -H "Mcp-Session-Id: YOUR_SESSION_ID" \
  -d '{
    "jsonrpc": "2.0",
    "method": "notifications/cancelled",
    "params": {
      "requestId": "1",
      "reason": "User requested"
    }
  }'

# 4. Or terminate by PID
curl -X POST http://localhost:8888/mcp \
  -H "Content-Type: application/json" \
  -H "Mcp-Session-Id: YOUR_SESSION_ID" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "terminate_process",
      "arguments": {"pid": 12345}
    }
  }'
```

## Files Modified/Created

### New Files
- `remote_server_lib/process_registry.py` - Process registry implementation
- `test_process_management.py` - Comprehensive test suite
- `PROCESS_MANAGEMENT.md` - This documentation

### Modified Files
- `mcp_remote_server.py`:
  - Added process registry initialization
  - Updated `stream_background_command()` to register/unregister processes
  - Added `notifications/cancelled` handler
  - Implemented `terminate_process` and `list_processes` tools
  - Added Docker mode support for new tools

- `remote_server_lib/api/async_process.py`:
  - Added process registry to backend
  - Updated `run_command()` to register processes
  - Added `/api/async/process/terminate_by_pid/` endpoint
  - Added `/api/async/processes/list/` endpoint

## Security Considerations

1. **Process Isolation**: Only processes started by this MCP server can be terminated
2. **PID Validation**: PIDs are validated against the registry before termination
3. **Session-based**: All operations require valid MCP session
4. **API Key**: Optional API key authentication (set `MCP_API_KEY`)
5. **Origin Validation**: CORS restricted to localhost

## Future Enhancements

- [ ] Docker mode SSE streaming support
- [ ] Process output capture history
- [ ] Process timeout configuration per-command
- [ ] Process grouping/tagging
- [ ] Metrics and monitoring
- [ ] Persistent registry (survive server restarts)
