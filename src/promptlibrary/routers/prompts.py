"""Prompt pages and mutations. Every mutation returns a consistent library and detail view."""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from promptlibrary.database import get_db
from promptlibrary.routers.common import require_prompt, tag_names, workspace
from promptlibrary.services.category_service import CategoryService
from promptlibrary.services.markdown_service import render_markdown
from promptlibrary.services.project_service import LabelService, ProjectService
from promptlibrary.services.prompt_service import PromptService
from promptlibrary.services.status_service import StatusService
from promptlibrary.services.version_service import VersionService

router = APIRouter(tags=["prompts"])


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    async with get_db(request.app.state.settings) as db:
        return await workspace(request, db, path="/")


@router.get("/prompts", response_class=HTMLResponse)
@router.get("/prompts/search", response_class=HTMLResponse)
async def list_prompts(request: Request) -> HTMLResponse:
    from promptlibrary.routers.common import filters_from_request

    filters = filters_from_request(request).model_copy(update={"item_type": "prompt"})
    async with get_db(request.app.state.settings) as db:
        return await workspace(request, db, path="/", filters=filters)


@router.get("/prompts/new", response_class=HTMLResponse)
async def new_prompt_form(request: Request) -> HTMLResponse:
    async with get_db(request.app.state.settings) as db:
        return await workspace(
            request,
            db,
            view="prompt_editor",
            title="New prompt",
            path="/prompts/new",
            prompt={
                "id": "",
                "title": "",
                "body": "",
                "notes": "",
                "status": "draft",
                "category_id": "",
                "project_id": request.query_params.get("project_id", ""),
                "tags": [],
                "labels": [],
                "updated_at": "",
            },
        )


@router.get("/prompts/{prompt_id}", response_class=HTMLResponse)
async def prompt_detail(request: Request, prompt_id: UUID) -> HTMLResponse:
    async with get_db(request.app.state.settings) as db:
        prompt = await require_prompt(db, str(prompt_id))
        return await workspace(
            request,
            db,
            view="prompt_detail",
            selected_id=str(prompt_id),
            title=prompt["title"],
            prompt=prompt,
            rendered_body=render_markdown(prompt["body"]),
            versions=await VersionService(db).list_versions(str(prompt_id)),
        )


@router.get("/prompts/{prompt_id}/edit", response_class=HTMLResponse)
async def prompt_edit_form(request: Request, prompt_id: UUID) -> HTMLResponse:
    async with get_db(request.app.state.settings) as db:
        prompt = await require_prompt(db, str(prompt_id))
        return await workspace(
            request,
            db,
            view="prompt_editor",
            selected_id=str(prompt_id),
            title=f"Edit {prompt['title']}",
            prompt=prompt,
        )


@router.post("/prompts", response_class=HTMLResponse)
async def create_prompt(
    request: Request,
    title: Annotated[str, Form()],
    body: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    status: Annotated[str, Form()] = "draft",
    category_id: Annotated[str, Form()] = "",
    project_id: Annotated[str, Form()] = "",
    tags: Annotated[str, Form()] = "",
    label_ids: Annotated[list[str] | None, Form()] = None,
) -> HTMLResponse:
    prompt_id = str(uuid4())
    async with get_db(request.app.state.settings, write=True) as db:
        await PromptService(db).create_prompt(
            prompt_id,
            title,
            body,
            notes,
            status,
            category_id or None,
            project_id or None,
            tag_names(tags),
        )
        await VersionService(db).create_version(prompt_id, body, notes, status, "Initial version")
        await LabelService(db).set_labels("prompt", prompt_id, label_ids or [])
        await db.commit()
        prompt = await require_prompt(db, prompt_id)
        return await workspace(
            request,
            db,
            view="prompt_detail",
            selected_id=prompt_id,
            title=prompt["title"],
            path=f"/prompts/{prompt_id}",
            prompt=prompt,
            rendered_body=render_markdown(body),
            versions=await VersionService(db).list_versions(prompt_id),
            message="Prompt created.",
        )


@router.put("/prompts/{prompt_id}", response_class=HTMLResponse)
@router.post("/prompts/{prompt_id}/save", response_class=HTMLResponse)
async def update_prompt(
    request: Request,
    prompt_id: UUID,
    title: Annotated[str, Form()],
    body: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    status: Annotated[str, Form()] = "draft",
    category_id: Annotated[str, Form()] = "",
    project_id: Annotated[str, Form()] = "",
    tags: Annotated[str, Form()] = "",
    version_message: Annotated[str, Form()] = "",
    label_ids: Annotated[list[str] | None, Form()] = None,
    expected_updated_at: Annotated[str, Form()] = "",
) -> HTMLResponse:
    identity = str(prompt_id)
    async with get_db(request.app.state.settings, write=True) as db:
        await PromptService(db).update_prompt(
            identity,
            title,
            body,
            notes,
            status,
            category_id or None,
            tag_names(tags),
            project_id,
            expected_updated_at=expected_updated_at or None,
        )
        await VersionService(db).create_version(
            identity, body, notes, status, version_message or None
        )
        await LabelService(db).set_labels("prompt", identity, label_ids or [])
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
            rendered_body=render_markdown(body),
            versions=await VersionService(db).list_versions(identity),
            message="Prompt saved.",
        )


@router.delete("/prompts/{prompt_id}", response_class=HTMLResponse)
@router.post("/prompts/{prompt_id}/delete", response_class=HTMLResponse)
async def delete_prompt(request: Request, prompt_id: UUID) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        await PromptService(db).delete_prompt(str(prompt_id))
        await db.commit()
        return await workspace(request, db, path="/", message="Prompt deleted.")


@router.post("/prompts/{prompt_id}/favourite", response_class=HTMLResponse)
async def toggle_favourite(request: Request, prompt_id: UUID) -> HTMLResponse:
    identity = str(prompt_id)
    async with get_db(request.app.state.settings, write=True) as db:
        await PromptService(db).toggle_favourite(identity)
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
            rendered_body=render_markdown(prompt["body"]),
            versions=await VersionService(db).list_versions(identity),
        )


@router.get("/api/tags/suggest")
async def suggest_tags(request: Request, q: str = "") -> JSONResponse:
    async with get_db(request.app.state.settings) as db:
        cursor = await db.execute(
            "SELECT name FROM tags WHERE name LIKE ? ORDER BY name LIMIT 10", (f"%{q}%",)
        )
        return JSONResponse([row[0] for row in await cursor.fetchall()])


class PreviewInput(BaseModel):
    text: str = Field(default="", max_length=2_000_000)


@router.post("/api/preview")
async def preview_markdown(payload: PreviewInput) -> JSONResponse:
    return JSONResponse({"html": render_markdown(payload.text)})


class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)


@router.post("/api/categories")
async def create_category_api(request: Request, payload: ProjectInput) -> JSONResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        identity = await CategoryService(db).create(payload.name)
        await db.commit()
        return JSONResponse({"id": identity, "name": payload.name.strip()})


@router.post("/api/statuses")
async def create_status_api(request: Request, payload: ProjectInput) -> JSONResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        key = await StatusService(db).save_status(payload.name)
        await db.commit()
        return JSONResponse({"id": key, "key": key, "name": payload.name.strip()})


@router.post("/api/projects")
async def create_project_api(request: Request, payload: ProjectInput) -> JSONResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        identity = await ProjectService(db).create_project(payload.name)
        await db.commit()
        return JSONResponse({"id": identity, "name": payload.name.strip()})


@router.post("/prompts/{prompt_id}/add-to-workflow", response_class=HTMLResponse)
async def add_prompt_to_workflow(
    request: Request,
    prompt_id: UUID,
    workflow_id: Annotated[str, Form()],
    link_prompt: Annotated[bool, Form()] = False,
) -> HTMLResponse:
    from promptlibrary.routers.workflows import detail_page
    from promptlibrary.services.workflow_service import WorkflowService

    async with get_db(request.app.state.settings, write=True) as db:
        prompt = await require_prompt(db, str(prompt_id))
        await WorkflowService(db).add_stage(
            workflow_id, prompt["title"], prompt_id=str(prompt_id), link_prompt=link_prompt
        )
        await db.commit()
        return await detail_page(request, db, workflow_id, "Prompt added to the workflow.")
