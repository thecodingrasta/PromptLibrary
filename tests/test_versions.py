"""Tests for version control service."""

import pytest

from promptlibrary.database import get_db, init_db
from promptlibrary.models import PromptStatus
from promptlibrary.services.prompt_service import PromptService
from promptlibrary.services.version_service import VersionService


@pytest.fixture
async def db(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTLIB_DATA_DIR", str(tmp_path))
    from promptlibrary.config import Settings

    monkeypatch.setattr("promptlibrary.database.settings", Settings())
    await init_db()
    async with get_db() as conn:
        yield conn


@pytest.mark.asyncio
async def test_version_creation(db):
    svc = PromptService(db)
    vsvc = VersionService(db)

    await svc.create_prompt(
        prompt_id="test-1", title="Test", body="v1 content", status=PromptStatus.DRAFT
    )
    v1 = await vsvc.create_version(
        prompt_id="test-1", body="v1 content", notes="", status=PromptStatus.DRAFT
    )
    assert v1 == 1

    v2 = await vsvc.create_version(
        prompt_id="test-1", body="v2 content", notes="", status=PromptStatus.DRAFT
    )
    assert v2 == 2


@pytest.mark.asyncio
async def test_diff_generation(db):
    svc = PromptService(db)
    vsvc = VersionService(db)

    await svc.create_prompt(
        prompt_id="test-2", title="Diff Test", body="line 1", status=PromptStatus.DRAFT
    )
    await vsvc.create_version(
        prompt_id="test-2", body="line 1", notes="", status=PromptStatus.DRAFT
    )
    await vsvc.create_version(
        prompt_id="test-2", body="line 1\nline 2", notes="", status=PromptStatus.DRAFT
    )

    diff = await vsvc.get_diff("test-2", 2)
    assert any("+" in line and "line 2" in line for line in diff)
