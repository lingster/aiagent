"""
Configuration settings for aiagents server.
"""
import os

# Working directory for aiagents operations
WORKING_DIR = os.environ.get("AIAGENTS_WORKING_DIR", "/data")

def get_working_dir() -> str:
    """Get the configured working directory."""
    return WORKING_DIR

def get_allowed_prefixes() -> list[str]:
    """Get the list of allowed path prefixes for security validation."""
    return [WORKING_DIR]

def resolve_relative_path(path: str) -> str:
    """Resolve relative paths to be within the working directory."""
    if path.startswith("./"):
        return path.replace("./", f"{WORKING_DIR}/")
    return path
