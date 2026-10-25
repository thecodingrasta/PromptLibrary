"""Integration tests for HTTP endpoints: widget, workflows, categories, full CRUD."""

import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("PROMPTLIB_DEBUG", "true")


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTLIB_DATA_DIR", str(tmp_path))
    from promptlibrary.config import Settings

    new_settings = Settings()
    monkeypatch.setattr("promptlibrary.config.settings", new_settings)
    monkeypatch.setattr("promptlibrary.database.settings", new_settings)
    from promptlibrary.database import init_db

    await init_db()
    from promptlibrary.app import create_app

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost", headers={"X-Fragment": "1"}
    ) as ac:
        yield ac


# === Widget ===


@pytest.mark.asyncio
async def test_widget_page(client):
    r = await client.get("/widget")
    assert r.status_code == 200
    assert "widget-bubble" in r.text
    assert "widget-panel" in r.text


@pytest.mark.asyncio
async def test_widget_recent(client):
    # Create a prompt first
    await client.post("/prompts", data={"title": "Widget Visible", "body": "test"})
    r = await client.get("/widget/recent")
    assert r.status_code == 200
    assert "Widget Visible" in r.text


@pytest.mark.asyncio
async def test_widget_search(client):
    await client.post("/prompts", data={"title": "Unique Widget Item", "body": "content"})
    r = await client.get("/widget/search?q=Unique+Widget")
    assert r.status_code == 200
    assert "Unique Widget Item" in r.text


# === Workflows ===


@pytest.mark.asyncio
async def test_workflow_list_empty(client):
    r = await client.get("/workflows")
    assert r.status_code == 200
    assert "No workflows yet" in r.text


@pytest.mark.asyncio
async def test_workflow_create(client):
    r = await client.post("/workflows", data={"name": "Test Workflow", "description": "A test"})
    assert r.status_code == 200
    assert "Test Workflow" in r.text


@pytest.mark.asyncio
async def test_workflow_add_stage(client):
    # Create workflow
    r = await client.post("/workflows", data={"name": "Stage Workflow"})
    assert r.status_code == 200

    # Get workflow ID from listing
    r = await client.get("/workflows")
    # Extract first workflow link (hx-get contains the UUID)
    import re

    match = re.search(r"/workflows/([a-f0-9-]+)", r.text)
    assert match, "No workflow found in listing"
    wf_id = match.group(1)

    # Add a stage
    r = await client.post(
        f"/workflows/{wf_id}/stages",
        data={
            "title": "Research Stage",
            "body": "Research {{TOPIC}}",
            "mode": "deep_research",
            "output_type": "markdown",
        },
    )
    assert r.status_code == 200
    assert "Research Stage" in r.text


@pytest.mark.asyncio
async def test_workflow_accepts_archive_output_type(client):
    response = await client.post(
        "/workflows",
        data={"name": "Archive workflow", "description": ""},
    )
    assert response.status_code == 200
    import re

    match = re.search(r"/workflows/([a-f0-9-]+)", response.text)
    assert match
    response = await client.post(
        f"/workflows/{match.group(1)}/stages",
        data={"title": "Archive stage", "output_type": "archive"},
    )
    assert response.status_code == 200
    assert "archive" in response.text


# === Categories (full CRUD via HTTP) ===


@pytest.mark.asyncio
async def test_categories_crud(client):
    # Create
    r = await client.post("/categories", data={"name": "HTTP Cat", "colour": "#ff0000"})
    assert r.status_code == 200
    assert "HTTP Cat" in r.text

    # List
    r = await client.get("/categories")
    assert r.status_code == 200
    assert "HTTP Cat" in r.text


# === Prompts (extended: project assignment, search, favourites) ===


@pytest.mark.asyncio
async def test_prompt_full_lifecycle(client):
    # Create
    r = await client.post(
        "/prompts",
        data={
            "title": "Lifecycle Prompt",
            "body": "# Content\nWith **markdown**",
            "tags": "lifecycle,test",
            "status": "draft",
        },
    )
    assert r.status_code == 200
    assert "Lifecycle Prompt" in r.text

    # Search
    r = await client.get("/prompts?q=Lifecycle")
    assert r.status_code == 200
    assert "Lifecycle Prompt" in r.text

    # Filter by status
    r = await client.get("/prompts?status=draft")
    assert r.status_code == 200
    assert "Lifecycle Prompt" in r.text

    r = await client.get("/prompts?status=published")
    assert r.status_code == 200
    assert "Lifecycle Prompt" not in r.text


@pytest.mark.asyncio
async def test_prompt_search_no_results(client):
    r = await client.get("/prompts?q=nonexistent_xyz_12345")
    assert r.status_code == 200
    assert "No prompts found" in r.text


@pytest.mark.asyncio
async def test_export_import_roundtrip(client):
    # Create data
    await client.post("/prompts", data={"title": "Export Me", "body": "content", "tags": "export"})

    # Export
    r = await client.get("/export/json")
    assert r.status_code == 200
    import json

    data = json.loads(r.text)
    assert len(data["prompts"]) >= 1
    assert data["version"] == "2.0"

    # XML export
    r = await client.get("/export/xml")
    assert r.status_code == 200
    assert "<?xml" in r.text


@pytest.mark.asyncio
async def test_sync_page(client):
    r = await client.get("/sync")
    assert r.status_code == 200
    assert "Push to Remote" in r.text
    assert "Pull from Remote" in r.text


@pytest.mark.asyncio
async def test_sync_push_no_provider(client):
    r = await client.post("/sync/push")
    assert r.status_code == 400
    assert "No remote configured" in r.text


@pytest.mark.asyncio
async def test_debug_headers(client):
    r = await client.get("/health")
    assert "x-request-id" in r.headers
    assert "x-response-time" in r.headers


@pytest.mark.asyncio
async def test_inline_category_creation_api(client):
    response = await client.post("/api/categories", json={"name": "Inline category"})
    assert response.status_code == 200
    assert response.json()["name"] == "Inline category"
    assert response.json()["id"]


@pytest.mark.asyncio
async def test_quick_prompts_has_active_navigation(client):
    response = await client.get("/widget")
    assert response.status_code == 200
    assert "Quick Prompts" in response.text
    assert 'aria-label="Quick Prompts"' in response.text
    assert 'class="active"' in response.text


@pytest.mark.asyncio
async def test_empty_about_help_and_mcp_presentational_contracts(client):
    empty = await client.get("/")
    assert "One home for your prompts. Endless ways to put them to work." in empty.text
    assert "Take the tour" not in empty.text
    assert 'class="empty-detail interactive-empty"' in empty.text
    assert 'class="empty-brand brand-image"' in empty.text

    about = await client.get("/about")
    assert about.status_code == 200
    assert "A focused workspace for turning scattered ideas into reusable prompts" in about.text
    assert about.text.count("<details open>") >= 3
    assert "PromptLibrary" in about.text

    help_page = await client.get("/help")
    assert help_page.status_code == 200
    assert "data-help-nav" in help_page.text
    assert "data-help-content" in help_page.text
    assert "help-layout" in help_page.text

    settings = await client.get("/settings")
    assert settings.status_code == 200
    assert 'role="tablist"' in settings.text
    assert 'role="tab"' in settings.text
    assert 'role="tabpanel"' in settings.text
    assert 'id="panel-storage"' in settings.text
    assert 'class="is-active"' in settings.text
    sync = await client.get("/sync")
    assert sync.status_code == 200
    assert 'aria-label="Backup sections"' in sync.text
    assert 'id="panel-export"' in sync.text
    assert 'id="panel-remote"' in sync.text
    assert 'id="panel-transfer"' in sync.text
    assert 'class="is-active"' in sync.text
    import json
    import re

    match = re.search(r'<pre id="mcp-config-generic">(.*?)</pre>', settings.text, re.S)
    assert match
    configuration = json.loads(match.group(1).strip())
    assert configuration["command"] == "promptlibrary-mcp"
    assert configuration["args"] == []
    assert configuration["env"]["PROMPTLIB_DATA_DIR"]
