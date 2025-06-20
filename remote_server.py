import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi import FastAPI, HTTPException, APIRouter
from pydantic import BaseModel
from asyncio import Task

from starlette.middleware.cors import CORSMiddleware

from remote_server_lib.api.async_process import router as async_process_router, cleanup_old_processes
from remote_server_lib.api.sync_process import router as sync_process_router
from remote_server_lib.api.git_functions import router as git_router
from remote_server_lib.api.str_replace import router as file_operations_router

from loguru import logger

API_VERSION_NUMBER = "0.1"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS")
DEBUG = os.environ.get("DEBUG")

# Store running processes and their metadata
cleanup_task: Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create the cleanup task
    global cleanup_task
    cleanup_task = asyncio.create_task(cleanup_old_processes())

    yield  # Run the FastAPI application

    # Shutdown: cancel the cleanup task
    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass

app = FastAPI(
    docs_url="/api/docs/",
    redoc_url="/api/redocs/",
    version=API_VERSION_NUMBER,
    title="AI Agents API",
    lifespan=lifespan,
)

allowed_hosts = [] if ALLOWED_HOSTS is None else ALLOWED_HOSTS
allowed_hosts.extend(
    [
        "http://localhost:3001",
        "http://0.0.0.0:3001",
        "http://127.0.0.1:3001",
    ]
)
origins = ["*"] if DEBUG else allowed_hosts

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex="https://.*\\.techarge\\.co\\.uk",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(responses={404: {"description": "Not found"}})
api_router.include_router(async_process_router)
api_router.include_router(sync_process_router)
api_router.include_router(git_router)
api_router.include_router(file_operations_router)
app.include_router(api_router)


os.chdir(os.environ.get("AIAGENTS_WORKING_DIR", "/data"))

# this is a simple server that provides a rest interface into a docker container to be able to run 
# arbitragy commands

# Custom exception handler for validation errors (422)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    error_details = []
    for error in exc.errors():
        error_details.append({
            "loc": error.get("loc", []),
            "msg": error.get("msg", ""),
            "type": error.get("type", "")
        })

    logger.error(f"Failed {request=}")
    logger.error(f"Validation Error: {error_details} {exc=}")  # Log the exception for debugging
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation Error",
            "errors": error_details,
            "body": exc.body  # Include the request body for debugging
        },
    )



@app.get("/health")
async def health_check():
    return {"status": "healthy"}
