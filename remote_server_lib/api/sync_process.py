import json 
from fastapi import HTTPException, APIRouter

from remote_server_lib.api.models import SourceCodeRequest
from remote_server_lib.core import execute_command_helper, CommandRequest, CommandResponse
from remote_server_lib.sourcecode import display_file_contents
from remote_server_lib.logging import log_execution_time

from loguru import logger

router = APIRouter(prefix="/api/sync", tags=["sync"])
router.get(path="/api/sync")



@router.post("/execute/", response_model=str)
@log_execution_time
async def execute_command(request: CommandRequest)->str:
    try:
        result: CommandResponse = execute_command_helper(request.command)

        # Prepare response
        response = {
            "command": request.command,
            "output": result.output,
            "error": result.error,
            "return_code": result.return_code
        }

        return json.dumps(response)

    except Exception as e:
        logger.error(f"Error executing command: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error executing command: {str(e)}")

@router.post("/sourcecode/")
#@log_execution_time
async def get_all_source_code(req: SourceCodeRequest):

    try:
        #dbg = f"{req.dir_path=} / {req.file_ext=} / {req.skip_dirs=} / {req.skip_ext=}"
        res = display_file_contents(req.dir_path, req.file_ext, req.skip_dirs, req.skip_ext)
        return f"{res}"
    except Exception as e:
        logger.error(f"Error getting sourcecode: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error listing files: {str(e)}")

# Health check endpoint

