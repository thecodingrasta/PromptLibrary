"""Agent operations use the same transactional services as the web application."""

from dataclasses import asdict
from typing import Annotated, Literal, cast
from uuid import uuid4

import aiosqlite
from pydantic import Field

from promptlibrary.config import Settings
from promptlibrary.mcp.registry import Identity, ItemId, Names, Text, Title, tool
from promptlibrary.services.category_service import CategoryService
from promptlibrary.services.export_service import ExportService, ImportMode
from promptlibrary.services.library_service import LibraryFilter, LibraryService
from promptlibrary.services.project_service import LabelService, ProjectService
from promptlibrary.services.prompt_service import PromptService
from promptlibrary.services.run_service import RunService
from promptlibrary.services.status_service import StatusService
from promptlibrary.services.sync_config_service import RemoteConfigInput, SyncConfigService
from promptlibrary.services.sync_service import SyncService
from promptlibrary.services.validation import ConflictError, NotFoundError, Record, title_value
from promptlibrary.services.version_service import VersionService
from promptlibrary.services.workflow_service import WorkflowService


async def require_prompt(db: aiosqlite.Connection, identity: str) -> Record:
    prompt = await PromptService(db).get_prompt(identity)
    if prompt is None:
        raise NotFoundError("Prompt not found.")
    prompt["labels"] = await LabelService(db).get_prompt_labels(identity)
    return prompt


@tool(read_only=True)
async def search_library(
    db: aiosqlite.Connection,
    query: str = "",
    item_type: Literal["", "prompt", "workflow"] = "",
    status: str = "",
    project_id: str = "",
    category_id: str = "",
    tag: str = "",
    favourites_only: bool = False,
    page: int = 1,
) -> Record:
    """Search prompts and workflows together. Returns at most 100 items, total and page."""
    items, total = await LibraryService(db).list_items(
        LibraryFilter(
            q=query,
            item_type=item_type,
            status=status,
            project_id=project_id,
            category_id=category_id,
            tag=tag,
            favourites_only=favourites_only,
            page=page,
        )
    )
    return {"items": items, "total": total, "page": page}


@tool(read_only=True)
async def search_prompts(
    db: aiosqlite.Connection,
    query: str = "",
    tag: str = "",
    status: str = "",
    favourites_only: bool = False,
    project_id: str = "",
    category_id: str = "",
    page: int = 1,
) -> list[Record]:
    """Find prompts, up to 100 per page. Use get_prompt to retrieve full content."""
    result = await search_library(
        db,
        query=query,
        item_type="prompt",
        tag=tag,
        status=status,
        favourites_only=favourites_only,
        project_id=project_id,
        category_id=category_id,
        page=page,
    )
    return cast(list[Record], result["items"])


@tool(read_only=True)
async def get_prompt(db: aiosqlite.Connection, item_id: ItemId) -> Record:
    """Read a prompt's complete content, notes and metadata."""
    return await require_prompt(db, item_id)


@tool(read_only=True)
async def get_prompt_by_title(db: aiosqlite.Connection, title: Title) -> Record:
    """Resolve an exact or unique partial title. Ambiguous matches are refused."""
    cursor = await db.execute(
        "SELECT id FROM prompts WHERE title=? COLLATE NOCASE LIMIT 2", (title,)
    )
    rows = list(await cursor.fetchall())
    if not rows:
        cursor = await db.execute(
            "SELECT id FROM prompts WHERE instr(lower(title),lower(?))>0 LIMIT 2", (title,)
        )
        rows = list(await cursor.fetchall())
    if not rows:
        raise NotFoundError("No prompt matches that title.")
    if len(rows) > 1:
        raise ConflictError("Several prompts match that title. Search and use an explicit ID.")
    return await require_prompt(db, rows[0][0])


@tool()
async def create_prompt(
    db: aiosqlite.Connection,
    title: Title,
    body: Text,
    notes: Text = "",
    status: str = "draft",
    tags: Names | None = None,
    category: str | None = None,
    category_id: str | None = None,
    project_id: str | None = None,
    label_ids: Names | None = None,
) -> Record:
    """Create a prompt and its initial version. Category names can be created on demand."""
    if category and category_id:
        raise ValueError("Supply category or category_id, not both.")
    if category:
        cursor = await db.execute(
            "SELECT id FROM categories WHERE name=? COLLATE NOCASE LIMIT 2", (category,)
        )
        matches = list(await cursor.fetchall())
        if len(matches) > 1:
            raise ConflictError("Category name is ambiguous. Use category_id.")
        category_id = matches[0][0] if matches else await CategoryService(db).create(category)
    identity = str(uuid4())
    await PromptService(db).create_prompt(
        identity, title, body, notes, status, category_id, project_id, tags
    )
    await VersionService(db).create_version(identity, body, notes, status, "Created via MCP")
    await LabelService(db).set_labels("prompt", identity, label_ids or [])
    return {"id": identity, "title": title.strip(), "status": "created"}


@tool()
async def update_prompt(
    db: aiosqlite.Connection,
    item_id: ItemId,
    title: Title | None = None,
    body: Text | None = None,
    notes: Text | None = None,
    status: str | None = None,
    tags: Names | None = None,
    message: str = "Updated via MCP",
    category_id: str | None = None,
    project_id: str | None = None,
    label_ids: Names | None = None,
    expected_updated_at: str | None = None,
) -> Record:
    """Update supplied fields and create a version. Empty project/category IDs unassign them. Pass
    expected_updated_at to reject stale edits."""
    prompt = await require_prompt(db, item_id)
    title = prompt["title"] if title is None else title
    body = prompt["body"] if body is None else body
    notes = prompt["notes"] if notes is None else notes
    status = prompt["status"] if status is None else status
    category_id = prompt["category_id"] if category_id is None else category_id or None
    await PromptService(db).update_prompt(
        item_id,
        title,
        body,
        notes,
        status,
        category_id,
        tags,
        project_id,
        expected_updated_at=expected_updated_at,
    )
    await VersionService(db).create_version(item_id, body, notes, status, message)
    if label_ids is not None:
        await LabelService(db).set_labels("prompt", item_id, label_ids)
    return {"id": item_id, "status": "updated"}


@tool(destructive=True)
async def delete_prompt(db: aiosqlite.Connection, item_id: ItemId) -> Record:
    """Delete a prompt and history. Linked workflow stages must be detached first."""
    await PromptService(db).delete_prompt(item_id)
    return {"id": item_id, "status": "deleted"}


@tool()
async def publish_prompt(db: aiosqlite.Connection, item_id: ItemId) -> Record:
    """Set the stable published status and record a new version."""
    await update_prompt(db, item_id, status="published", message="Published via MCP")
    return {"id": item_id, "status": "published"}


@tool()
async def bulk_update_status(
    db: aiosqlite.Connection,
    ids: Annotated[list[str], Field(min_length=1, max_length=100)],
    status: str,
) -> Record:
    """Update up to 100 prompts atomically. A missing prompt rolls back the entire batch."""
    for identity in dict.fromkeys(ids):
        await update_prompt(db, identity, status=status, message="Bulk status change via MCP")
    return {"updated": len(set(ids)), "status": status}


@tool()
async def toggle_favourite(db: aiosqlite.Connection, item_id: ItemId) -> Record:
    """Toggle a prompt's favourite flag and return its current state."""
    return {"id": item_id, "is_favourite": await PromptService(db).toggle_favourite(item_id)}


@tool(read_only=True)
async def get_version_history(db: aiosqlite.Connection, item_id: ItemId) -> list[Record]:
    """Read saved prompt body, notes and status versions, newest first."""
    await require_prompt(db, item_id)
    return await VersionService(db).list_versions(item_id)


@tool(read_only=True)
async def get_version_diff(
    db: aiosqlite.Connection, item_id: ItemId, version: Annotated[int, Field(ge=1)]
) -> Record:
    """Compare a saved version with its predecessor."""
    service = VersionService(db)
    if await service.get_version(item_id, version) is None:
        raise NotFoundError("Version not found.")
    return {"version": version, "diff": await service.get_diff(item_id, version)}


@tool()
async def restore_version(
    db: aiosqlite.Connection, item_id: ItemId, version: Annotated[int, Field(ge=1)]
) -> Record:
    """Restore body, notes and status, keeping a new version of the restoration."""
    await VersionService(db).restore_version(item_id, version)
    return {"id": item_id, "restored_to": version}


@tool(destructive=True)
async def clear_version_history(db: aiosqlite.Connection, item_id: ItemId) -> Record:
    """Permanently clear history without altering the current prompt. Backups are unchanged."""
    await require_prompt(db, item_id)
    return {"id": item_id, "deleted_versions": await VersionService(db).clear_history(item_id)}


@tool(read_only=True)
async def list_categories(db: aiosqlite.Connection) -> list[Record]:
    """List categories and their stable IDs."""
    return await PromptService(db).list_categories()


@tool()
async def create_category(
    db: aiosqlite.Connection, name: Title, colour: str | None = None, parent_id: str | None = None
) -> Record:
    """Create a category, optionally beneath an existing category."""
    return {
        "id": await CategoryService(db).create(name, parent_id, colour),
        "name": name,
        "status": "created",
    }


@tool()
async def update_category(
    db: aiosqlite.Connection,
    item_id: ItemId,
    name: Title,
    colour: str | None = None,
    parent_id: str | None = None,
) -> Record:
    """Update a category. Empty parent_id makes it a root category."""
    await CategoryService(db).update(
        item_id, name, colour, parent_id or None, change_parent=parent_id is not None
    )
    return {"id": item_id, "status": "updated"}


@tool(destructive=True)
async def delete_category(db: aiosqlite.Connection, item_id: ItemId) -> Record:
    """Delete a category; its items and children remain, without that category/parent."""
    await CategoryService(db).delete(item_id)
    return {"id": item_id, "status": "deleted"}


@tool(read_only=True)
async def list_tags(db: aiosqlite.Connection) -> list[Record]:
    """List tags used by prompts and workflows."""
    return await PromptService(db).list_tags()


@tool()
async def rename_tag(db: aiosqlite.Connection, old_name: str, new_name: Title) -> Record:
    """Rename a tag across both prompts and workflows."""
    new_name = title_value(new_name, 50)
    if "," in new_name:
        raise ValueError("Tags cannot contain commas.")
    cursor = await db.execute("UPDATE tags SET name=? WHERE name=?", (new_name, old_name))
    if not cursor.rowcount:
        raise NotFoundError("Tag not found.")
    return {"old_name": old_name, "new_name": new_name, "status": "renamed"}


@tool(destructive=True)
async def delete_tag(db: aiosqlite.Connection, name: str) -> Record:
    """Remove a tag and all its assignments. Prompts and workflows remain."""
    cursor = await db.execute("DELETE FROM tags WHERE name=?", (name,))
    if not cursor.rowcount:
        raise NotFoundError("Tag not found.")
    return {"name": name, "status": "deleted"}


@tool(read_only=True)
async def list_statuses(db: aiosqlite.Connection) -> list[Record]:
    """List default and custom status keys, names, colours and order."""
    return await StatusService(db).list_statuses()


@tool()
async def save_status(
    db: aiosqlite.Connection,
    name: Title,
    colour: str = "#6366f1",
    sort_order: int = 0,
    key: str | None = None,
) -> Record:
    """Create a status, or edit its name/colour/order by stable key."""
    return {"key": await StatusService(db).save_status(name, colour, sort_order, key)}


@tool(destructive=True)
async def delete_status(db: aiosqlite.Connection, key: str) -> Record:
    """Delete an unused custom status. Default or referenced statuses are protected."""
    await StatusService(db).delete_status(key)
    return {"key": key, "status": "deleted"}


@tool(read_only=True)
async def list_projects(db: aiosqlite.Connection, include_archived: bool = False) -> list[Record]:
    """List projects with prompt and workflow counts."""
    return await ProjectService(db).list_projects(include_archived)


@tool()
async def create_project(
    db: aiosqlite.Connection,
    name: Title,
    description: Text = "",
    colour: str | None = None,
    icon: str | None = None,
) -> Record:
    """Create a project to organise prompts and workflows."""
    return {
        "id": await ProjectService(db).create_project(name, description, colour, icon),
        "name": name,
        "status": "created",
    }


@tool()
async def update_project(
    db: aiosqlite.Connection,
    item_id: ItemId,
    name: Title | None = None,
    description: Text | None = None,
    colour: str | None = None,
    icon: str | None = None,
    is_archived: bool | None = None,
) -> Record:
    """Edit, archive or unarchive a project without changing its items."""
    await ProjectService(db).update_project(
        item_id,
        name=name,
        description=description,
        colour=colour,
        icon=icon,
        is_archived=is_archived,
    )
    return {"id": item_id, "status": "updated"}


@tool(destructive=True)
async def delete_project(db: aiosqlite.Connection, item_id: ItemId) -> Record:
    """Delete a project. Its prompts and workflows remain unassigned."""
    await ProjectService(db).delete_project(item_id)
    return {"id": item_id, "status": "deleted"}


@tool(read_only=True)
async def list_labels(
    db: aiosqlite.Connection, label_type: Annotated[str | None, Field(alias="type")] = None
) -> list[Record]:
    """List labels, optionally filtered by language, framework, platform, model or custom."""
    return await LabelService(db).list_labels(label_type)


@tool()
async def create_label(
    db: aiosqlite.Connection,
    name: Title,
    label_type: str = "custom",
    colour: str | None = None,
    icon: str | None = None,
) -> Record:
    """Create a typed label for prompts and workflows."""
    return {"id": await LabelService(db).create_label(name, label_type, colour, icon)}


@tool()
async def update_label(
    db: aiosqlite.Connection,
    item_id: ItemId,
    name: Title,
    label_type: str = "custom",
    colour: str | None = None,
    icon: str | None = None,
) -> Record:
    """Update an existing label's metadata."""
    await LabelService(db).update_label(item_id, name, label_type, colour, icon)
    return {"id": item_id, "status": "updated"}


@tool(destructive=True)
async def delete_label(db: aiosqlite.Connection, item_id: ItemId) -> Record:
    """Delete a label and assignments, keeping the labelled items."""
    await LabelService(db).delete_label(item_id)
    return {"id": item_id, "status": "deleted"}


@tool()
async def assign_labels(db: aiosqlite.Connection, prompt_id: Identity, labels: Names) -> Record:
    """Add existing labels to a prompt by name. Unknown labels reject the whole change."""
    service = LabelService(db)
    await require_prompt(db, prompt_id)
    assigned: list[str] = []
    for name in dict.fromkeys(labels):
        label = await service.find_label_by_name(name)
        if label is None:
            raise NotFoundError("Unknown label: " + name)
        await service.assign_label_to_prompt(prompt_id, label["id"])
        assigned.append(name)
    return {"assigned": assigned}


@tool()
async def set_labels(
    db: aiosqlite.Connection,
    item_id: ItemId,
    item_type: Literal["prompt", "workflow"],
    label_ids: Names,
) -> Record:
    """Replace an item's complete label assignment. An empty list removes all labels."""
    await LabelService(db).set_labels(item_type, item_id, label_ids)
    return {"id": item_id, "status": "updated"}


@tool(read_only=True)
async def list_workflows(
    db: aiosqlite.Connection, search: str = "", project_id: str = "", page: int = 1
) -> list[Record]:
    """List up to 100 matching workflows per page. Use get_workflow for stages and metadata."""
    result = await search_library(
        db, query=search, item_type="workflow", project_id=project_id, page=page
    )
    return cast(list[Record], result["items"])


@tool(read_only=True)
async def get_workflow(db: aiosqlite.Connection, item_id: ItemId) -> Record:
    """Read a workflow and its ordered stages, resolving linked prompt bodies."""
    return await WorkflowService(db).require_workflow(item_id)


@tool()
async def create_workflow(
    db: aiosqlite.Connection,
    name: Title,
    description: Text = "",
    project_id: str | None = None,
    category_id: str | None = None,
    status: str = "draft",
    tags: Names | None = None,
    label_ids: Names | None = None,
) -> Record:
    """Create a workflow. Add its stages separately or compose them from existing prompts."""
    identity = await WorkflowService(db).create_workflow(
        name, description, project_id, category_id, status, tags
    )
    await LabelService(db).set_labels("workflow", identity, label_ids or [])
    return {"id": identity, "status": "created"}


@tool()
async def update_workflow(
    db: aiosqlite.Connection,
    item_id: ItemId,
    name: Title | None = None,
    description: Text | None = None,
    project_id: str | None = None,
    category_id: str | None = None,
    status: str | None = None,
    tags: Names | None = None,
    label_ids: Names | None = None,
    expected_updated_at: str | None = None,
) -> Record:
    """Edit supplied workflow fields. Empty project/category IDs unassign them; optional timestamp
    guards stale edits."""
    service = WorkflowService(db)
    current = await service.require_workflow(item_id)
    if expected_updated_at is not None and expected_updated_at != current["updated_at"]:
        raise ConflictError("The workflow changed. Read it again before updating.")
    await service.update_workflow(item_id, name, description, project_id, category_id, status, tags)
    if label_ids is not None:
        await LabelService(db).set_labels("workflow", item_id, label_ids)
    return {"id": item_id, "status": "updated"}


@tool(destructive=True)
async def delete_workflow(db: aiosqlite.Connection, item_id: ItemId) -> Record:
    """Delete a workflow, its stages and run history. Source prompts remain."""
    await WorkflowService(db).delete_workflow(item_id)
    return {"id": item_id, "status": "deleted"}


@tool()
async def toggle_workflow_favourite(db: aiosqlite.Connection, item_id: ItemId) -> Record:
    """Toggle a workflow's favourite flag."""
    return {"id": item_id, "is_favourite": await WorkflowService(db).toggle_favourite(item_id)}


@tool()
async def add_workflow_stage(
    db: aiosqlite.Connection,
    workflow_id: Identity,
    title: Title,
    body: Text = "",
    instructions: Text = "",
    mode: str = "standard",
    output_type: str = "text",
    prompt_id: str | None = None,
    link_prompt: bool = False,
) -> Record:
    """Append a stage. prompt_id copies its body, or live-links it when link_prompt is true."""
    identity = await WorkflowService(db).add_stage(
        workflow_id,
        title,
        body,
        instructions,
        mode=mode,
        output_type=output_type,
        prompt_id=prompt_id,
        link_prompt=link_prompt,
    )
    return {"id": identity, "status": "added"}


@tool()
async def update_workflow_stage(
    db: aiosqlite.Connection,
    stage_id: Identity,
    title: Title | None = None,
    body: Text | None = None,
    instructions: Text | None = None,
    mode: str | None = None,
    output_type: str | None = None,
    detach: bool = False,
) -> Record:
    """Edit stage metadata/content. Set detach to turn a live link into a copy before editing its
    body."""
    await WorkflowService(db).update_stage(
        stage_id, title, body, instructions, mode=mode, output_type=output_type, detach=detach
    )
    return {"id": stage_id, "status": "updated"}


@tool()
async def reorder_workflow_stage(
    db: aiosqlite.Connection, stage_id: Identity, position: Annotated[int, Field(ge=1)]
) -> Record:
    """Move a stage to a one-based position. Invalid dependencies are rejected; valid references are
    renumbered."""
    await WorkflowService(db).reorder_stage(stage_id, position)
    return {"id": stage_id, "position": position}


@tool(destructive=True)
async def delete_workflow_stage(db: aiosqlite.Connection, stage_id: Identity) -> Record:
    """Delete a stage and renumber safely. Stages whose outputs are referenced cannot be deleted."""
    await WorkflowService(db).delete_stage(stage_id)
    return {"id": stage_id, "status": "deleted"}


@tool(read_only=True)
async def render_workflow_stage(
    db: aiosqlite.Connection,
    workflow_id: Identity,
    stage_number: Annotated[int, Field(ge=1)],
    variables: dict[str, str] | None = None,
) -> Record:
    """Render a stage without running a model. Unprovided placeholders remain visible."""
    service = WorkflowService(db)
    workflow = await service.require_workflow(workflow_id)
    if stage_number > len(workflow["stages"]):
        raise NotFoundError("Stage not found.")
    stage = workflow["stages"][stage_number - 1]
    return {
        "rendered_body": service.render_stage(stage, variables),
        "instructions": stage["instructions"],
        "mode": stage["mode"],
        "output_type": stage["output_type"],
    }


@tool()
async def start_workflow_run(
    db: aiosqlite.Connection, workflow_id: Identity, variables: dict[str, str] | None = None
) -> Record:
    """Start a guided run with immutable stage/input snapshots. This does not perform inference."""
    identity = await RunService(db).start(workflow_id, variables or {})
    return await RunService(db).get_run(identity)


@tool(read_only=True)
async def get_workflow_run(db: aiosqlite.Connection, item_id: ItemId) -> Record:
    """Read run history and the currently rendered stage, including prior saved outputs."""
    return await RunService(db).get_run(item_id)


@tool(read_only=True)
async def list_workflow_runs(db: aiosqlite.Connection, workflow_id: Identity) -> list[Record]:
    """List a workflow's running, completed and cancelled runs."""
    await WorkflowService(db).require_workflow(workflow_id)
    return await RunService(db).list_runs(workflow_id)


@tool()
async def complete_workflow_step(
    db: aiosqlite.Connection,
    run_id: Identity,
    expected_stage: Annotated[int, Field(ge=1)],
    output: Text,
) -> Record:
    """Capture one stage output. Reject duplicate or stale submissions."""
    return await RunService(db).complete_step(run_id, expected_stage, output)


@tool()
async def cancel_workflow_run(db: aiosqlite.Connection, item_id: ItemId) -> Record:
    """Cancel a running workflow while preserving saved inputs and outputs."""
    await RunService(db).cancel(item_id)
    return {"id": item_id, "status": "cancelled"}


@tool(read_only=True)
async def export_library(
    db: aiosqlite.Connection, file_format: Literal["json", "xml"] = "json"
) -> Record:
    """Export complete portable content. Machine-local credentials/settings are excluded. Prefer
    HTTP downloads for large libraries."""
    service = ExportService(db)
    content = (
        await service.export_xml()
        if file_format == "xml"
        else (await service.export_all()).model_dump_json(indent=2)
    )
    service._check_size(content)
    return {"format": file_format, "content": content}


@tool(destructive=True)
async def import_library(
    db: aiosqlite.Connection,
    content: str,
    file_format: Literal["json", "xml"] = "json",
    mode: ImportMode = "merge",
) -> Record:
    """Import up to 25 MiB atomically. Merge refuses conflicts; replace requires a full v2 snapshot
    and creates a safety backup."""
    service = ExportService(db)
    result = (
        await service.import_xml(content, mode)
        if file_format == "xml"
        else await service.import_json(content, mode)
    )
    return asdict(result)


@tool(read_only=True)
async def get_sync_config(db: aiosqlite.Connection, configuration: Settings) -> Record:
    """Read the selected remote without revealing stored credentials."""
    return (await SyncConfigService(db, configuration).load()).public_values()


@tool(destructive=True)
async def configure_sync(
    db: aiosqlite.Connection,
    configuration: Settings,
    remote: RemoteConfigInput,
    preserve_secrets: bool = True,
) -> Record:
    """Save machine-local remote configuration. Credentials are encrypted and never echoed. A new
    destination does not inherit old secrets."""
    service = SyncConfigService(db, configuration)
    await service.save(remote.model_dump(), preserve_secrets=preserve_secrets)
    return (await service.load()).public_values()


@tool(read_only=True, network=True)
async def test_sync_connection(db: aiosqlite.Connection, configuration: Settings) -> Record:
    """Check the destination using a temporary probe for local folders."""
    return {"connected": await SyncService(db, configuration).test_connection()}


@tool(destructive=True, network=True)
async def push_sync(db: aiosqlite.Connection, configuration: Settings) -> Record:
    """Overwrite the remote snapshot with current portable library content. This is not a
    multi-writer merge."""
    return asdict(await SyncService(db, configuration).push())


@tool(destructive=True, network=True)
async def pull_sync(
    db: aiosqlite.Connection, configuration: Settings, mode: ImportMode = "merge"
) -> Record:
    """Download a snapshot. Merge refuses conflicts; replace takes a safety backup and mirrors
    remote content/deletions."""
    return asdict(await SyncService(db, configuration).pull(mode))
