"""HTTP regressions for prompt, workflow, version and import routes."""

import json
import os
import re

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


def _extract_id(html: str, pattern: str = r"/prompts/([a-f0-9-]+)") -> str | None:
    match = re.search(pattern, html)
    return match.group(1) if match else None


# === Prompts Router: route regressions ===


@pytest.mark.asyncio
async def test_prompt_create_and_detail(client):
    """Create → appears in list → detail page works."""
    # First: the "New" button must load the creation form (this was broken - 422)
    r = await client.get("/prompts/new")
    assert r.status_code == 200, (
        f"GET /prompts/new returned {r.status_code}: the new prompt form must load"
    )
    assert 'name="title"' in r.text, "Form must have a title field"
    assert "New prompt" in r.text, "Form must show 'New Prompt' heading"

    # Submit the form
    r = await client.post(
        "/prompts", data={"title": "Detail Test", "body": "# Content\n**bold**", "tags": "a,b"}
    )
    assert r.status_code == 200

    # Get ID from list
    r = await client.get("/prompts")
    prompt_id = _extract_id(r.text)
    assert prompt_id is not None

    # Detail via fragment
    r = await client.get(f"/prompts/{prompt_id}", headers={"X-Fragment": "1"})
    assert r.status_code == 200
    assert "Detail Test" in r.text
    assert "Content" in r.text  # Rendered markdown

    # Direct links must include the document, not just a fragment.
    r = await client.get(f"/prompts/{prompt_id}", headers={"X-Fragment": "0"})
    assert "<!doctype html>" in r.text
    assert r.status_code == 200
    assert "Detail Test" in r.text


@pytest.mark.asyncio
async def test_prompt_edit_form(client):
    """Edit form loads correctly."""
    await client.post("/prompts", data={"title": "Edit Me", "body": "original"})
    r = await client.get("/prompts")
    prompt_id = _extract_id(r.text)

    r = await client.get(f"/prompts/{prompt_id}/edit")
    assert r.status_code == 200
    assert "Edit Me" in r.text
    assert 'name="title"' in r.text
    assert 'name="body"' in r.text


@pytest.mark.asyncio
async def test_prompt_update(client):
    """Update a prompt via PUT."""
    await client.post("/prompts", data={"title": "Update Me", "body": "v1"})
    r = await client.get("/prompts")
    prompt_id = _extract_id(r.text)

    r = await client.put(
        f"/prompts/{prompt_id}",
        data={
            "title": "Updated Title",
            "body": "v2 content",
            "notes": "Changed in test",
            "status": "staged",
            "tags": "updated",
            "version_message": "Test update",
        },
    )
    assert r.status_code == 200
    assert "Updated Title" in r.text or "v2 content" in r.text


@pytest.mark.asyncio
async def test_prompt_delete(client):
    """Delete a prompt."""
    await client.post("/prompts", data={"title": "Delete Me", "body": "temp"})
    r = await client.get("/prompts")
    prompt_id = _extract_id(r.text)

    r = await client.delete(f"/prompts/{prompt_id}")
    assert r.status_code == 200
    assert r.headers["X-Message"] == "Prompt deleted."
    assert "Delete Me" not in r.text


@pytest.mark.asyncio
async def test_prompt_favourite(client):
    """Toggle favourite."""
    await client.post("/prompts", data={"title": "Fav Me", "body": "x"})
    r = await client.get("/prompts")
    prompt_id = _extract_id(r.text)

    r = await client.post(f"/prompts/{prompt_id}/favourite")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_prompt_not_found(client):
    """404 for non-existent prompt."""
    r = await client.get("/prompts/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_prompt_search_endpoint(client):
    """The search via query param works."""
    await client.post("/prompts", data={"title": "Searchable XYZ", "body": "content"})
    r = await client.get("/prompts?q=Searchable")
    assert r.status_code == 200
    assert "Searchable XYZ" in r.text


@pytest.mark.asyncio
async def test_prompt_filter_favourites(client):
    """Filter by favourites_only."""
    r = await client.get("/prompts?favourites_only=true")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_prompt_filter_by_tag(client):
    """Filter by tag."""
    await client.post("/prompts", data={"title": "Tagged", "body": "x", "tags": "specific_tag"})
    r = await client.get("/prompts?tag=specific_tag")
    assert r.status_code == 200
    assert "Tagged" in r.text


# === Versions Router: route regressions ===


@pytest.mark.asyncio
async def test_version_history_endpoint(client):
    """Get version history for a prompt."""
    await client.post("/prompts", data={"title": "Versioned", "body": "v1"})
    r = await client.get("/prompts")
    prompt_id = _extract_id(r.text)

    # Update to create v2
    await client.put(
        f"/prompts/{prompt_id}",
        data={"title": "Versioned", "body": "v2", "version_message": "Second version"},
    )

    r = await client.get(f"/versions/prompts/{prompt_id}/versions")
    assert r.status_code == 200
    assert "v1" in r.text or "v2" in r.text


@pytest.mark.asyncio
async def test_version_diff_endpoint(client):
    """Get diff between versions."""
    await client.post("/prompts", data={"title": "Diff P", "body": "line1"})
    r = await client.get("/prompts")
    prompt_id = _extract_id(r.text)

    await client.put(f"/prompts/{prompt_id}", data={"title": "Diff P", "body": "line1\nline2"})

    r = await client.get(f"/versions/prompts/{prompt_id}/versions/2/diff")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_version_restore_endpoint(client):
    """Restore a version."""
    await client.post("/prompts", data={"title": "Restore P", "body": "original"})
    r = await client.get("/prompts")
    prompt_id = _extract_id(r.text)

    await client.put(f"/prompts/{prompt_id}", data={"title": "Restore P", "body": "changed"})
    r = await client.post(f"/versions/prompts/{prompt_id}/restore/1")
    assert r.status_code == 200


# === Categories Router: Update & Delete ===


@pytest.mark.asyncio
async def test_category_update(client):
    """Update a category."""
    r = await client.post("/categories", data={"name": "Original", "colour": "#000000"})
    assert r.status_code == 200

    # Get category ID from the sidebar link format: /?category=UUID
    r = await client.get("/categories")
    cat_id_match = re.search(r"/categories/([a-f0-9-]+)", r.text)
    assert cat_id_match, f"No category ID found in: {r.text[:200]}"
    cat_id = cat_id_match.group(1)

    r = await client.put(f"/categories/{cat_id}", data={"name": "Renamed", "colour": "#ffffff"})
    assert r.status_code == 200
    assert "Renamed" in r.text


@pytest.mark.asyncio
async def test_category_delete(client):
    """Delete a category."""
    await client.post("/categories", data={"name": "DeleteCat"})
    r = await client.get("/categories")
    cat_id_match = re.search(r"/categories/([a-f0-9-]+)", r.text)
    assert cat_id_match, f"No category ID found in: {r.text[:200]}"
    cat_id = cat_id_match.group(1)

    r = await client.delete(f"/categories/{cat_id}")
    assert r.status_code == 200


# === Export Router: Import ===


@pytest.mark.asyncio
async def test_import_json(client):
    """Import JSON file."""
    export_data = json.dumps(
        {
            "version": "1.0",
            "exported_at": "2026-01-01T00:00:00Z",
            "categories": [],
            "tags": [],
            "prompts": [
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "title": "Imported",
                    "body": "content",
                    "notes": "",
                    "status": "published",
                    "category_id": None,
                    "is_favourite": 0,
                    "tags": [],
                    "created_at": "2026-01-01T00:00:00",
                    "updated_at": "2026-01-01T00:00:00",
                }
            ],
            "versions": [],
        }
    )

    r = await client.post(
        "/export/import/json",
        files={"file": ("test.json", export_data.encode(), "application/json")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["imported"] >= 1


@pytest.mark.asyncio
async def test_import_xml(client):
    """Import XML file."""
    # Use JSON export format wrapped in XML (matching our export format)
    xml_content = """<?xml version="1.0" encoding="utf-8"?>
<promptlibrary>
    <version>1.0</version>
    <exported_at>2026-01-01T00:00:00Z</exported_at>
    <categories></categories>
    <tags></tags>
    <prompts>
        <item>
            <id>22222222-2222-2222-2222-222222222222</id>
            <title>XML Import</title>
            <body>xml content</body>
            <notes></notes>
            <status>draft</status>
            <is_favourite>0</is_favourite>
            <tags></tags>
            <created_at>2026-01-01T00:00:00</created_at>
            <updated_at>2026-01-01T00:00:00</updated_at>
        </item>
    </prompts>
    <versions></versions>
</promptlibrary>"""

    r = await client.post(
        "/export/import/xml", files={"file": ("test.xml", xml_content.encode(), "application/xml")}
    )
    assert r.status_code == 200
    assert r.json()["imported"] == 1
    stored = await client.get("/prompts/22222222-2222-2222-2222-222222222222")
    assert "XML Import" in stored.text
    assert "xml content" in stored.text


# === Workflow Router: Detail, Delete ===


@pytest.mark.asyncio
async def test_workflow_detail_page(client):
    """View workflow detail."""
    r = await client.post("/workflows", data={"name": "Detail WF"})
    r = await client.get("/workflows")
    wf_id = re.search(r"/workflows/([a-f0-9-]+)", r.text).group(1)

    # fragment request
    r = await client.get(f"/workflows/{wf_id}", headers={"X-Fragment": "1"})
    assert r.status_code == 200
    assert "Detail WF" in r.text

    # Direct links must include the document, not just a fragment.
    r = await client.get(f"/workflows/{wf_id}", headers={"X-Fragment": "0"})
    assert "<!doctype html>" in r.text
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_workflow_delete(client):
    """Delete a workflow."""
    await client.post("/workflows", data={"name": "Delete WF"})
    r = await client.get("/workflows")
    wf_id = re.search(r"/workflows/([a-f0-9-]+)", r.text).group(1)

    r = await client.delete(f"/workflows/{wf_id}")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_workflow_update_stage(client):
    """Update a stage in a workflow."""
    await client.post("/workflows", data={"name": "Stage Edit WF"})
    r = await client.get("/workflows")
    wf_id = re.search(r"/workflows/([a-f0-9-]+)", r.text).group(1)

    # Add stage
    r = await client.post(
        f"/workflows/{wf_id}/stages",
        data={"title": "Original", "body": "orig body", "mode": "standard"},
    )
    assert r.status_code == 200

    # Get stage ID
    stage_id = re.search(r"/stages/([a-f0-9-]+)", r.text)
    if stage_id:
        stage_id = stage_id.group(1)
        # Update stage
        r = await client.put(
            f"/workflows/{wf_id}/stages/{stage_id}",
            data={"title": "Updated Stage", "body": "new body", "mode": "high_reasoning"},
        )
        assert r.status_code == 200


@pytest.mark.asyncio
async def test_workflow_delete_stage(client):
    """Delete a stage."""
    await client.post("/workflows", data={"name": "Del Stage WF"})
    r = await client.get("/workflows")
    wf_id = re.search(r"/workflows/([a-f0-9-]+)", r.text).group(1)

    await client.post(f"/workflows/{wf_id}/stages", data={"title": "S1", "body": "x"})
    r = await client.get(f"/workflows/{wf_id}")
    stage_id = re.search(r"/stages/([a-f0-9-]+)", r.text)
    if stage_id:
        r = await client.delete(f"/workflows/{wf_id}/stages/{stage_id.group(1)}")
        assert r.status_code == 200


@pytest.mark.asyncio
async def test_workflow_not_found(client):
    """404 for non-existent workflow."""
    r = await client.get("/workflows/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
