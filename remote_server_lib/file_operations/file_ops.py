import os
import shutil
from pathlib import Path
from typing import List, Optional, Tuple
from loguru import logger
from config import get_working_dir, get_allowed_prefixes, resolve_relative_path

# Dictionary to store backups for undo functionality
# Format: {file_path: last_content}
file_backups = {}

def verify_changes(file_path) -> str:
    """Run tests or checks after making changes."""
    try:
        # For Python files, check for syntax errors
        if file_path.endswith('.py'):
            import ast
            with open(file_path, 'r') as f:
                ast.parse(f.read())
            return "Syntax check passed"
        return f"Syntax check not available for filetype: {file_path.split('.')[-1]}"
    except Exception as e:
        return f"Verification failed: {str(e)}"


def ensure_path_safety(path: str) -> str:
    """
    Ensure the path is within the allowed directory.
    Returns the normalized path or raises an exception if unsafe.
    """
    # Normalize the path
    if path.startswith("./"):
        path = resolve_relative_path(path)

    abs_path = os.path.abspath(path)
    
    # Ensure path is within the working directory or other allowed dirs
    allowed_prefixes = get_allowed_prefixes()
    if not any(abs_path.startswith(prefix) for prefix in allowed_prefixes):
        raise ValueError(f"Path '{path}' is outside of allowed directories")
    
    return abs_path

def create_backup(path: str) -> None:
    """Create a backup of a file before modifying it"""
    try:
        abs_path = ensure_path_safety(path)
        if os.path.exists(abs_path) and os.path.isfile(abs_path):
            with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
                file_backups[abs_path] = f.read()
    except Exception as e:
        logger.error(f"Failed to create backup of {path}: {str(e)}")
        raise

def view_file(path: str, view_range: Optional[List[int]] = None) -> str:
    """View the contents of a file, optionally within a specified line range"""
    try:
        abs_path = ensure_path_safety(path)
        
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"File not found: {path}")
        
        if os.path.isdir(abs_path):
            # List directory contents
            return "\n".join(sorted(os.listdir(abs_path)))
        
        # Read file content
        with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.readlines()
        
        # Apply line range if specified
        if view_range and len(view_range) == 2:
            start_line, end_line = view_range
            # Adjust for 0-based indexing
            start_idx = max(0, start_line - 1)
            end_idx = min(len(content), end_line)
            content = content[start_idx:end_idx]
        
        return ''.join(content)
    
    except Exception as e:
        logger.error(f"Error viewing file {path}: {str(e)}")
        raise

def create_file(path: str, file_text: str) -> bool:
    """Create a new file with the specified content"""
    try:
        abs_path = ensure_path_safety(path)
        
        # Create parent directories if they don't exist
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        
        # Check if file already exists
        if os.path.exists(abs_path):
            # Create backup before overwriting
            create_backup(abs_path)
        
        # Write to file
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(file_text)
        
        return True
    
    except Exception as e:
        logger.error(f"Error creating file {path}: {str(e)}")
        raise

def string_replace(path: str, old_str: str, new_str: str) -> Tuple[bool, str]:
    """Replace single occurrences of old_str with new_str in the file"""
    try:
        abs_path = ensure_path_safety(path)
        
        if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
            raise FileNotFoundError(f"File not found: {path}")
        
        # Create backup before modifying
        create_backup(abs_path)
        
        # Read file content
        with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        if content.count(old_str) == 0:
            return False, "Error: no match found"
        if content.count(old_str) > 1:
            return False, f"Error: Found {count} matches"
        
        # Perform replacement
        if old_str not in content:
            return False, f"String '{old_str}' not found in {path}"
        
        modified_content = content.replace(old_str, new_str)
        
        # Write modified content back to file
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(modified_content)
        
        return True, "Successfully replaced text"
    
    except Exception as e:
        logger.error(f"Error replacing string in file {path}: {str(e)}")
        raise

def insert_at_line(path: str, insert_line: int, new_str: str) -> Tuple[bool, str]:
    """Insert text at a specific line in the file"""
    try:
        abs_path = ensure_path_safety(path)
        
        if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
            raise FileNotFoundError(f"File not found: {path}")
        
        # Create backup before modifying
        create_backup(abs_path)
        
        # Read file content
        with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.readlines()
        
        # Ensure insert_line is valid
        if insert_line < 1:
            insert_line = 1
        elif insert_line > len(content) + 1:
            insert_line = len(content) + 1
        
        # Adjust for 0-based indexing
        insert_idx = insert_line - 1
        
        # Ensure new_str ends with a newline if not at the end of file
        if insert_idx < len(content) and not new_str.endswith('\n'):
            new_str += '\n'
        
        # Insert the new string
        content.insert(insert_idx, new_str)
        
        # Write modified content back to file
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.writelines(content)
        
        return True, f"Inserted text at line {insert_line} in {path}"
    
    except Exception as e:
        logger.error(f"Error inserting at line in file {path}: {str(e)}")
        raise

def undo_edit(path: str) -> Tuple[bool, str]:
    """Revert the last edit made to a file"""
    try:
        abs_path = ensure_path_safety(path)
        
        if abs_path not in file_backups:
            return False, f"No backup found for {path}"
        
        # Restore from backup
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(file_backups[abs_path])
        
        # Remove the backup after restoring
        del file_backups[abs_path]
        
        return True, f"Reverted last edit to {path}"
    
    except Exception as e:
        logger.error(f"Error undoing edit for file {path}: {str(e)}")
        raise
