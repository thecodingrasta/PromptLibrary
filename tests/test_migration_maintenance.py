"""Upgrades and recovery preserve real database relationships and WAL content."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest

from promptlibrary.config import Settings
from promptlibrary.database import get_db, init_db
from promptlibrary.maintenance import backup_database, inspect_database, restore_database
from promptlibrary.services.export_service import ExportService
from promptlibrary.services.prompt_service import PromptService
from promptlibrary.services.validation import ConflictError, next_revision


async def test_schema_two_upgrade_preserves_relations_and_creates_backup(tmp_path: Path):
    settings = Settings(data_dir=tmp_path, _env_file=None)
    schema = (Path(__file__).parent / "fixtures/schema-v2.sql").read_text()
    with closing(sqlite3.connect(settings.db_path)) as db:
        db.executescript(schema)
        db.execute("INSERT INTO schema_version VALUES (2)")
        db.execute("INSERT INTO projects (id,name) VALUES ('project','Original')")
        db.execute("INSERT INTO categories (id,name) VALUES ('category','Original')")
        db.execute("INSERT INTO labels (id,name) VALUES ('label','Original')")
        db.execute("INSERT INTO tags (id,name) VALUES ('tag','Original')")
        db.execute(
            "INSERT INTO prompts (id,title,body,project_id,category_id) "
            "VALUES ('prompt','Original','Content','project','category')"
        )
        db.execute(
            "INSERT INTO prompt_versions (id,prompt_id,version_number,body,status) "
            "VALUES ('version','prompt',1,'Version content','draft')"
        )
        db.execute("INSERT INTO prompt_tags VALUES ('prompt','tag')")
        db.execute("INSERT INTO prompt_labels VALUES ('prompt','label')")
        db.execute(
            "INSERT INTO workflows (id,name,project_id) VALUES ('workflow','Flow','project')"
        )
        db.execute(
            "INSERT INTO workflow_stages (id,workflow_id,stage_number,title,body) "
            "VALUES ('stage','workflow',1,'First','Body')"
        )
        db.execute("INSERT INTO workflow_labels VALUES ('workflow','label')")
        db.execute("INSERT INTO workflow_tags VALUES ('workflow','tag')")
        db.commit()
    await init_db(settings)
    assert inspect_database(settings.db_path)["schema_version"] == 4
    backups = list((tmp_path / "backups").glob("*.db"))
    assert len(backups) == 1
    assert inspect_database(backups[0])["schema_version"] == 2
    async with get_db(settings) as db:
        snapshot = await ExportService(db).export_all()
        assert snapshot.prompts[0]["body"] == "Content"
        assert snapshot.prompts[0]["project_id"] == "project"
        assert snapshot.versions[0]["body"] == "Version content"
        assert snapshot.workflow_stages[0]["prompt_id"] is None
        assert snapshot.workflows[0]["status"] == "draft"
        assert len(snapshot.prompt_labels) == len(snapshot.workflow_labels) == 1
        assert len(snapshot.prompt_tags) == len(snapshot.workflow_tags) == 1
        await db.execute("UPDATE status_definitions SET name='Writing' WHERE key='draft'")
        await db.commit()
    await init_db(settings)
    async with get_db(settings) as db:
        row = await (
            await db.execute("SELECT name FROM status_definitions WHERE key='draft'")
        ).fetchone()
        assert row[0] == "Writing"
    assert len(list((tmp_path / "backups").glob("*.db"))) == 1


async def test_native_backup_reads_live_wal_and_restore_retains_safety_copy(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / "live", _env_file=None)
    await init_db(settings)
    async with get_db(settings) as db:
        prompt = str(uuid4())
        await PromptService(db).create_prompt(prompt, "Before")
        await db.commit()
        backup = backup_database(settings.db_path, tmp_path / "backups/library.db")
        with pytest.raises(FileExistsError):
            backup_database(settings.db_path, backup)
        await PromptService(db).update_prompt(prompt, "After")
        await db.commit()
    safety = restore_database(backup, settings.db_path)
    assert safety is not None
    assert safety.exists()
    for path, expected in [(settings.db_path, "Before"), (safety, "After")]:
        with closing(sqlite3.connect(path)) as db:
            assert db.execute("SELECT title FROM prompts").fetchone()[0] == expected
        assert inspect_database(path)["ok"]
    backup.unlink()
    assert not backup.exists()


async def test_native_restore_to_empty_directory_and_future_refusal(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / "source", _env_file=None)
    await init_db(settings)
    target = tmp_path / "new" / "library.db"
    assert restore_database(settings.db_path, target) is None
    assert inspect_database(target)["ok"]
    with closing(sqlite3.connect(settings.db_path)) as db:
        db.execute("UPDATE schema_version SET version=999")
        db.commit()
    with pytest.raises(ValueError, match="newer"):
        restore_database(settings.db_path, target)
    with pytest.raises(RuntimeError, match="newer"):
        await init_db(settings)
    assert inspect_database(target)["schema_version"] == 4


async def test_revision_tokens_change_on_every_edit(tmp_path: Path):
    settings = Settings(data_dir=tmp_path, _env_file=None)
    await init_db(settings)
    async with get_db(settings, write=True) as db:
        service = PromptService(db)
        identity = str(uuid4())
        await service.create_prompt(identity, "Original")
        previous = (await service.get_prompt(identity))["updated_at"]
        for index in range(10):
            await service.update_prompt(identity, f"Edit {index}", expected_updated_at=previous)
            current = (await service.get_prompt(identity))["updated_at"]
            assert current != previous
            with pytest.raises(ConflictError):
                await service.update_prompt(identity, "Stale", expected_updated_at=previous)
            previous = current
        await db.commit()
    assert next_revision("2099-01-01T00:00:00.000000Z") > "2099-01-01T00:00:00.000000Z"


async def test_duplicate_snapshot_fields_are_rejected(tmp_path: Path):
    settings = Settings(data_dir=tmp_path, _env_file=None)
    await init_db(settings)
    async with get_db(settings) as db:
        with pytest.raises(ValueError, match="JSON"):
            await ExportService(db).import_json('{"version":"2.0","version":"1.0"}')
        with pytest.raises(ValueError, match="XML"):
            await ExportService(db).import_xml(
                "<promptlibrary><prompts><item><id>a</id><id>b</id>"
                "<title>Bad</title></item></prompts></promptlibrary>"
            )
        snapshot = json.loads((await ExportService(db).export_all()).model_dump_json())
        assert snapshot["version"] == "2.0"
