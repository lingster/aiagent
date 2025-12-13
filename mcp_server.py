import os
import sys
from loguru import logger
from mcp.server.fastmcp import FastMCP
from typing import Optional, List

# Configure advanced error handling for loguru
logger.configure(handlers=[
    {"sink": sys.stderr, "level": "ERROR", "backtrace": True, "diagnose": True}
])

mcp = FastMCP("Automate", dependences=["loguru", "httpx"])

from remote_server_lib.command_executor import CommandExecutor

# Create an MCP server

PORT = os.environ.get("MCP_PORT", "8181")
USE_DOCKER = os.environ.get("USE_DOCKER", "True") == "True"

# Initialize the command executor
executor = CommandExecutor(
    use_docker=USE_DOCKER,
    mcp_port=PORT
)

logger.remove()
logger.add(sys.stderr, format="{time} {level} {message}", level="INFO")

@mcp.tool()
async def execute_linux_shell_command(cmd: str) -> dict:
    """Execute a Linux shell command synchronously. This will only return when the shell command completed.
    Therefore do not use this tool if you are starting a long running task, such as a web server.
    The linux shell also includes the following tools:
      - tree-sitter which can be used to index and search code.
    """
    return await executor.execute_linux_shell_command(cmd)

@mcp.tool()
async def execute_background_linux_shell_command(cmd: str) -> dict:
    """Execute a Linux shell command asynchronously in the background.
    This is useful to start web servers. Will return process id.
    """
    return await executor.execute_background_linux_shell_command(cmd)

# File Operation Tools

@mcp.tool()
async def view_file(path: str, view_range: Optional[List[int]] = None) -> dict:
    """
    View the contents of a file or directory.

    Args:
        path: The path to the file or directory to view
        view_range: Optional list of [start_line, end_line] to view only a portion of the file

    Returns:
        A dictionary with the file content or error message
    """
    return await executor.view_file(path, view_range)

@mcp.tool()
async def create_a_file(path: str, file_text: str) -> dict:
    """
    Create a new file with the specified content.

    Args:
        path: The path where the file should be created
        file_text: The content to write to the file

    Returns:
        A dictionary indicating success or failure
    """
    return await executor.create_a_file(path, file_text)

@mcp.tool()
async def string_replace(path: str, old_str: str, new_str: str) -> dict:
    """
    Replace text in a file.

    Args:
        path: The path to the file to modify
        old_str: The string to be replaced
        new_str: The string to replace with

    Returns:
        A dictionary indicating success or failure and a message
    """
    return await executor.string_replace(path, old_str, new_str)

@mcp.tool()
async def insert_at(path: str, insert_line: int, new_str: str) -> dict:
    """
    Insert text at a specific line in a file.

    Args:
        path: The path to the file to modify
        insert_line: The line number where the text should be inserted
        new_str: The string to insert

    Returns:
        A dictionary indicating success or failure and a message
    """
    return await executor.insert_at(path, insert_line, new_str)

@mcp.tool()
async def undo_file_edit(path: str) -> dict:
    """
    Revert the last edit made to a file.

    Args:
        path: The path to the file to revert

    Returns:
        A dictionary indicating success or failure and a message
    """
    return await executor.undo_file_edit(path)

if __name__ == "__main__":
    try:
        # Set specific MCP options that help with task group handling
        mcp_options = {
            #"debug": True,  # Enable handling of cancellation notifications
            #"log_level": "DEBUG",                # Increase timeout if needed
        }
        mcp.run(transport='stdio', **mcp_options)
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as ex:
        logger.exception(f"mcp_server error: {ex}")
        sys.exit(1)
