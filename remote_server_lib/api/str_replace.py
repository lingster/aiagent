import json
from fastapi import HTTPException, APIRouter
from loguru import logger

from remote_server_lib.api.models import (
    ViewFileRequest, CreateFileRequest, StringReplaceRequest, 
    InsertRequest, UndoEditRequest, FileOperationResponse
)
from remote_server_lib.file_operations.file_ops import (
    view_file, create_file, string_replace, 
    insert_at_line, undo_edit
)
from remote_server_lib.execution_timing import log_execution_time

router = APIRouter(prefix="/api/files", tags=["files"])

@router.post("/view/", response_model=FileOperationResponse)
@log_execution_time
async def api_view_file(request: ViewFileRequest) -> FileOperationResponse:
    """View the contents of a file, optionally within a specified line range"""
    try:
        content = view_file(request.path, request.view_range)
        return FileOperationResponse(
            success=True,
            message=f"Successfully viewed {request.path}",
            content=content
        )
    except FileNotFoundError as e:
        logger.error(f"File not found: {str(e)}")
        return FileOperationResponse(
            success=False,
            message="Requested file does not exist",
            content="Requested file does not exist",
        )
    except Exception as e:
        logger.error(f"Error viewing file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error viewing file: {str(e)}")

@router.post("/create/", response_model=FileOperationResponse)
@log_execution_time
async def api_create_file(request: CreateFileRequest) -> FileOperationResponse:
    """Create a new file with the specified content"""
    try:
        result = create_file(request.path, request.file_text)
        logger.info(f"Successfully created {request.path}")
        return FileOperationResponse(
            success=result,
            message=f"Successfully created {request.path}"
        )
    except Exception as e:
        logger.error(f"Error creating file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating file: {str(e)}")

@router.post("/str_replace/", response_model=FileOperationResponse)
@log_execution_time
async def api_string_replace(request: StringReplaceRequest) -> FileOperationResponse:
    """Replace text in a file"""
    try:
        success, message = string_replace(request.path, request.old_str, request.new_str)
        logger.info(f"{message}")
        return FileOperationResponse(
            success=success,
            message=message
        )
    except FileNotFoundError as e:
        logger.error(f"File not found: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error replacing string in file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error replacing string in file: {str(e)}")

@router.post("/insert", response_model=FileOperationResponse)
@log_execution_time
async def api_insert_at_line(request: InsertRequest) -> FileOperationResponse:
    """Insert text at a specific line"""
    try:
        success, message = insert_at_line(request.path, request.insert_line, request.new_str)
        return FileOperationResponse(
            success=success,
            message=message
        )
    except FileNotFoundError as e:
        logger.error(f"File not found: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error inserting at line in file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error inserting at line in file: {str(e)}")

@router.post("/undo_edit/", response_model=FileOperationResponse)
@log_execution_time
async def api_undo_edit(request: UndoEditRequest) -> FileOperationResponse:
    """Revert the last edit made to a file"""
    try:
        success, message = undo_edit(request.path)
        logger.info(f"{message}")
        return FileOperationResponse(
            success=success,
            message=message
        )
    except Exception as e:
        logger.error(f"Error undoing edit: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error undoing edit: {str(e)}")

# Generic file operation endpoint
@router.post("/operation/", response_model=FileOperationResponse)
@log_execution_time
async def file_operation(operation: dict) -> FileOperationResponse:
    """
    Generic endpoint for file operations.
    
    Accepts a JSON object with 'command' and other parameters.
    Commands: 'view', 'create', 'str_replace', 'insert', 'undo_edit'
    """
    try:
        command = operation.get("command")

        logger.info(f"running {command}")

        if command == "view":
            return await api_view_file(ViewFileRequest(
                path=operation.get("path"),
                view_range=operation.get("view_range")
            ))
        
        elif command == "create":
            return await api_create_file(CreateFileRequest(
                path=operation.get("path"),
                file_text=operation.get("file_text", "")
            ))
        
        elif command == "str_replace":
            return await api_string_replace(StringReplaceRequest(
                path=operation.get("path"),
                old_str=operation.get("old_str", ""),
                new_str=operation.get("new_str", "")
            ))
        
        elif command == "insert":
            return await api_insert_at_line(InsertRequest(
                path=operation.get("path"),
                insert_line=operation.get("insert_line", 1),
                new_str=operation.get("new_str", "")
            ))
        
        elif command == "undo_edit":
            return await api_undo_edit(UndoEditRequest(
                path=operation.get("path")
            ))
        
        else:
            logger.error(f"unknown command: {command}")
            raise ValueError(f"Unknown command: {command}")
    
    except Exception as e:
        logger.error(f"Error in file operation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error in file operation: {str(e)}")
