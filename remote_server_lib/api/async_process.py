import uuid
import asyncio
import os
from fastapi import APIRouter
from fastapi import HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from loguru import logger

from remote_server_lib.process_registry import get_process_registry


router = APIRouter(prefix="/api/async", tags=["async"])
router.get(path="/api/async")


background_processes: dict[str, dict] = {}
PROCESS_RETENTION = 24  # hours
CLEANUP_INTERVAL = 3600  # 1 hour

# Get termination timeout from environment
TERMINATION_TIMEOUT = int(os.environ.get("TERMINATION_TIMEOUT", "30"))

# Initialize process registry for backend
backend_process_registry = get_process_registry(termination_timeout=TERMINATION_TIMEOUT)


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
        cmd_str = command if isinstance(command, str) else " ".join(command)
        process = await asyncio.create_subprocess_shell(
            cmd_str,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        background_processes[process_id]["process"] = process
        background_processes[process_id]["pid"] = process.pid

        # Register in process registry
        await backend_process_registry.register(
            request_id=process_id,
            pid=process.pid,
            command=cmd_str
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )

            # Update registry
            await backend_process_registry.update_status(
                pid=process.pid,
                status="completed",
                exit_code=process.returncode
            )
            await backend_process_registry.unregister(pid=process.pid)

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

            # Update registry
            await backend_process_registry.update_status(
                pid=process.pid,
                status="timeout"
            )
            await backend_process_registry.unregister(pid=process.pid)

            background_processes[process_id].update({
                "status": "timeout",
                "end_time": datetime.now()
            })

    except Exception as e:
        if process_id in background_processes and "pid" in background_processes[process_id]:
            await backend_process_registry.unregister(pid=background_processes[process_id]["pid"])

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

        # Update registry
        if "pid" in process_info:
            await backend_process_registry.unregister(pid=process_info["pid"])

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


@router.post("/process/terminate_by_pid/")
async def terminate_process_by_pid(pid: int):
    """Terminate a process by PID using graceful termination (SIGTERM then SIGKILL)"""
    try:
        result = await backend_process_registry.terminate_gracefully(
            pid=pid,
            reason="Termination via API"
        )

        if result.get("success"):
            return {
                "success": True,
                "pid": pid,
                "request_id": result.get("request_id"),
                "signal": result.get("signal"),
                "message": result.get("message")
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=result.get("error", "Process not found")
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to terminate process: {str(e)}"
        )


@router.get("/processes/list/")
async def list_all_processes():
    """List all background processes tracked by the registry"""
    try:
        processes = await backend_process_registry.list_all()

        return {
            "processes": [
                {
                    "pid": p.pid,
                    "request_id": p.request_id,
                    "command": p.command,
                    "status": p.status,
                    "started_at": p.started_at.isoformat(),
                    "exit_code": p.exit_code,
                    "terminated_at": p.terminated_at.isoformat() if p.terminated_at else None,
                    "termination_signal": p.termination_signal
                }
                for p in processes
            ],
            "count": len(processes)
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list processes: {str(e)}"
        )
