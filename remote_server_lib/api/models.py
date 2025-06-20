from pydantic import BaseModel
from typing import Optional, List, Union, Tuple
from config import get_working_dir


# Define a request model for input validation
class CommandRequest(BaseModel):
    command: str

class SourceCodeRequest(BaseModel):
    dir_path: str = get_working_dir()
    file_ext: list[str] | None = None, 
    skip_dirs: list[str|int] | int | None = None,
    skip_ext: list[str] | None = None  

# File operation models
class ViewFileRequest(BaseModel):
    path: str
    view_range: Optional[list[int]] = None  # [start_line, end_line]

class CreateFileRequest(BaseModel):
    path: str
    file_text: str

class StringReplaceRequest(BaseModel):
    path: str
    old_str: str
    new_str: str

class InsertRequest(BaseModel):
    path: str
    insert_line: int
    new_str: str

class UndoEditRequest(BaseModel):
    path: str

class FileOperationResponse(BaseModel):
    success: bool
    message: str
    content: Optional[str] = None
