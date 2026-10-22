"""Version history, comparisons and explicitly destructive history removal."""

from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from promptlibrary.database import get_db
from promptlibrary.routers.common import require_prompt, workspace
from promptlibrary.services.markdown_service import render_markdown
from promptlibrary.services.validation import NotFoundError
from promptlibrary.services.version_service import VersionService

router = APIRouter(tags=["versions"])


@router.get("/versions/prompts/{prompt_id}/versions", response_class=HTMLResponse)
async def version_history(request: Request, prompt_id: UUID) -> HTMLResponse:
    identity = str(prompt_id)
    async with get_db(request.app.state.settings) as db:
        prompt = await require_prompt(db, identity)
        return await workspace(
            request,
            db,
            view="prompt_detail",
            selected_id=identity,
            title=prompt["title"],
            path=f"/prompts/{identity}",
            prompt=prompt,
            history_open=True,
            versions=await VersionService(db).list_versions(identity),
            rendered_body=render_markdown(prompt["body"]),
        )


@router.get(
    "/versions/prompts/{prompt_id}/versions/{version_number}/diff", response_class=HTMLResponse
)
async def version_diff(request: Request, prompt_id: UUID, version_number: int) -> HTMLResponse:
    identity = str(prompt_id)
    async with get_db(request.app.state.settings) as db:
        prompt = await require_prompt(db, identity)
        service = VersionService(db)
        version = await service.get_version(identity, version_number)
        if version is None:
            raise NotFoundError("Version not found.")
        return await workspace(
            request,
            db,
            view="version_diff",
            selected_id=identity,
            title="Version comparison",
            prompt=prompt,
            saved_version=version,
            diff=await service.get_diff(identity, version_number),
        )


@router.post("/versions/prompts/{prompt_id}/restore/{version_number}", response_class=HTMLResponse)
async def restore_version(request: Request, prompt_id: UUID, version_number: int) -> HTMLResponse:
    identity = str(prompt_id)
    async with get_db(request.app.state.settings, write=True) as db:
        service = VersionService(db)
        await service.restore_version(identity, version_number)
        await db.commit()
        prompt = await require_prompt(db, identity)
        return await workspace(
            request,
            db,
            view="prompt_detail",
            selected_id=identity,
            title=prompt["title"],
            path=f"/prompts/{identity}",
            prompt=prompt,
            history_open=True,
            versions=await service.list_versions(identity),
            rendered_body=render_markdown(prompt["body"]),
            message="Version restored as a new version.",
        )


@router.delete("/prompts/{prompt_id}/versions", response_class=HTMLResponse)
@router.post("/prompts/{prompt_id}/versions/clear", response_class=HTMLResponse)
async def clear_history(request: Request, prompt_id: UUID) -> HTMLResponse:
    identity = str(prompt_id)
    async with get_db(request.app.state.settings, write=True) as db:
        await VersionService(db).clear_history(identity)
        await db.commit()
        prompt = await require_prompt(db, identity)
        return await workspace(
            request,
            db,
            view="prompt_detail",
            selected_id=identity,
            title=prompt["title"],
            path=f"/prompts/{identity}",
            prompt=prompt,
            versions=[],
            history_open=True,
            rendered_body=render_markdown(prompt["body"]),
            message="Version history cleared.",
        )
