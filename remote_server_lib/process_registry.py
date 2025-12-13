"""
Process Registry for tracking background processes.

Maintains mappings between MCP request IDs and process IDs,
allowing for graceful termination and process management.
"""
import signal
import asyncio
from datetime import datetime
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class ProcessInfo:
    """Information about a tracked background process."""
    pid: int
    request_id: int
    command: str
    started_at: datetime
    status: str = "running"  # running, completed, terminated, failed
    exit_code: Optional[int] = None
    terminated_at: Optional[datetime] = None
    termination_signal: Optional[str] = None


class ProcessRegistry:
    """
    Registry for tracking background processes.

    Maintains bidirectional mappings between request IDs and PIDs,
    and provides process lifecycle management.
    """

    def __init__(self, termination_timeout: int = 30):
        """
        Initialize the process registry.

        Args:
            termination_timeout: Seconds to wait for graceful termination before SIGKILL
        """
        self.termination_timeout = termination_timeout
        self._by_request_id: Dict[int, ProcessInfo] = {}
        self._by_pid: Dict[int, ProcessInfo] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        request_id: int,
        pid: int,
        command: str
    ) -> ProcessInfo:
        """
        Register a new background process.

        Args:
            request_id: MCP request ID that started the process
            pid: Process ID
            command: Command being executed

        Returns:
            ProcessInfo object
        """
        async with self._lock:
            process_info = ProcessInfo(
                pid=pid,
                request_id=request_id,
                command=command,
                started_at=datetime.now()
            )

            self._by_request_id[request_id] = process_info
            self._by_pid[pid] = process_info

            logger.info(f"Registered process: request_id={request_id}, pid={pid}")
            return process_info

    async def unregister(
        self,
        request_id: Optional[int] = None,
        pid: Optional[int] = None
    ) -> Optional[ProcessInfo]:
        """
        Unregister a process by request ID or PID.

        Args:
            request_id: MCP request ID
            pid: Process ID

        Returns:
            ProcessInfo if found, None otherwise
        """
        async with self._lock:
            process_info = None

            if request_id:
                process_info = self._by_request_id.pop(request_id, None)
            elif pid:
                process_info = self._by_pid.pop(pid, None)

            if process_info:
                # Remove from both mappings
                self._by_request_id.pop(process_info.request_id, None)
                self._by_pid.pop(process_info.pid, None)
                logger.info(f"Unregistered process: request_id={process_info.request_id}, pid={process_info.pid}")

            return process_info

    async def get_by_request_id(self, request_id: int) -> Optional[ProcessInfo]:
        """Get process info by request ID."""
        async with self._lock:
            return self._by_request_id.get(request_id)

    async def get_by_pid(self, pid: int) -> Optional[ProcessInfo]:
        """Get process info by PID."""
        async with self._lock:
            return self._by_pid.get(pid)

    async def list_all(self) -> List[ProcessInfo]:
        """Get list of all tracked processes."""
        async with self._lock:
            return list(self._by_request_id.values())

    async def update_status(
        self,
        request_id: Optional[int] = None,
        pid: Optional[int] = None,
        status: Optional[str] = None,
        exit_code: Optional[int] = None
    ) -> bool:
        """
        Update process status.

        Args:
            request_id: MCP request ID
            pid: Process ID
            status: New status (running, completed, terminated, failed)
            exit_code: Exit code if completed

        Returns:
            True if updated, False if process not found
        """
        async with self._lock:
            process_info = None
            if request_id:
                process_info = self._by_request_id.get(request_id)
            elif pid:
                process_info = self._by_pid.get(pid)

            if process_info:
                if status:
                    process_info.status = status
                if exit_code is not None:
                    process_info.exit_code = exit_code
                if status in ("completed", "terminated", "failed"):
                    process_info.terminated_at = datetime.now()
                return True

            return False

    async def terminate_gracefully(
        self,
        request_id: Optional[int] = None,
        pid: Optional[int] = None,
        reason: str = "Manual termination"
    ) -> Dict:
        """
        Terminate a process gracefully with SIGTERM, then SIGKILL if needed.

        Args:
            request_id: MCP request ID
            pid: Process ID
            reason: Reason for termination

        Returns:
            Dict with termination result
        """
        # Get process info
        process_info = None
        if request_id:
            process_info = await self.get_by_request_id(request_id)
        elif pid:
            process_info = await self.get_by_pid(pid)

        if not process_info:
            return {
                "success": False,
                "error": f"Process not found: request_id={request_id}, pid={pid}"
            }

        target_pid = process_info.pid
        logger.info(f"Terminating process {target_pid} gracefully. Reason: {reason}")

        import os

        try:
            # Check if process exists - try psutil first
            try:
                import psutil
                try:
                    proc = psutil.Process(target_pid)
                except psutil.NoSuchProcess:
                    # Process doesn't exist - verify with os.kill
                    try:
                        os.kill(target_pid, 0)
                    except OSError:
                        logger.warning(f"Process {target_pid} no longer exists")
                        await self.update_status(pid=target_pid, status="completed", exit_code=0)
                        await self.unregister(pid=target_pid)
                        return {
                            "success": True,
                            "pid": target_pid,
                            "request_id": process_info.request_id,
                            "signal": None,
                            "exit_code": 0,
                            "message": "Process already terminated"
                        }
            except ImportError:
                # psutil not available, fall back to os.kill
                try:
                    os.kill(target_pid, 0)  # Check if process exists
                except OSError:
                    logger.warning(f"Process {target_pid} no longer exists")
                    await self.update_status(pid=target_pid, status="completed", exit_code=0)
                    await self.unregister(pid=target_pid)
                    return {
                        "success": True,
                        "pid": target_pid,
                        "request_id": process_info.request_id,
                        "signal": None,
                        "exit_code": 0,
                        "message": "Process already terminated"
                    }

            # Send SIGTERM
            logger.info(f"Sending SIGTERM to process {target_pid}")
            os.kill(target_pid, signal.SIGTERM)
            process_info.termination_signal = "SIGTERM"

            # Wait for graceful termination
            terminated = False
            for i in range(self.termination_timeout):
                await asyncio.sleep(1)
                try:
                    os.kill(target_pid, 0)  # Check if still alive
                except OSError:
                    # Process terminated
                    terminated = True
                    logger.info(f"Process {target_pid} terminated gracefully after {i+1} seconds")
                    break

            # If still running, use SIGKILL
            if not terminated:
                logger.warning(f"Process {target_pid} did not terminate gracefully, sending SIGKILL")
                try:
                    os.kill(target_pid, signal.SIGKILL)
                    process_info.termination_signal = "SIGKILL"
                    await asyncio.sleep(0.5)  # Brief wait for SIGKILL
                except OSError:
                    pass  # Already dead

            # Update status and unregister
            await self.update_status(pid=target_pid, status="terminated")
            await self.unregister(pid=target_pid)

            return {
                "success": True,
                "pid": target_pid,
                "request_id": process_info.request_id,
                "signal": process_info.termination_signal,
                "exit_code": None,
                "message": f"Process terminated with {process_info.termination_signal}",
                "reason": reason
            }

        except Exception as e:
            logger.error(f"Error terminating process {target_pid}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "pid": target_pid,
                "request_id": process_info.request_id
            }


# Global process registry instance
_process_registry: Optional[ProcessRegistry] = None


def get_process_registry(termination_timeout: int = 30) -> ProcessRegistry:
    """Get or create the global process registry."""
    global _process_registry
    if _process_registry is None:
        _process_registry = ProcessRegistry(termination_timeout=termination_timeout)
    return _process_registry
