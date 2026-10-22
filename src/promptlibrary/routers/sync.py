"""Remote configuration and explicit snapshot transfer controls."""

from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from promptlibrary.database import get_db
from promptlibrary.routers.common import page
from promptlibrary.services.export_service import ImportMode
from promptlibrary.services.sync_config_service import RemoteConfig, SyncConfigService
from promptlibrary.services.sync_service import SyncService
from promptlibrary.services.validation import ConflictError

router = APIRouter(prefix="/sync", tags=["backups"])


async def backup_page(
    request: Request, db: aiosqlite.Connection, message: str | None = None
) -> HTMLResponse:
    service = SyncConfigService(db, request.app.state.settings)
    config_error = ""
    try:
        config = await service.load()
    except (ConflictError, ValueError) as error:
        config = RemoteConfig()
        config_error = str(error)
    return page(
        request,
        "pages/sync.html",
        {
            "remote": config.public_values(),
            "last_synced": await service.last_synced(),
            "config_error": config_error,
        },
        title="Backups | PromptLibrary",
        section="sync",
        url="/sync",
        message=message,
    )


@router.get("", response_class=HTMLResponse)
async def sync_page(request: Request) -> HTMLResponse:
    async with get_db(request.app.state.settings) as db:
        return await backup_page(request, db)


@router.post("/config", response_class=HTMLResponse)
async def save_config(request: Request) -> HTMLResponse:
    form = await request.form()
    values = {name: str(value) for name, value in form.items() if name in RemoteConfig.model_fields}
    async with get_db(request.app.state.settings) as db:
        await SyncConfigService(db, request.app.state.settings).save(
            values,
            preserve_secrets=form.get("clear_secrets") != "true",
        )
        return await backup_page(request, db, "Remote configuration saved.")


@router.post("/test", response_class=HTMLResponse)
async def test_connection(request: Request) -> HTMLResponse:
    async with get_db(request.app.state.settings) as db:
        await SyncService(db, request.app.state.settings).test_connection()
        return await backup_page(request, db, "Saved remote connection succeeded.")


@router.post("/push", response_class=HTMLResponse)
async def push_remote(request: Request) -> HTMLResponse:
    async with get_db(request.app.state.settings) as db:
        await SyncService(db, request.app.state.settings).push()
        return await backup_page(request, db, "Library snapshot pushed to the remote.")


@router.post("/pull", response_class=HTMLResponse)
async def pull_remote(
    request: Request, mode: Annotated[ImportMode, Form()] = "merge"
) -> HTMLResponse:
    async with get_db(request.app.state.settings) as db:
        result = await SyncService(db, request.app.state.settings).pull(mode)
        message = f"Imported {result.imported} records; skipped {result.skipped} identical records."
        if result.safety_backup:
            message += " A pre-restore safety snapshot was saved in the data directory."
        return await backup_page(request, db, message)
