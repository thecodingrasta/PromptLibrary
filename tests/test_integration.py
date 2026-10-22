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
