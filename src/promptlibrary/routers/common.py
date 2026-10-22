"""Shared page context and navigation for server-rendered routes."""

from urllib.parse import urlencode

import aiosqlite
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from promptlibrary import __version__
from promptlibrary.services.library_service import LibraryFilter, LibraryService
from promptlibrary.services.project_service import LabelService, ProjectService
from promptlibrary.services.prompt_service import PromptService
from promptlibrary.services.status_service import StatusService
from promptlibrary.services.validation import NotFoundError, Record


def filters_from_request(request: Request) -> LibraryFilter:
    values = dict(request.query_params)
    if "category" in values and "category_id" not in values:
        values["category_id"] = values["category"]
    if "project" in values and "project_id" not in values:
        values["project_id"] = values["project"]
    if values.get("filter") == "favourites":
        values["favourites_only"] = "true"
    elif values.get("filter"):
        values.setdefault("status", values["filter"])
    return LibraryFilter.model_validate(values)


def filtered_path(path: str, filters: LibraryFilter) -> str:
    values = filters.model_dump(exclude_defaults=True)
    query = urlencode(values)
    return path + ("?" + query if query else "")


def page(
    request: Request,
    template: str,
    context: Record | None = None,
    *,
    title: str = "PromptLibrary",
    section: str = "library",
    url: str | None = None,
    message: str | None = None,
) -> HTMLResponse:
    if request.method not in {"GET", "HEAD"} and request.headers.get("X-Fragment") != "1" and url:
        return HTMLResponse("", status_code=303, headers={"Location": url})
    templates: Jinja2Templates = request.app.state.templates
    values: Record = {
        "version": __version__,
        "page_title": title,
        "section": section,
        "fragment": request.headers.get("X-Fragment") == "1",
    }
    values.update(context or {})
    response = templates.TemplateResponse(request, template, values)
    response.headers["X-Page-URL"] = url or str(request.url.path)
    if message:
        response.headers["X-Message"] = message
    return response


async def workspace(
    request: Request,
    db: aiosqlite.Connection,
    *,
    view: str = "empty",
    selected_id: str = "",
    title: str = "Library",
    path: str | None = None,
    message: str | None = None,
    filters: LibraryFilter | None = None,
    **detail: Record | str | list[Record] | list[str] | bool,
) -> HTMLResponse:
    filters = filters or filters_from_request(request)
    items, total = await LibraryService(db).list_items(filters)
    context: Record = {
        "items": items,
        "total": total,
        "filters": filters,
        "page_size": LibraryService.PAGE_SIZE,
        "selected_id": selected_id,
        "view": view,
        "categories": await PromptService(db).list_categories(),
        "tags": await PromptService(db).list_tags(),
        "projects": await ProjectService(db).list_projects(include_archived=True),
        "labels": await LabelService(db).list_labels(),
        "statuses": await StatusService(db).list_statuses(),
    }
    context.update(detail)
    if view == "prompt_detail":
        cursor = await db.execute("SELECT id,name FROM workflows ORDER BY name COLLATE NOCASE")
        context["workflows_for_prompt"] = [dict(row) for row in await cursor.fetchall()]
    context["filter_path"] = path or request.url.path
    context["query_suffix"] = filtered_path("", filters)
    context["previous_page"] = filtered_path(
        path or "/",
        filters.model_copy(update={"page": max(1, filters.page - 1)}),
    )
    context["next_page"] = filtered_path(
        path or "/",
        filters.model_copy(update={"page": filters.page + 1}),
    )
    context["status_map"] = {row["key"]: row for row in context["statuses"]}
    context["project_map"] = {row["id"]: row for row in context["projects"]}
    context["category_map"] = {row["id"]: row for row in context["categories"]}
    return page(
        request,
        "pages/workspace.html",
        context,
        title=f"{title} | PromptLibrary",
        url=filtered_path(path or request.url.path, filters),
        message=message,
    )


async def require_prompt(db: aiosqlite.Connection, prompt_id: str) -> Record:
    prompt = await PromptService(db).get_prompt(prompt_id)
    if prompt is None:
        raise NotFoundError("Prompt not found.")
    prompt["labels"] = await LabelService(db).get_prompt_labels(prompt_id)
    return prompt


def tag_names(value: str) -> list[str]:
    return list(dict.fromkeys(name.strip() for name in value.split(",") if name.strip()))
