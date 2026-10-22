"""Tests for export/import service."""

import json

import pytest

from promptlibrary.database import get_db, init_db
from promptlibrary.models import PromptStatus
from promptlibrary.services.export_service import ExportService
from promptlibrary.services.prompt_service import PromptService


@pytest.fixture
async def db(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTLIB_DATA_DIR", str(tmp_path))
    from promptlibrary.config import Settings

    monkeypatch.setattr("promptlibrary.database.settings", Settings())
    await init_db()
    async with get_db() as conn:
        yield conn


@pytest.mark.asyncio
async def test_export_json_roundtrip(db):
    svc = PromptService(db)
    export_svc = ExportService(db)

    # Create test data
    await svc.create_prompt(
        prompt_id="00000000-0000-0000-0000-000000000001",
        title="Export Test",
        body="# Hello\nWorld",
        status=PromptStatus.PUBLISHED,
        tags=["test", "export"],
    )
    await db.commit()

    # Export
    data = await export_svc.export_all()
    json_str = data.model_dump_json()

    # Verify structure
    parsed = json.loads(json_str)
    assert parsed["version"] == "2.0"
    assert len(parsed["prompts"]) == 1
    assert parsed["prompts"][0]["title"] == "Export Test"
    assert len(parsed["tags"]) == 2
