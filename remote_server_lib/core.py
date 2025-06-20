import subprocess
from pydantic import BaseModel
from loguru import logger

class CommandException(Exception):
    pass

class CommandRequest(BaseModel):
    command: str

class CommandResponse(BaseModel):
    command: str
    output: str
    error: str
    return_code: int


def execute_command_helper(command: str) -> CommandResponse:
    try:
        # Execute the command and capture output
        logger.info(f"Executing command: {command}")
        result = subprocess.run(
            command,
            shell=True,  # Required for command interpretation
            capture_output=True,
            text=True,   # Return strings instead of bytes
            check=False  # Don't raise exception on non-zero exit
        )

        # Prepare response
        response = CommandResponse(
            command=command,
            output=result.stdout,
            error=result.stderr,
            return_code=result.returncode
        )
        return response

    except Exception as e:
        raise CommandException(detail=f"Error executing local command: {str(e)}")

