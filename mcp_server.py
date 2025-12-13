import os
import sys
import subprocess
from loguru import logger
from mcp.server.fastmcp import FastMCP
import httpx
import anyio
import json
from typing import Optional, List

# Configure advanced error handling for loguru
logger.configure(handlers=[
    {"sink": sys.stderr, "level": "ERROR", "backtrace": True, "diagnose": True}
])

mcp = FastMCP("Automate", dependences=["loguru", "httpx"])

from loguru import logger
from remote_server_lib.core import CommandRequest
from skills_manager import SkillsManager

# Create an MCP server

PORT = os.environ.get("MCP_PORT", "8181")
USE_DOCKER = os.environ.get("USE_DOCKER", "True") == "True"
execute_url = os.environ.get("mcp_sync", f"http://localhost:{PORT}/api/sync/execute/")
async_url = os.environ.get("mcp_async", f"http://localhost:{PORT}/api/async/execute/background/")
file_operations_base_url = os.environ.get("str_replace", f"http://localhost:{PORT}/api/files/")

logger.remove()
logger.add(sys.stderr, format="{time} {level} {message}", level="INFO")

# Initialize skills manager
SKILLS_DIR = os.environ.get("SKILLS_DIR", "./skills")
skills_manager = SkillsManager(SKILLS_DIR)
logger.info(f"Initialized skills manager with {len(skills_manager.skills_cache)} skills")

@mcp.tool()
async def execute_linux_shell_command(cmd: str) -> dict:
    """Execute a Linux shell command synchronously. This will only return when the shell command completed.
    Therefore do not use this tool if you are starting a long running task, such as a web server.
    The linux shell also includes the following tools:
      - tree-sitter which can be used to index and search code.
    """
    try:
        if USE_DOCKER:
            logger.info(f"running {cmd[0:30]}... on {PORT=}")
            req = CommandRequest(command=cmd)
            httpx_timeout = httpx.Timeout(60)
            async with httpx.AsyncClient() as client:
                response = await client.post(execute_url, data=req.model_dump_json(), timeout=httpx_timeout)
            response.raise_for_status()
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"failed to run linux command: {response.json().get('error')}"}
        else:
            process = await anyio.run_process(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            return {
                "command": cmd,
                "output": process.stdout.decode() if process.stdout else "",
                "error": process.stderr.decode() if process.stderr else "",
                "return_code": process.returncode,
                "pid": process.pid,

            }
    except Exception as ex:
        logger.error(f"failed to execute command: {cmd=}: {str(ex)}")
        return {"error": f"failed to run linux command: {str(ex)}"}

@mcp.tool()
async def execute_background_linux_shell_command(cmd: str) -> dict:
    """Execute a Linux shell command asynchronously in the background.
    This is useful to start web servers. Will return process id.
    """
    try:
        if USE_DOCKER:
            req = CommandRequest(command=cmd)
            async with httpx.AsyncClient() as client:
                response = await client.post(async_url, data=req.model_dump_json())
                response.raise_for_status()
                if response.status_code == 200:
                    return response.json()
                else:
                    return {"error": f"failed to run async linux command: {response.json().get('error')}"}
        else:
            # For background tasks, we can't use anyio.run_process as it waits for completion
            # Instead, we should start a subprocess in the background
            import asyncio
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            return {"pid": proc.pid}
    except Exception as ex:
        logger.error(f"failed to execute async command: {cmd=}: {str(ex)}")
        return {"error": f"failed to run async linux command: {str(ex)}"}

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
    try:
        payload = {
            "command": "view",
            "path": path,
            "view_range": json.dumps(view_range)
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{file_operations_base_url}operation/", json=payload)
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
    try:
        payload = {
            "command": "create",
            "path": path,
            "file_text": json.dumps(file_text),
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{file_operations_base_url}operation/", json=payload)
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
    try:
        payload = {
            "command": "str_replace",
            "path": path,
            "old_str": json.dumps(old_str),
            "new_str": json.dumps(new_str)
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{file_operations_base_url}operation/", json=payload)
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
    try:
        payload = {
            "command": "insert",
            "path": path,
            "insert_line": json.dumps(insert_line),
            "new_str": json.dumps(new_str)
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{file_operations_base_url}operation/", json=payload)
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

@mcp.tool()
async def undo_file_edit(path: str) -> dict:
    """
    Revert the last edit made to a file.

    Args:
        path: The path to the file to revert

    Returns:
        A dictionary indicating success or failure and a message
    """
    try:
        payload = {
            "command": "undo_edit",
            "path": path
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{file_operations_base_url}operation/", json=payload)
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

# Skills Management Tools

@mcp.tool()
async def list_skills() -> dict:
    """
    List all available skills with their names and summaries.

    Returns:
        A dictionary containing a list of skills with name and summary
    """
    try:
        skills = skills_manager.list_skills()
        return {
            "success": True,
            "skills": skills,
            "count": len(skills)
        }
    except Exception as ex:
        logger.error(f"Failed to list skills: {str(ex)}")
        return {"success": False, "error": str(ex)}

@mcp.tool()
async def get_skill(name: str) -> dict:
    """
    Get the full description and details of a specific skill by name.

    Args:
        name: The name of the skill to retrieve

    Returns:
        A dictionary with the skill's full details or error if not found
    """
    try:
        skill = skills_manager.get_skill(name)
        if skill:
            return {
                "success": True,
                "skill": skill
            }
        else:
            return {
                "success": False,
                "error": f"Skill '{name}' not found",
                "available_skills": list(skills_manager.skills_cache.keys())
            }
    except Exception as ex:
        logger.error(f"Failed to get skill {name}: {str(ex)}")
        return {"success": False, "error": str(ex)}

@mcp.tool()
async def use_skill(skill_name: str, command: str) -> dict:
    """
    Execute a command in the context of a skill.

    This copies the skill files to a temporary directory and executes the command there,
    preventing any modifications to the original skill files.

    Args:
        skill_name: The name of the skill to use
        command: The command to execute (e.g., "python script.py arg1 arg2")

    Returns:
        A dictionary with the command execution results including output, error, and return code
    """
    try:
        result = await skills_manager.use_skill(skill_name, command, execute_url)
        return result
    except Exception as ex:
        logger.error(f"Failed to use skill {skill_name}: {str(ex)}")
        return {"success": False, "error": str(ex)}

@mcp.tool()
async def refresh_skills_cache() -> dict:
    """
    Refresh the skills cache by reloading all skills from disk.

    This is useful when new skills are added or existing skills are modified
    without restarting the MCP server.

    Returns:
        A dictionary indicating success and the number of skills loaded
    """
    try:
        result = skills_manager.refresh_skills()
        return result
    except Exception as ex:
        logger.error(f"Failed to refresh skills cache: {str(ex)}")
        return {"success": False, "error": str(ex)}

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
