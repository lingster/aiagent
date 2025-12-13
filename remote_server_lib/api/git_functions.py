import json 
from fastapi import HTTPException, APIRouter
from pydantic import BaseModel

from config import get_working_dir
from remote_server_lib.api.models import SourceCodeRequest
from remote_server_lib.core import execute_command_helper, CommandRequest, CommandResponse
from remote_server_lib.sourcecode import display_file_contents
from remote_server_lib.execution_timing import log_execution_time

from loguru import logger

router = APIRouter(prefix="/api/git", tags=["git"])
router.get(path="/api/git")


class GitRepoRequest(BaseModel):
    owner: str
    repo: str
    gh_token: str
    branch: str = "main"
    target_dir: str = f"{get_working_dir()}/cloned_repos"

@router.post("/clone/", response_model=str)
@log_execution_time
async def git_clone_command(request: GitRepoRequest) -> str:
    try:
        # Construct the git clone URL with authentication token
        clone_url = f"https://{request.gh_token}@github.com/{request.owner}/{request.repo}.git"
        
        # Create target directory if it doesn't exist
        mkdir_cmd = f"mkdir -p {request.target_dir}"
        mkdir_result = execute_command_helper(mkdir_cmd)
        
        if mkdir_result.return_code != 0:
            logger.error(f"Failed to create target directory: {mkdir_result.error}")
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to create target directory: {mkdir_result.error}"
            )
        
        # Prepare the git clone command with branch specification
        repo_name = request.repo
        target_path = f"{request.target_dir}/{repo_name}"
        
        # Check if repo already exists
        check_cmd = f"[ -d {target_path}/.git ] && echo 'exists' || echo 'not exists'"
        check_result = execute_command_helper(check_cmd)
        
        # Command and result to return
        command = ""
        result = None
        
        if "exists" in check_result.output:
            # If repo exists, pull latest changes
            logger.info(f"Repository already exists at {target_path}, pulling latest changes")
            command = f"cd {target_path} && git fetch && git checkout {request.branch} && git pull origin {request.branch}"
            result = execute_command_helper(command)
        else:
            # Clone the repository with specified branch
            logger.info(f"Cloning repository to {target_path}")
            command = f"git clone -b {request.branch} {clone_url} {target_path}"
            result = execute_command_helper(command)
        
        # Prepare response
        response = {
            "command": command.replace(request.gh_token, "***TOKEN***"),  # Redact token from logs
            "output": result.output,
            "error": result.error,
            "return_code": result.return_code
        }

        return json.dumps(response)

    except Exception as e:
        logger.error(f"Error executing command: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error executing command: {str(e)}")
