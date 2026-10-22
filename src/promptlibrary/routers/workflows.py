"""Workflow composition and provider-neutral, resumable guided runs."""

from typing import Annotated
from uuid import UUID

import aiosqlite
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from promptlibrary.database import get_db
from promptlibrary.routers.common import filters_from_request, tag_names, workspace
from promptlibrary.services.project_service import LabelService
from promptlibrary.services.run_service import RunService
from promptlibrary.services.validation import ConflictError, Record
from promptlibrary.services.workflow_service import WorkflowService

router = APIRouter(prefix="/workflows", tags=["workflows"])


async def detail_page(
    request: Request,
    db: aiosqlite.Connection,
    workflow_id: str,
    message: str | None = None,
) -> HTMLResponse:
    workflow = await WorkflowService(db).require_workflow(workflow_id)
    cursor = await db.execute("SELECT id,title FROM prompts ORDER BY title COLLATE NOCASE")
    available_prompts = [dict(row) for row in await cursor.fetchall()]
    run_error = ""
    try:
        inputs = RunService.required_inputs(workflow)
    except ValueError as error:
        inputs = []
        run_error = str(error)
    return await workspace(
        request,
        db,
        view="workflow_detail",
        selected_id=workflow_id,
        title=workflow["name"],
        path=f"/workflows/{workflow_id}",
        workflow=workflow,
        available_prompts=available_prompts,
        runs=await RunService(db).list_runs(workflow_id),
        inputs=inputs,
        run_error=run_error,
        message=message,
    )


@router.get("", response_class=HTMLResponse)
async def list_workflows(request: Request) -> HTMLResponse:
    filters = filters_from_request(request).model_copy(update={"item_type": "workflow"})
    async with get_db(request.app.state.settings) as db:
        return await workspace(request, db, title="Workflows", path="/", filters=filters)


@router.get("/new", response_class=HTMLResponse)
async def new_workflow(request: Request) -> HTMLResponse:
    workflow: Record = {
        "id": "",
        "name": "",
        "description": "",
        "status": "draft",
        "category_id": "",
        "project_id": request.query_params.get("project_id", ""),
        "tags": [],
        "labels": [],
        "updated_at": "",
    }
    async with get_db(request.app.state.settings) as db:
        return await workspace(
            request, db, view="workflow_editor", title="New workflow", workflow=workflow
        )


@router.post("", response_class=HTMLResponse)
async def create_workflow(
    request: Request,
    name: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    project_id: Annotated[str, Form()] = "",
    category_id: Annotated[str, Form()] = "",
    status: Annotated[str, Form()] = "draft",
    tags: Annotated[str, Form()] = "",
    label_ids: Annotated[list[str] | None, Form()] = None,
) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        identity = await WorkflowService(db).create_workflow(
            name,
            description,
            project_id or None,
            category_id or None,
            status,
            tag_names(tags),
        )
        await LabelService(db).set_labels("workflow", identity, label_ids or [])
        await db.commit()
        return await detail_page(request, db, identity, "Workflow created.")


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_detail(request: Request, run_id: UUID) -> HTMLResponse:
    async with get_db(request.app.state.settings) as db:
        run = await RunService(db).get_run(str(run_id))
        return await workspace(
            request,
            db,
            view="run_detail",
            run=run,
            selected_id=run["workflow_id"],
            title=run["snapshot"]["name"],
        )


@router.post("/runs/{run_id}/complete", response_class=HTMLResponse)
async def complete_run_stage(
    request: Request,
    run_id: UUID,
    expected_stage: Annotated[int, Form()],
    output: Annotated[str, Form()],
) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        run = await RunService(db).complete_step(str(run_id), expected_stage, output)
        await db.commit()
        return await workspace(
            request,
            db,
            view="run_detail",
            run=run,
            selected_id=run["workflow_id"],
            title=run["snapshot"]["name"],
            path=f"/workflows/runs/{run_id}",
            message="Stage output saved.",
        )


@router.post("/runs/{run_id}/cancel", response_class=HTMLResponse)
async def cancel_run(request: Request, run_id: UUID) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        service = RunService(db)
        await service.cancel(str(run_id))
        await db.commit()
        run = await service.get_run(str(run_id))
        return await workspace(
            request,
            db,
            view="run_detail",
            run=run,
            selected_id=run["workflow_id"],
            title=run["snapshot"]["name"],
            path=f"/workflows/runs/{run_id}",
            message="Run cancelled.",
        )


@router.get("/{workflow_id}", response_class=HTMLResponse)
async def workflow_detail(request: Request, workflow_id: UUID) -> HTMLResponse:
    async with get_db(request.app.state.settings) as db:
        return await detail_page(request, db, str(workflow_id))


@router.get("/{workflow_id}/edit", response_class=HTMLResponse)
async def edit_workflow(request: Request, workflow_id: UUID) -> HTMLResponse:
    async with get_db(request.app.state.settings) as db:
        workflow = await WorkflowService(db).require_workflow(str(workflow_id))
        return await workspace(
            request,
            db,
            view="workflow_editor",
            selected_id=str(workflow_id),
            title=f"Edit {workflow['name']}",
            workflow=workflow,
        )


@router.put("/{workflow_id}", response_class=HTMLResponse)
@router.post("/{workflow_id}/save", response_class=HTMLResponse)
async def update_workflow(
    request: Request,
    workflow_id: UUID,
    name: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    project_id: Annotated[str, Form()] = "",
    category_id: Annotated[str, Form()] = "",
    status: Annotated[str, Form()] = "draft",
    tags: Annotated[str, Form()] = "",
    label_ids: Annotated[list[str] | None, Form()] = None,
    expected_updated_at: Annotated[str, Form()] = "",
) -> HTMLResponse:
    identity = str(workflow_id)
    async with get_db(request.app.state.settings, write=True) as db:
        service = WorkflowService(db)
        workflow = await service.require_workflow(identity)
        if expected_updated_at and workflow["updated_at"] != expected_updated_at:
            raise ConflictError(
                "This workflow changed elsewhere. Copy your edits before reloading."
            )
        await service.update_workflow(
            identity, name, description, project_id, category_id, status, tag_names(tags)
        )
        await LabelService(db).set_labels("workflow", identity, label_ids or [])
        await db.commit()
        return await detail_page(request, db, identity, "Workflow saved.")


@router.delete("/{workflow_id}", response_class=HTMLResponse)
@router.post("/{workflow_id}/delete", response_class=HTMLResponse)
async def delete_workflow(request: Request, workflow_id: UUID) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        await WorkflowService(db).delete_workflow(str(workflow_id))
        await db.commit()
        return await workspace(request, db, path="/", message="Workflow and its runs deleted.")


@router.post("/{workflow_id}/favourite", response_class=HTMLResponse)
async def favourite_workflow(request: Request, workflow_id: UUID) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        await WorkflowService(db).toggle_favourite(str(workflow_id))
        await db.commit()
        return await detail_page(request, db, str(workflow_id))


@router.post("/{workflow_id}/stages", response_class=HTMLResponse)
async def add_stage(
    request: Request,
    workflow_id: UUID,
    title: Annotated[str, Form()],
    body: Annotated[str, Form()] = "",
    instructions: Annotated[str, Form()] = "",
    mode: Annotated[str, Form()] = "standard",
    output_type: Annotated[str, Form()] = "text",
    prompt_id: Annotated[str, Form()] = "",
    link_prompt: Annotated[bool, Form()] = False,
) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        await WorkflowService(db).add_stage(
            str(workflow_id),
            title,
            body,
            instructions,
            mode=mode,
            output_type=output_type,
            prompt_id=prompt_id or None,
            link_prompt=link_prompt,
        )
        await db.commit()
        return await detail_page(request, db, str(workflow_id), "Stage added.")


@router.put("/{workflow_id}/stages/{stage_id}", response_class=HTMLResponse)
@router.post("/{workflow_id}/stages/{stage_id}/save", response_class=HTMLResponse)
async def update_stage(
    request: Request,
    workflow_id: UUID,
    stage_id: UUID,
    title: Annotated[str, Form()],
    body: Annotated[str | None, Form()] = None,
    instructions: Annotated[str, Form()] = "",
    mode: Annotated[str, Form()] = "standard",
    output_type: Annotated[str, Form()] = "text",
    detach_prompt: Annotated[bool, Form()] = False,
) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        service = WorkflowService(db)
        await service.require_stage(str(stage_id), str(workflow_id))
        # An omitted disabled field preserves a live reference; an empty posted body clears it.
        posted = await request.form()
        new_body = str(posted["body"]) if "body" in posted else None
        await service.update_stage(
            str(stage_id),
            title=title,
            body=new_body,
            instructions=instructions,
            mode=mode,
            output_type=output_type,
            detach=detach_prompt,
        )
        await db.commit()
        return await detail_page(request, db, str(workflow_id), "Stage saved.")


@router.post("/{workflow_id}/stages/{stage_id}/move", response_class=HTMLResponse)
async def move_stage(
    request: Request,
    workflow_id: UUID,
    stage_id: UUID,
    position: Annotated[int, Form()],
) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        service = WorkflowService(db)
        await service.require_stage(str(stage_id), str(workflow_id))
        await service.reorder_stage(str(stage_id), position)
        await db.commit()
        return await detail_page(request, db, str(workflow_id), "Stage order updated.")


@router.delete("/{workflow_id}/stages/{stage_id}", response_class=HTMLResponse)
@router.post("/{workflow_id}/stages/{stage_id}/delete", response_class=HTMLResponse)
async def remove_stage(request: Request, workflow_id: UUID, stage_id: UUID) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        service = WorkflowService(db)
        await service.require_stage(str(stage_id), str(workflow_id))
        await service.delete_stage(str(stage_id))
        await db.commit()
        return await detail_page(request, db, str(workflow_id), "Stage deleted.")


# These paths retain compatibility with pre-v1 stage clients.
@router.put("/stages/{stage_id}", response_class=HTMLResponse)
async def legacy_update_stage(
    request: Request,
    stage_id: UUID,
    title: Annotated[str, Form()],
    body: Annotated[str | None, Form()] = None,
    instructions: Annotated[str, Form()] = "",
    mode: Annotated[str, Form()] = "standard",
    output_type: Annotated[str, Form()] = "text",
) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        service = WorkflowService(db)
        stage = await service.require_stage(str(stage_id))
        # An omitted disabled field preserves a live reference; an empty posted body clears it.
        posted = await request.form()
        new_body = str(posted["body"]) if "body" in posted else None
        await service.update_stage(
            str(stage_id),
            title=title,
            body=new_body,
            instructions=instructions,
            mode=mode,
            output_type=output_type,
        )
        await db.commit()
        return await detail_page(request, db, stage["workflow_id"], "Stage saved.")


@router.delete("/stages/{stage_id}", response_class=HTMLResponse)
async def legacy_remove_stage(request: Request, stage_id: UUID) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        service = WorkflowService(db)
        stage = await service.require_stage(str(stage_id))
        await service.delete_stage(str(stage_id))
        await db.commit()
        return await detail_page(request, db, stage["workflow_id"], "Stage deleted.")


@router.post("/{workflow_id}/runs", response_class=HTMLResponse)
async def start_run(request: Request, workflow_id: UUID) -> HTMLResponse:
    form = await request.form()
    inputs = {name[6:]: str(value) for name, value in form.items() if name.startswith("input:")}
    async with get_db(request.app.state.settings, write=True) as db:
        service = RunService(db)
        identity = await service.start(str(workflow_id), inputs)
        await db.commit()
        run = await service.get_run(identity)
        return await workspace(
            request,
            db,
            view="run_detail",
            selected_id=str(workflow_id),
            title=run["snapshot"]["name"],
            path=f"/workflows/runs/{identity}",
            run=run,
            message="Run started. Complete each stage in your chosen tool.",
        )
