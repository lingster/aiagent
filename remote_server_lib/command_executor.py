"""
Shared command execution module for MCP servers.

This module provides unified command and file operation execution
that supports both local execution and remote HTTP-based execution
(for Docker scenarios).
"""

import os
import subprocess
import asyncio
import json
from typing import Optional, List, Dict, Any
import httpx
import anyio
from loguru import logger

from remote_server_lib.core import CommandRequest


class CommandExecutor:
    """
    Handles command and file operation execution with support for both
    local execution and remote HTTP-based execution.
    """

    def __init__(
        self,
        use_docker: bool = None,
        mcp_port: str = None,
        execute_url: str = None,
        async_url: str = None,
        file_operations_base_url: str = None
    ):
        """
        Initialize the command executor.

        Args:
            use_docker: Whether to use Docker/HTTP execution. If None, reads from env.
            mcp_port: MCP port. If None, reads from env.
            execute_url: URL for sync command execution. If None, constructed from port.
            async_url: URL for async command execution. If None, constructed from port.
            file_operations_base_url: Base URL for file operations. If None, constructed from port.
        """
        self.use_docker = use_docker if use_docker is not None else (
            os.environ.get("USE_DOCKER", "True") == "True"
        )
        self.mcp_port = mcp_port or os.environ.get("MCP_PORT", "8181")

        self.execute_url = execute_url or f"http://localhost:{self.mcp_port}/api/sync/execute/"
        self.async_url = async_url or f"http://localhost:{self.mcp_port}/api/async/execute/background/"
        self.file_operations_base_url = file_operations_base_url or f"http://localhost:{self.mcp_port}/api/files/"

    async def execute_linux_shell_command(self, cmd: str) -> dict:
        """
        Execute a Linux shell command synchronously.

        Args:
            cmd: The command to execute

        Returns:
            Dict with command, output, error, return_code, and pid
        """
        try:
            if self.use_docker:
                logger.info(f"running {cmd[0:30]}... on PORT={self.mcp_port}")
                req = CommandRequest(command=cmd)
                httpx_timeout = httpx.Timeout(60)
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self.execute_url,
                        data=req.model_dump_json(),
                        timeout=httpx_timeout
                    )
                response.raise_for_status()
                if response.status_code == 200:
                    return response.json()
                else:
                    return {"error": f"failed to run linux command: {response.json().get('error')}"}
            else:
                process = await anyio.run_process(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False
                )
                return {
                    "command": cmd,
                    "output": process.stdout.decode() if process.stdout else "",
                    "error": process.stderr.decode() if process.stderr else "",
                    "return_code": process.returncode,
                }
        except Exception as ex:
            logger.error(f"failed to execute command: {cmd=}: {str(ex)}")
            return {"error": f"failed to run linux command: {str(ex)}"}

    async def execute_background_linux_shell_command(self, cmd: str) -> dict:
        """
        Execute a Linux shell command asynchronously in the background.

        Args:
            cmd: The command to execute

        Returns:
            Dict with pid or task_id and message
        """
        try:
            if self.use_docker:
                req = CommandRequest(command=cmd)
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self.async_url,
                        data=req.model_dump_json()
                    )
                    response.raise_for_status()
                    if response.status_code == 200:
                        return response.json()
                    else:
                        return {"error": f"failed to run async linux command: {response.json().get('error')}"}
            else:
                # For background tasks, we can't use anyio.run_process as it waits for completion
                # Instead, we should start a subprocess in the background
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                return {"pid": proc.pid}
        except Exception as ex:
            logger.error(f"failed to execute async command: {cmd=}: {str(ex)}")
            return {"error": f"failed to run async linux command: {str(ex)}"}

    async def view_file(self, path: str, view_range: Optional[List[int]] = None) -> dict:
        """
        View the contents of a file or directory.

        Args:
            path: The path to the file or directory to view
            view_range: Optional list of [start_line, end_line] to view only a portion

        Returns:
            Dict with success, content/error, and message
        """
        try:
            payload = {
                "command": "view",
                "path": path,
                "view_range": json.dumps(view_range)
            }
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.file_operations_base_url}operation/",
                    json=payload
                )
                if response.status_code == 200:
                    result = response.json()
                    if result.get("success", False):
                        return {
                            "success": True,
                            "content": result.get("content", ""),
                            "message": result.get("message", "")
                        }
                    else:
                        return {
                            "success": False,
                            "error": result.get("message", "Unknown error")
                        }
                else:
                    return {
                        "success": False,
                        "error": f"Request failed with status code {response.status_code}"
                    }
        except Exception as ex:
            logger.error(f"Failed to view file {path}: {str(ex)}")
            return {"success": False, "error": str(ex)}

    async def create_a_file(self, path: str, file_text: str) -> dict:
        """
        Create a new file with the specified content.

        Args:
            path: The path where the file should be created
            file_text: The content to write to the file

        Returns:
            Dict with success and message/error
        """
        try:
            payload = {
                "command": "create",
                "path": path,
                "file_text": json.dumps(file_text),
            }
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.file_operations_base_url}operation/",
                    json=payload
                )
                if response.status_code == 200:
                    result = response.json()
                    return {
                        "success": result.get("success", False),
                        "message": result.get("message", "")
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Request failed with status code {response.status_code}"
                    }
        except Exception as ex:
            logger.error(f"Failed to create file {path}: {str(ex)}")
            return {"success": False, "error": str(ex)}

    async def string_replace(self, path: str, old_str: str, new_str: str) -> dict:
        """
        Replace text in a file.

        Args:
            path: The path to the file to modify
            old_str: The string to be replaced
            new_str: The string to replace with

        Returns:
            Dict with success and message/error
        """
        try:
            payload = {
                "command": "str_replace",
                "path": path,
                "old_str": json.dumps(old_str),
                "new_str": json.dumps(new_str)
            }
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.file_operations_base_url}operation/",
                    json=payload
                )
                if response.status_code == 200:
                    result = response.json()
                    return {
                        "success": result.get("success", False),
                        "message": result.get("message", "")
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Request failed with status code {response.status_code}"
                    }
        except Exception as ex:
            logger.error(f"Failed to replace string in file {path}: {str(ex)}")
            return {"success": False, "error": str(ex)}

    async def insert_at(self, path: str, insert_line: int, new_str: str) -> dict:
        """
        Insert text at a specific line in a file.

        Args:
            path: The path to the file to modify
            insert_line: The line number where the text should be inserted
            new_str: The string to insert

        Returns:
            Dict with success and message/error
        """
        try:
            payload = {
                "command": "insert",
                "path": path,
                "insert_line": json.dumps(insert_line),
                "new_str": json.dumps(new_str)
            }
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.file_operations_base_url}operation/",
                    json=payload
                )
                if response.status_code == 200:
                    result = response.json()
                    return {
                        "success": result.get("success", False),
                        "message": result.get("message", "")
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Request failed with status code {response.status_code}"
                    }
        except Exception as ex:
            logger.error(f"Failed to insert at line in file {path}: {str(ex)}")
            return {"success": False, "error": str(ex)}

    async def undo_file_edit(self, path: str) -> dict:
        """
        Revert the last edit made to a file.

        Args:
            path: The path to the file to revert

        Returns:
            Dict with success and message/error
        """
        try:
            payload = {
                "command": "undo_edit",
                "path": path
            }
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.file_operations_base_url}operation/",
                    json=payload
                )
                if response.status_code == 200:
                    result = response.json()
                    return {
                        "success": result.get("success", False),
                        "message": result.get("message", "")
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Request failed with status code {response.status_code}"
                    }
        except Exception as ex:
            logger.error(f"Failed to undo edit for file {path}: {str(ex)}")
            return {"success": False, "error": str(ex)}


# Create a default global executor instance for convenience
_default_executor = None

def get_default_executor() -> CommandExecutor:
    """Get or create the default command executor instance."""
    global _default_executor
    if _default_executor is None:
        _default_executor = CommandExecutor()
    return _default_executor
