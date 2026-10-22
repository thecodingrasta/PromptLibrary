"""Project management and links to the unified project library."""

from typing import Annotated
from uuid import UUID

import aiosqlite
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from promptlibrary.database import get_db
from promptlibrary.routers.common import page, workspace
from promptlibrary.services.library_service import LibraryFilter
from promptlibrary.services.project_service import ProjectService
from promptlibrary.services.validation import NotFoundError

router = APIRouter(prefix="/projects", tags=["projects"])


async def project_page(
    request: Request, db: aiosqlite.Connection, message: str | None = None
) -> HTMLResponse:
    return page(
        request,
        "pages/projects.html",
        {"projects": await ProjectService(db).list_projects(include_archived=True)},
        title="Projects | PromptLibrary",
        section="projects",
        url="/projects",
        message=message,
    )


@router.get("", response_class=HTMLResponse)
async def list_projects(request: Request) -> HTMLResponse:
    async with get_db(request.app.state.settings) as db:
        return await project_page(request, db)


@router.get("/{project_id}", response_class=HTMLResponse)
async def view_project(request: Request, project_id: UUID) -> HTMLResponse:
    async with get_db(request.app.state.settings) as db:
        project = await ProjectService(db).get_project(str(project_id))
        if project is None:
            raise NotFoundError("Project not found.")
        return await workspace(
            request,
            db,
            title=project["name"],
            path="/",
            filters=LibraryFilter(project_id=str(project_id)),
        )


@router.post("", response_class=HTMLResponse)
async def create_project(
    request: Request,
    name: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    colour: Annotated[str, Form()] = "#6366f1",
) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        await ProjectService(db).create_project(name, description, colour)
        await db.commit()
        return await project_page(request, db, "Project created.")


@router.put("/{project_id}", response_class=HTMLResponse)
@router.post("/{project_id}/save", response_class=HTMLResponse)
async def update_project(
    request: Request,
    project_id: UUID,
    name: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    colour: Annotated[str, Form()] = "#6366f1",
) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        await ProjectService(db).update_project(
            str(project_id), name=name, description=description, colour=colour
        )
        await db.commit()
        return await project_page(request, db, "Project saved.")


@router.post("/{project_id}/archive", response_class=HTMLResponse)
async def archive_project(request: Request, project_id: UUID) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        await ProjectService(db).archive_project(str(project_id))
        await db.commit()
        return await project_page(request, db, "Project archived. Its items remain available.")


@router.post("/{project_id}/unarchive", response_class=HTMLResponse)
async def unarchive_project(request: Request, project_id: UUID) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        await ProjectService(db).update_project(str(project_id), is_archived=False)
        await db.commit()
        return await project_page(request, db, "Project restored.")


@router.delete("/{project_id}", response_class=HTMLResponse)
@router.post("/{project_id}/delete", response_class=HTMLResponse)
async def delete_project(request: Request, project_id: UUID) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        await ProjectService(db).delete_project(str(project_id))
        await db.commit()
        return await project_page(
            request, db, "Project deleted. Its prompts and workflows are now unassigned."
        )
