"""Tests for prompt CRUD operations."""

import os

import pytest
from httpx import ASGITransport, AsyncClient

# Set test env before importing app
os.environ.setdefault("PROMPTLIB_DEBUG", "true")


@pytest.fixture
async def client(tmp_path, monkeypatch):
    """Create a test client with a temporary database."""
    monkeypatch.setenv("PROMPTLIB_DATA_DIR", str(tmp_path))

    # Force reimport of settings with new env
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


@pytest.mark.asyncio
async def test_index_returns_html(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "PromptLibrary" in response.text


@pytest.mark.asyncio
async def test_create_prompt(client):
    response = await client.post(
        "/prompts",
        data={"title": "Test Prompt", "body": "Hello world", "status": "draft"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_export_json_empty(client):
    response = await client.get("/export/json")
    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_unimplemented_pwa_is_not_advertised(client):
    response = await client.get("/manifest.json")
    assert response.status_code == 404
    response = await client.get("/")
    assert 'rel="manifest"' not in response.text
