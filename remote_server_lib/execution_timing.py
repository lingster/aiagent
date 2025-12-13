import time
import random
import asyncio
from loguru import logger
from functools import wraps
from typing import Callable, ParamSpec, TypeVar

# Type variables for generic function parameters and return type
P = ParamSpec("P")
R = TypeVar("R")

def log_execution_time(func: Callable[P, R]) -> Callable[P, R]:
    """
    Decorator that logs the start time, end time, and duration of a function execution.
    Uses time.monotonic() for accurate duration measurement.

    Args:
        func: The function to be decorated

    Returns:
        The wrapped function with timing logs
    """
    @wraps(func)
    async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        start_time = time.monotonic()
        start_datetime = time.strftime('%Y-%m-%d %H:%M:%S')

        try:
            logger.info(f"Starting function {func.__name__}")
            result = await func(*args, **kwargs)
            logger.info(f"awill return {result=}")
            return result
        finally:
            end_time = time.monotonic()
            duration = end_time - start_time

            logger.info(
                f"Completed {func.__name__}, Start: {start_datetime}, Duration: {duration:.3f} seconds"
            )

    @wraps(func)
    def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        start_time = time.monotonic()
        start_datetime = time.strftime('%Y-%m-%d %H:%M:%S')

        try:
            logger.info(f"Starting function {func.__name__}")
            result = func(*args, **kwargs)
            logger.info(f"will return {result=}")
            return result
        finally:
            end_time = time.monotonic()
            duration = end_time - start_time
            logger.info(
                f"Completed: {func.__name__}, Start: {start_datetime}, Duration: {duration:.3f} seconds"

            )

    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
