"""User-managed status definitions, labels and categories."""

from typing import Annotated
from uuid import UUID

import aiosqlite
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from promptlibrary.database import get_db
from promptlibrary.routers.common import page
from promptlibrary.services.category_service import CategoryService
from promptlibrary.services.project_service import LABEL_TYPES, LabelService
from promptlibrary.services.prompt_service import PromptService
from promptlibrary.services.status_service import StatusService

router = APIRouter(tags=["settings"])


async def settings_page(
    request: Request, db: aiosqlite.Connection, message: str | None = None
) -> HTMLResponse:
    return page(
        request,
        "pages/settings.html",
        {
            "statuses": await StatusService(db).list_statuses(),
            "categories": await PromptService(db).list_categories(),
            "labels": await LabelService(db).list_labels(),
            "label_types": LABEL_TYPES,
            "data_directory": str(request.app.state.settings.data_dir),
        },
        title="Settings | PromptLibrary",
        section="settings",
        url="/settings",
        message=message,
    )


@router.get("/settings", response_class=HTMLResponse)
@router.get("/categories", response_class=HTMLResponse)
@router.get("/categories/manage", response_class=HTMLResponse)
async def show_settings(request: Request) -> HTMLResponse:
    async with get_db(request.app.state.settings) as db:
        return await settings_page(request, db)


@router.post("/settings/statuses", response_class=HTMLResponse)
async def add_status(
    request: Request,
    name: Annotated[str, Form()],
    colour: Annotated[str, Form()] = "#6366f1",
    sort_order: Annotated[int, Form()] = 0,
) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        await StatusService(db).save_status(name, colour, sort_order)
        await db.commit()
        return await settings_page(request, db, "Status created.")


@router.post("/settings/statuses/{key}/save", response_class=HTMLResponse)
async def save_status(
    request: Request,
    key: str,
    name: Annotated[str, Form()],
    colour: Annotated[str, Form()] = "#6366f1",
    sort_order: Annotated[int, Form()] = 0,
) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        await StatusService(db).save_status(name, colour, sort_order, key)
        await db.commit()
        return await settings_page(request, db, "Status saved.")


@router.post("/settings/statuses/{key}/delete", response_class=HTMLResponse)
async def delete_status(request: Request, key: str) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        await StatusService(db).delete_status(key)
        await db.commit()
        return await settings_page(request, db, "Status deleted.")


@router.post("/categories", response_class=HTMLResponse)
async def add_category(
    request: Request,
    name: Annotated[str, Form()],
    colour: Annotated[str, Form()] = "",
    parent_id: Annotated[str, Form()] = "",
) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        await CategoryService(db).create(name, parent_id or None, colour or None)
        await db.commit()
        return await settings_page(request, db, "Category created.")


@router.put("/categories/{category_id}", response_class=HTMLResponse)
@router.post("/categories/{category_id}/save", response_class=HTMLResponse)
async def save_category(
    request: Request,
    category_id: UUID,
    name: Annotated[str, Form()],
    colour: Annotated[str, Form()] = "",
    parent_id: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        await CategoryService(db).update(
            str(category_id),
            name,
            colour or None,
            parent_id or None,
            change_parent=parent_id is not None,
        )
        await db.commit()
        return await settings_page(request, db, "Category saved.")


@router.delete("/categories/{category_id}", response_class=HTMLResponse)
@router.post("/categories/{category_id}/delete", response_class=HTMLResponse)
async def delete_category(request: Request, category_id: UUID) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        await CategoryService(db).delete(str(category_id))
        await db.commit()
        return await settings_page(request, db, "Category deleted. Its items were not deleted.")


@router.post("/settings/labels", response_class=HTMLResponse)
async def add_label(
    request: Request,
    name: Annotated[str, Form()],
    label_type: Annotated[str, Form()] = "custom",
    colour: Annotated[str, Form()] = "#6366f1",
) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        await LabelService(db).create_label(name, label_type, colour)
        await db.commit()
        return await settings_page(request, db, "Label created.")


@router.post("/settings/labels/{label_id}/save", response_class=HTMLResponse)
async def save_label(
    request: Request,
    label_id: str,
    name: Annotated[str, Form()],
    label_type: Annotated[str, Form()] = "custom",
    colour: Annotated[str, Form()] = "#6366f1",
) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        await LabelService(db).update_label(label_id, name, label_type, colour)
        await db.commit()
        return await settings_page(request, db, "Label saved.")


@router.post("/settings/labels/{label_id}/delete", response_class=HTMLResponse)
async def delete_label(request: Request, label_id: str) -> HTMLResponse:
    async with get_db(request.app.state.settings, write=True) as db:
        await LabelService(db).delete_label(label_id)
        await db.commit()
        return await settings_page(request, db, "Label deleted and removed from its items.")
