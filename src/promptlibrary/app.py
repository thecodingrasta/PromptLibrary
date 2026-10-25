"""Application lifecycle, HTTP boundaries and command-line entry point."""

import argparse
import logging
import os
import sqlite3
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from promptlibrary import __version__, config
from promptlibrary.database import get_db, init_db
from promptlibrary.routers import (
    export,
    pages,
    projects,
    prompts,
    settings,
    sync,
    versions,
    widget,
    workflows,
)
from promptlibrary.security import SecurityMiddleware
from promptlibrary.services.validation import ConflictError, NotFoundError

PACKAGE_DIR = Path(__file__).parent
logger = logging.getLogger("promptlibrary")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db(app.state.settings)
    logger.info("PromptLibrary %s started", __version__)
    yield
    logger.info("PromptLibrary stopped")


def create_app(configuration: config.Settings | None = None) -> FastAPI:
    configuration = configuration or config.settings
    app = FastAPI(
        title="PromptLibrary",
        version=__version__,
        lifespan=lifespan,
        description="Single-operator prompt library and guided workflows.",
        debug=False,
        docs_url=None,
        redoc_url=None,
    )
    app.state.settings = configuration
    app.state.templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
    app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")
    app.add_middleware(SecurityMiddleware, settings=configuration)

    @app.exception_handler(RequestValidationError)
    async def request_error(request: Request, error: RequestValidationError) -> JSONResponse:
        fields = sorted({".".join(str(part) for part in issue["loc"]) for issue in error.errors()})
        return JSONResponse(
            {"detail": "Invalid input. Check: " + ", ".join(fields)}, status_code=422
        )

    @app.exception_handler(ValueError)
    async def value_error(request: Request, error: ValueError) -> JSONResponse:
        if isinstance(error, NotFoundError):
            status = 404
        elif isinstance(error, ConflictError):
            status = 409
        else:
            status = 400
        # Validation errors can contain submitted secrets. Never echo their inputs.
        message = (
            "Invalid input. Check the supplied fields."
            if isinstance(error, ValidationError)
            else str(error)
        )
        return JSONResponse({"detail": message}, status_code=status)

    @app.exception_handler(sqlite3.IntegrityError)
    async def integrity_error(request: Request, error: sqlite3.IntegrityError) -> JSONResponse:
        return JSONResponse(
            {"detail": "A duplicate value or invalid reference conflicts with this change."},
            status_code=409,
        )

    @app.exception_handler(sqlite3.OperationalError)
    async def database_error(request: Request, error: sqlite3.OperationalError) -> JSONResponse:
        if "locked" in str(error).lower() or "busy" in str(error).lower():
            return JSONResponse(
                {"detail": "The library is busy. Retry this change."}, status_code=409
            )
        logger.error("Database operation failed: %s", type(error).__name__)
        return JSONResponse(
            {"detail": "Database operation failed. Check the server and database integrity."},
            status_code=500,
        )

    @app.get("/health")
    async def health() -> JSONResponse:
        async with get_db(configuration) as db:
            await db.execute("SELECT version FROM schema_version LIMIT 1")
        return JSONResponse({"status": "ok", "version": __version__})

    for module in (prompts, projects, versions, workflows, settings, sync, export, widget, pages):
        app.include_router(module.router)
    return app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="PromptLibrary local web server")
    parser.add_argument("--version", action="version", version=__version__)
    parser.parse_args(argv)
    if os.name == "nt" and os.environ.get("PROMPTLIB_SERVER_ROLE") != "web-server":
        environment = os.environ.copy()
        environment["PROMPTLIB_LAUNCHER_ROLE"] = "tray"
        creation_flags = int(getattr(subprocess, "DETACHED_PROCESS", 0)) | int(
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
        interpreter = Path(sys.executable)
        if os.name == "nt":
            windowless = interpreter.with_name("pythonw.exe")
            if windowless.exists():
                interpreter = windowless
        subprocess.Popen(  # noqa: S603 - executable and arguments are local constants.
            [str(interpreter), "-m", "promptlibrary.tray", *(argv or [])],
            env=environment,
            creationflags=creation_flags,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

    configuration = config.settings
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    uvicorn.run(
        create_app(configuration),
        host=configuration.host,
        port=configuration.port,
        reload=False,
        log_level="debug" if configuration.debug else "info",
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
