# MCP Server Tests

This directory contains comprehensive unit tests for the MCP server functions in `mcp_server.py`.

## Test Coverage

The test suite covers all functions in mcp_server.py:

### Command Execution Functions
- `execute_linux_shell_command` - Tests for both Docker and non-Docker modes
- `execute_background_linux_shell_command` - Tests for both Docker and non-Docker modes

### File Operation Functions
- `view_file` - View file contents with optional line ranges
- `create_a_file` - Create new files
- `string_replace` - Replace text in files
- `insert_at` - Insert text at specific line numbers
- `undo_file_edit` - Undo file edits

## Test Scenarios

Each function is tested with:
- **Success scenarios** - Happy path operations
- **Error scenarios** - HTTP errors, network failures, timeouts
- **Exception handling** - Various exception types
- **JSON validation** - All payloads are validated to ensure valid JSON
- **Both modes** - Docker mode (USE_DOCKER=True) and non-Docker mode (USE_DOCKER=False)

## Running Tests

### Install Test Dependencies

Using uv (recommended):
```bash
uv sync --extra dev
```

Or using pip:
```bash
pip install -e ".[dev]"
```

### Run All Tests

```bash
# Using uv
uv run pytest

# Or directly with pytest
pytest

# With verbose output
uv run pytest -v

# With coverage report
uv run pytest --cov=mcp_server --cov-report=html
```

### Run Specific Test Classes

```bash
# Test only command execution
uv run pytest tests/test_mcp_server.py::TestExecuteLinuxShellCommand

# Test only file operations
uv run pytest tests/test_mcp_server.py::TestViewFile
```

### Run Specific Test Methods

```bash
# Test Docker mode success
uv run pytest tests/test_mcp_server.py::TestExecuteLinuxShellCommand::test_docker_mode_success

# Test error scenarios
uv run pytest tests/test_mcp_server.py -k "error"
```

## Test Structure

### Fixtures

- `env_docker_enabled` - Sets USE_DOCKER=True and related environment variables
- `env_docker_disabled` - Sets USE_DOCKER=False
- `mock_httpx_success` - Mocks successful HTTP responses
- `mock_httpx_error` - Mocks HTTP error responses
- `mock_anyio_process` - Mocks anyio process execution

### Test Classes

- `TestExecuteLinuxShellCommand` - 6 tests
- `TestExecuteBackgroundLinuxShellCommand` - 5 tests
- `TestViewFile` - 5 tests
- `TestCreateFile` - 4 tests
- `TestStringReplace` - 4 tests
- `TestInsertAt` - 4 tests
- `TestUndoFileEdit` - 4 tests

**Total: 32 comprehensive test cases**

## JSON Validation

All tests validate that:
1. Data sent in HTTP requests is valid JSON
2. JSON structure matches expected format
3. Values can be properly deserialized

## Mocking Strategy

- **HTTP calls**: Mocked using `unittest.mock.patch` on `httpx.AsyncClient`
- **Process execution**: Mocked using `unittest.mock.patch` on `anyio.run_process`
- **Environment variables**: Controlled using pytest's `monkeypatch` fixture

## CI/CD Integration

These tests are designed to run in CI/CD pipelines. They:
- Don't require external services
- Run entirely with mocks
- Are fast and deterministic
- Provide clear failure messages
