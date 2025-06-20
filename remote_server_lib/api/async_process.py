import uuid
import asyncio
from fastapi import APIRouter
from fastapi import HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from loguru import logger


router = APIRouter(prefix="/api/async", tags=["async"])
router.get(path="/api/async")


background_processes: dict[str, dict] = {}
PROCESS_RETENTION = 24  # hours
CLEANUP_INTERVAL = 3600  # 1 hour


class AsyncCommandRequest(BaseModel):
    command: str | list[str]
    timeout: Optional[int] = None


class AsyncCommandResponse(BaseModel):
    process_id: str
    command: str | list[str]
    start_time: datetime
    status: str
    timeout: int = 600


async def cleanup_old_processes() -> None:
    """Remove completed processes older than PROCESS_RETENTION hours"""
    while True:
        try:
            current_time = datetime.now()
            retention_cutoff = current_time - timedelta(hours=PROCESS_RETENTION)

            processes_to_remove = [
                pid for pid, info in background_processes.items()
                if (info.get("status") in ["completed", "failed", "timeout", "terminated"] and
                    info.get("end_time", current_time) < retention_cutoff)
            ]

            for pid in processes_to_remove:
                del background_processes[pid]
                logger.info(f"Cleaned up process {pid}")

            await asyncio.sleep(CLEANUP_INTERVAL)

        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")
            await asyncio.sleep(60)  # Wait before retrying on error


async def run_command(process_id: str, command: str | list[str], timeout: Optional[int] = None) -> None:
    try:
        logger.info(f"starting: {command=}")
        process = await asyncio.create_subprocess_shell(
            command if isinstance(command, str) else " ".join(command),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        background_processes[process_id]["process"] = process

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )

            background_processes[process_id].update({
                "status": "completed",
                "return_code": process.returncode,
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
                "end_time": datetime.now()
            })
        except asyncio.TimeoutError:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                process.kill()  # Force kill if terminate doesn't work

            background_processes[process_id].update({
                "status": "timeout",
                "end_time": datetime.now()
            })

    except Exception as e:
        background_processes[process_id].update({
            "status": "failed",
            "error": str(e),
            "end_time": datetime.now()
        })


@router.post("/execute/background/", response_model=AsyncCommandResponse)
async def execute_background_command(request: AsyncCommandRequest) -> AsyncCommandResponse:
    process_id = str(uuid.uuid4())

    background_processes[process_id] = {
        "command": request.command,
        "start_time": datetime.now(),
        "status": "running"
    }

    # Start the command in the background

    asyncio.create_task(run_command(process_id, request.command, request.timeout))

    return AsyncCommandResponse(
        process_id=process_id,
        command=request.command,
        start_time=background_processes[process_id]["start_time"],
        status=background_processes[process_id]["status"]
    )


@router.get("/process/{process_id}/")
async def get_process_status(process_id: str):
    if process_id not in background_processes:
        raise HTTPException(status_code=404, detail="Process not found")

    process_info = background_processes[process_id].copy()

    # Remove the process object from the response
    process_info.pop("process", None)

    return process_info


@router.post("/process/terminate/{process_id}/")
async def terminate_process(process_id: str):
    if process_id not in background_processes:
        raise HTTPException(status_code=404, detail="Process not found")


    try:
        process_info = background_processes[process_id]
        process = process_info.get("process")

        if not process or process_info["status"] != "running":
            raise HTTPException(
                status_code=400,
                detail=f"Process cannot be terminated (status: {process_info['status']})"
            )
        # Try graceful termination first
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            # If termination doesn't work, force kill
            process.kill()
            await process.wait()

        process_info.update({
            "status": "terminated",
            "end_time": datetime.now()
        })

        return {"status": "terminated", "process_id": process_id}

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to terminate process: {str(e)}"
        )
