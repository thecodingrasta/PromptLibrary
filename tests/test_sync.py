"""Tests for sync service."""

import pytest

from promptlibrary.database import get_db, init_db
from promptlibrary.services.sync_service import SyncService


@pytest.fixture
async def db(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTLIB_DATA_DIR", str(tmp_path))
    from promptlibrary.config import Settings

    monkeypatch.setattr("promptlibrary.database.settings", Settings())
    await init_db()
    async with get_db() as conn:
        yield conn


@pytest.mark.asyncio
async def test_push_without_provider(db):
    svc = SyncService(db)
    with pytest.raises(ValueError, match="No remote configured"):
        await svc.push()


@pytest.mark.asyncio
async def test_local_sync_roundtrip(db, tmp_path, monkeypatch):
    backup_dir = tmp_path / "backups"
    monkeypatch.setenv("PROMPTLIB_SYNC_PROVIDER", "local")
    monkeypatch.setenv("PROMPTLIB_LOCAL_BACKUP_PATH", str(backup_dir))

    from promptlibrary.config import Settings

    new_settings = Settings()
    monkeypatch.setattr("promptlibrary.config.settings", new_settings)
    monkeypatch.setattr("promptlibrary.services.sync_service.settings", new_settings)

    svc = SyncService(db)
    result = await svc.push()
    assert result.success

    # Verify file was created
    assert (backup_dir / "promptlibrary_backup.json").exists()


@pytest.mark.asyncio
async def test_local_sync_push_and_pull_round_trip(db, tmp_path, monkeypatch):
    backup_dir = tmp_path / "backups"
    monkeypatch.setenv("PROMPTLIB_SYNC_PROVIDER", "local")
    monkeypatch.setenv("PROMPTLIB_LOCAL_BACKUP_PATH", str(backup_dir))
    from promptlibrary.config import Settings
    from promptlibrary.services.prompt_service import PromptService

    configured = Settings()
    monkeypatch.setattr("promptlibrary.config.settings", configured)
    monkeypatch.setattr("promptlibrary.services.sync_service.settings", configured)
    await PromptService(db).create_prompt(
        "00000000-0000-0000-0000-000000000020", "Backup prompt", "Body"
    )
    await db.commit()
    service = SyncService(db)
    pushed = await service.push()
    assert pushed.success is True
    assert (backup_dir / "promptlibrary_backup.json").exists()
    pulled = await service.pull("merge")
    assert pulled.success is True
    assert pulled.skipped > 0
