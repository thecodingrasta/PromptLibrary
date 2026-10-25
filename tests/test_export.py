"""Tests for export/import service."""

import json

import pytest

from promptlibrary.database import get_db, init_db
from promptlibrary.models import PromptStatus
from promptlibrary.services.export_service import ExportService
from promptlibrary.services.prompt_service import PromptService
from promptlibrary.services.validation import ConflictError


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


@pytest.mark.asyncio
async def test_json_and_xml_round_trip_preserve_content(db):
    service = PromptService(db)
    await service.create_prompt(
        "00000000-0000-0000-0000-000000000010", "Round trip", "Body", tags=["portable"]
    )
    await db.commit()
    export_service = ExportService(db)
    json_content = (await export_service.export_all()).model_dump_json()
    xml_content = await export_service.export_xml()

    await export_service.import_json(json_content, mode="merge")
    xml_result = await export_service.import_xml(xml_content, mode="merge")
    assert xml_result.imported_count == 0
    assert xml_result.skipped_count > 0


@pytest.mark.asyncio
async def test_merge_conflict_rolls_back_without_partial_import(db):
    service = PromptService(db)
    await service.create_prompt("00000000-0000-0000-0000-000000000011", "Original", "Body")
    await db.commit()
    content = (await ExportService(db).export_all()).model_dump(mode="json")
    content["prompts"][0]["title"] = "Conflicting edit"
    with pytest.raises(ConflictError, match="Conflicting prompts"):
        await ExportService(db).import_json(json.dumps(content), mode="merge")
    cursor = await db.execute(
        "SELECT title FROM prompts WHERE id=?", ("00000000-0000-0000-0000-000000000011",)
    )
    assert (await cursor.fetchone())[0] == "Original"


@pytest.mark.asyncio
async def test_replace_creates_file_backed_safety_snapshot(db, tmp_path):
    service = PromptService(db)
    await service.create_prompt("00000000-0000-0000-0000-000000000012", "Replace me", "Body")
    await db.commit()
    content = (await ExportService(db).export_all()).model_dump_json()
    result = await ExportService(db).import_json(content, mode="replace")
    assert result.replaced is True
    assert result.safety_backup is not None
    assert (tmp_path / "backups" / result.safety_backup).exists()
