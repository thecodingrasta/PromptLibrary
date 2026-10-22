"""Tests for the MCP server: validates agentic capabilities."""

import json

import pytest

from promptlibrary.database import init_db
from promptlibrary.mcp.server import call_tool


@pytest.fixture(autouse=True)
async def setup_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTLIB_DATA_DIR", str(tmp_path))
    from promptlibrary.config import Settings

    new_settings = Settings()
    monkeypatch.setattr("promptlibrary.database.settings", new_settings)
    monkeypatch.setattr("promptlibrary.config.settings", new_settings)
    await init_db()


def _parse(result) -> dict | list:
    return json.loads(result[0].text)


@pytest.mark.asyncio
async def test_mcp_create_prompt():
    """Agent can create a prompt."""
    result = await call_tool(
        "create_prompt",
        {
            "title": "MCP Test Prompt",
            "body": "# Hello from MCP\n\nThis prompt was created by an agent.",
            "tags": ["mcp", "test"],
            "status": "draft",
        },
    )
    data = _parse(result)
    assert data["status"] == "created"
    assert "id" in data


@pytest.mark.asyncio
async def test_mcp_search_prompts():
    """Agent can search prompts."""
    # Create first
    await call_tool("create_prompt", {"title": "Searchable", "body": "Find me"})

    result = await call_tool("search_prompts", {"query": "Searchable"})
    data = _parse(result)
    assert len(data) >= 1
    assert data[0]["title"] == "Searchable"


@pytest.mark.asyncio
async def test_mcp_get_prompt():
    """Agent can retrieve a specific prompt."""
    create_result = await call_tool("create_prompt", {"title": "Get Me", "body": "Content"})
    prompt_id = _parse(create_result)["id"]

    result = await call_tool("get_prompt", {"id": prompt_id})
    data = _parse(result)
    assert data["title"] == "Get Me"
    assert data["body"] == "Content"


@pytest.mark.asyncio
async def test_mcp_get_prompt_by_title():
    """Agent can find a prompt by title."""
    await call_tool("create_prompt", {"title": "Unique Title XYZ", "body": "Body"})

    result = await call_tool("get_prompt_by_title", {"title": "Unique Title XYZ"})
    data = _parse(result)
    assert data["title"] == "Unique Title XYZ"


@pytest.mark.asyncio
async def test_mcp_update_prompt():
    """Agent can update a prompt (creates new version)."""
    create_result = await call_tool("create_prompt", {"title": "Update Me", "body": "v1"})
    prompt_id = _parse(create_result)["id"]

    result = await call_tool(
        "update_prompt",
        {
            "id": prompt_id,
            "body": "v2 - updated",
            "message": "Agent improved the prompt",
        },
    )
    data = _parse(result)
    assert data["status"] == "updated"

    # Verify content changed
    get_result = await call_tool("get_prompt", {"id": prompt_id})
    prompt = _parse(get_result)
    assert prompt["body"] == "v2 - updated"


@pytest.mark.asyncio
async def test_mcp_delete_prompt():
    """Agent can delete a prompt."""
    create_result = await call_tool("create_prompt", {"title": "Delete Me", "body": "Temp"})
    prompt_id = _parse(create_result)["id"]

    result = await call_tool("delete_prompt", {"id": prompt_id})
    data = _parse(result)
    assert data["status"] == "deleted"

    # Verify gone
    get_result = await call_tool("get_prompt", {"id": prompt_id})
    assert "error" in _parse(get_result)


@pytest.mark.asyncio
async def test_mcp_publish_prompt():
    """Agent can publish a draft prompt."""
    create_result = await call_tool("create_prompt", {"title": "Publish Me", "body": "Content"})
    prompt_id = _parse(create_result)["id"]

    result = await call_tool("publish_prompt", {"id": prompt_id})
    data = _parse(result)
    assert data["status"] == "published"


@pytest.mark.asyncio
async def test_mcp_toggle_favourite():
    """Agent can favourite/unfavourite a prompt."""
    create_result = await call_tool("create_prompt", {"title": "Fav Me", "body": "Content"})
    prompt_id = _parse(create_result)["id"]

    result = await call_tool("toggle_favourite", {"id": prompt_id})
    data = _parse(result)
    assert data["is_favourite"] is True

    result = await call_tool("toggle_favourite", {"id": prompt_id})
    data = _parse(result)
    assert data["is_favourite"] is False


@pytest.mark.asyncio
async def test_mcp_category_lifecycle():
    """Agent can create, list, and delete categories."""
    # Create
    result = await call_tool("create_category", {"name": "MCP Category", "colour": "#ff0000"})
    data = _parse(result)
    assert data["status"] == "created"
    cat_id = data["id"]

    # List
    result = await call_tool("list_categories", {})
    cats = _parse(result)
    assert any(c["name"] == "MCP Category" for c in cats)

    # Delete
    result = await call_tool("delete_category", {"id": cat_id})
    assert _parse(result)["status"] == "deleted"


@pytest.mark.asyncio
async def test_mcp_tag_lifecycle():
    """Agent can list, rename, and delete tags."""
    # Create a prompt with tags
    await call_tool("create_prompt", {"title": "Tagged", "body": "X", "tags": ["alpha", "beta"]})

    # List
    result = await call_tool("list_tags", {})
    tags = _parse(result)
    assert any(t["name"] == "alpha" for t in tags)

    # Rename
    result = await call_tool("rename_tag", {"old_name": "alpha", "new_name": "omega"})
    assert _parse(result)["status"] == "renamed"

    # Delete
    result = await call_tool("delete_tag", {"name": "omega"})
    assert _parse(result)["status"] == "deleted"


@pytest.mark.asyncio
async def test_mcp_version_history():
    """Agent can view version history."""
    create_result = await call_tool("create_prompt", {"title": "Versioned", "body": "v1"})
    prompt_id = _parse(create_result)["id"]

    # Make an edit
    await call_tool("update_prompt", {"id": prompt_id, "body": "v2", "message": "Edit 1"})

    result = await call_tool("get_version_history", {"id": prompt_id})
    versions = _parse(result)
    assert len(versions) >= 2


@pytest.mark.asyncio
async def test_mcp_version_diff():
    """Agent can view diffs between versions."""
    create_result = await call_tool("create_prompt", {"title": "Diff Test", "body": "line 1"})
    prompt_id = _parse(create_result)["id"]

    await call_tool("update_prompt", {"id": prompt_id, "body": "line 1\nline 2"})

    result = await call_tool("get_version_diff", {"id": prompt_id, "version": 2})
    data = _parse(result)
    assert any("line 2" in line for line in data.get("diff", []))


@pytest.mark.asyncio
async def test_mcp_restore_version():
    """Agent can restore a previous version."""
    create_result = await call_tool("create_prompt", {"title": "Restore Test", "body": "original"})
    prompt_id = _parse(create_result)["id"]

    await call_tool("update_prompt", {"id": prompt_id, "body": "changed"})
    await call_tool("restore_version", {"id": prompt_id, "version": 1})

    get_result = await call_tool("get_prompt", {"id": prompt_id})
    assert _parse(get_result)["body"] == "original"


@pytest.mark.asyncio
async def test_mcp_bulk_update_status():
    """Agent can bulk-update status of multiple prompts."""
    ids = []
    for i in range(3):
        r = await call_tool("create_prompt", {"title": f"Bulk {i}", "body": "X"})
        ids.append(_parse(r)["id"])

    result = await call_tool("bulk_update_status", {"ids": ids, "status": "published"})
    data = _parse(result)
    assert data["updated"] == 3
    assert data["status"] == "published"


@pytest.mark.asyncio
async def test_mcp_create_with_category():
    """Agent can create a prompt with a new category in one call."""
    result = await call_tool(
        "create_prompt",
        {
            "title": "Categorised",
            "body": "Content",
            "category": "New Auto Category",
        },
    )
    data = _parse(result)
    assert data["status"] == "created"

    # Verify category was created
    cats = _parse(await call_tool("list_categories", {}))
    assert any(c["name"] == "New Auto Category" for c in cats)


@pytest.mark.asyncio
async def test_mcp_error_handling():
    """Agent gets clear errors for invalid operations."""
    # Non-existent prompt
    result = await call_tool("get_prompt", {"id": "00000000-0000-0000-0000-000000000000"})
    data = _parse(result)
    assert "error" in data

    # Non-existent tag
    result = await call_tool("delete_tag", {"name": "nonexistent_xyz"})
    data = _parse(result)
    assert "error" in data
