import os
import mimetypes
from pathlib import Path
from typing import Callable

def display_file_contents(
    dir_path: str, 
    file_ext: list[str] = None, 
    skip_dirs: list[str] | int = None,
    skip_ext: list[str] = None,
) -> str:
    """
    Recursively search a directory and display content for matching files.
    
    Args:
        dir_path: Path to the directory to search
        file_ext: List of file extensions to include (without the dot)
        skip_dirs: List of directory names to skip (default: ['.git', 'node_modules'])
        skip_ext: List of file extensions to skip (default: ['.pyc', '.so'])
        output_format: Optional callable to format the output for each file
        
    Returns:
        A string containing the formatted content of all matching files
    """
    output_format = lambda path, content: f"\n// {path}\n{content}\n"

    # set default values if not provided
    if file_ext is None: 
        file_ext  = []
    if skip_dirs is None or skip_dirs == 0: 
        skip_dirs = ['.git', 'node_modules']
    if skip_ext is None:
        skip_ext = ['.pyc', '.so']

    # Ensure extensions have dots
    #file_ext = [f".{ext.lstrip('.')}" for ext in file_ext]
    #skip_ext = [f".{ext.lstrip('.')}" for ext in skip_ext]
    
    result = []
    
    for root, dirs, files in os.walk(dir_path):
        # Skip directories in skip_dirs
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        
        for file in files:
            file_path = os.path.join(root, file)
            _, ext = os.path.splitext(file_path)
            
            # Skip files with extensions in skip_ext
            if ext in skip_ext:
                continue
                
            # Only include files with extensions in file_ext if it's not empty
            if file_ext and len(file_ext) > 0 and ext not in file_ext:
                continue
            
            # Skip binary files
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type and not mime_type.startswith('text/'):
                # Additional check to handle common text files with different mime types
                if not any(file_path.endswith(text_ext) for text_ext in 
                          ['.md', '.txt', '.py', '.js', '.html', '.css', '.json', '.xml', '.yml', '.yaml']):
                    continue
            
            try:
                # Try to read the file as text
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    result.append(output_format(file_path, content))
            except (UnicodeDecodeError, IsADirectoryError):
                # Skip binary files that weren't caught by the mime type check
                continue
            except Exception as e:
                result.append(output_format(file_path, f"Error reading file: {str(e)}"))
    
    return "".join(result)


if __name__ == "__main__":
    print(display_file_contents("."))