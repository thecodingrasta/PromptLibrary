"""Release regressions for data integrity, human/agent parity and security boundaries."""

import asyncio
import json
import sqlite3
import threading
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from promptlibrary.app import create_app
from promptlibrary.config import Settings
from promptlibrary.database import get_db, init_db
from promptlibrary.mcp.registry import TOOLS, execute_tool
from promptlibrary.services.category_service import CategoryService
from promptlibrary.services.export_service import TABLES, ExportService
from promptlibrary.services.library_service import LibraryFilter, LibraryService
from promptlibrary.services.markdown_service import render_markdown
from promptlibrary.services.project_service import LabelService, ProjectService
from promptlibrary.services.prompt_service import PromptService
from promptlibrary.services.run_service import RunService
from promptlibrary.services.status_service import StatusService
from promptlibrary.services.sync_config_service import RemoteConfig, SyncConfigService
from promptlibrary.services.validation import ConflictError
from promptlibrary.services.version_service import VersionService
from promptlibrary.services.workflow_service import WorkflowService
from promptlibrary.sync_providers.base import blocking_operation


@pytest.fixture
async def configuration(tmp_path: Path) -> Settings:
    settings = Settings(data_dir=tmp_path / "library", _env_file=None)
    await init_db(settings)
    return settings


@pytest.fixture
async def client(configuration: Settings):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(configuration)),
        base_url="http://localhost",
        headers={"X-Fragment": "1"},
    ) as session:
        yield session


async def seed(db) -> dict[str, str]:
    project = await ProjectService(db).create_project("Real project", "Description", "#112233")
    category = await CategoryService(db).create("Development", colour="#223344")
    await CategoryService(db).create("Child", parent_id=category)
    status = await StatusService(db).save_status("Ready to review", "#334455", 3)
    label = await LabelService(db).create_label("Release label")
    prompt = str(uuid4())
    await PromptService(db).create_prompt(
        prompt,
        "Research",
        "Research {{TOPIC}}",
        "Operator notes",
        status,
        category,
        project,
        ["research", "release"],
    )
    await PromptService(db).toggle_favourite(prompt)
    await LabelService(db).set_labels("prompt", prompt, [label])
    await VersionService(db).create_version(
        prompt, "Research {{TOPIC}}", "Operator notes", status, "First"
    )
    workflow = await WorkflowService(db).create_workflow(
        "Research workflow", "Two stages", project, category, status, ["release"]
    )
    await WorkflowService(db).toggle_favourite(workflow)
    await LabelService(db).set_labels("workflow", workflow, [label])
    stage = await WorkflowService(db).add_stage(
        workflow, "Research", prompt_id=prompt, link_prompt=True
    )
    await WorkflowService(db).add_stage(
        workflow, "Summarise", "Summarise {{stage_1_output}}", "Be concise."
    )
    run = await RunService(db).start(workflow, {"TOPIC": "SQLite"})
    await RunService(db).complete_step(run, 1, "First stage output")
    await db.execute("INSERT INTO preferences VALUES ('theme','dark')")
    await db.commit()
    return {
        "project": project,
        "category": category,
        "status": status,
        "label": label,
        "prompt": prompt,
        "workflow": workflow,
        "stage": stage,
        "run": run,
    }


@pytest.mark.parametrize("file_format", ["json", "xml"])
async def test_complete_snapshot_roundtrip(configuration, tmp_path, file_format):
    async with get_db(configuration) as db:
        await seed(db)
        baseline = (await ExportService(db).export_all()).model_dump(mode="json")
        content = (
            await ExportService(db).export_xml() if file_format == "xml" else json.dumps(baseline)
        )
    target = Settings(data_dir=tmp_path / "target", _env_file=None)
    await init_db(target)
    async with get_db(target) as db:
        service = ExportService(db)
        result = (
            await service.import_xml(content, "replace")
            if file_format == "xml"
            else await service.import_json(content, "replace")
        )
        await db.commit()
        restored = (await service.export_all()).model_dump(mode="json")
        for section in TABLES:
            assert restored[section] == baseline[section], section
        assert result.safety_backup
        assert (target.data_dir / "backups" / result.safety_backup).is_file()
        assert await (await db.execute("PRAGMA foreign_key_check")).fetchone() is None


async def test_merge_is_idempotent_and_conflict_rolls_back(configuration):
    async with get_db(configuration) as db:
        ids = await seed(db)
        service = ExportService(db)
        baseline = (await service.export_all()).model_dump(mode="json")
        result = await service.import_json(json.dumps(baseline))
        assert result.imported_count == 0
        assert result.skipped_count == sum(len(baseline[name]) for name in TABLES)
        await db.commit()
        edited = json.loads(json.dumps(baseline))
        edited["projects"].append({"id": str(uuid4()), "name": "Must roll back"})
        edited["prompts"][0]["body"] = "Conflicting change"
        with pytest.raises(ConflictError):
            await service.import_json(json.dumps(edited))
        await db.commit()
        current = (await service.export_all()).model_dump(mode="json")
        for section in TABLES:
            assert current[section] == baseline[section]
        assert (await PromptService(db).get_prompt(ids["prompt"]))["body"] == "Research {{TOPIC}}"


async def test_failed_replacement_leaves_content_unchanged(configuration):
    async with get_db(configuration) as db:
        await seed(db)
        service = ExportService(db)
        baseline = (await service.export_all()).model_dump(mode="json")
        malformed = json.loads(json.dumps(baseline))
        malformed["workflow_stages"][0]["workflow_id"] = str(uuid4())
        with pytest.raises((ValueError, sqlite3.IntegrityError)):
            await service.import_json(json.dumps(malformed), "replace")
        await db.commit()
        current = (await service.export_all()).model_dump(mode="json")
        assert {key: current[key] for key in TABLES} == {key: baseline[key] for key in TABLES}


@pytest.mark.parametrize(
    "payload",
    [
        "[]",
        '{"version":"99"}',
        '{"version":"2.0","unknown":[]}',
        '{"prompts":[{"id":"x","title":"Bad","status":"missing"}]}',
    ],
)
async def test_invalid_import_is_rejected(configuration, payload):
    async with get_db(configuration) as db:
        with pytest.raises((ValueError, sqlite3.IntegrityError)):
            await ExportService(db).import_json(payload)


async def test_xml_entities_are_rejected(configuration):
    content = '<!DOCTYPE promptlibrary [<!ENTITY secret SYSTEM "file:///etc/passwd">]><promptlibrary><version>&secret;</version></promptlibrary>'
    async with get_db(configuration) as db:
        with pytest.raises(ValueError, match="XML"):
            await ExportService(db).import_xml(content)


async def test_library_filters_projects_statuses_tags_and_types(configuration):
    async with get_db(configuration) as db:
        ids = await seed(db)
        service = LibraryService(db)
        items, count = await service.list_items(
            LibraryFilter(
                project_id=ids["project"], status=ids["status"], tag="release", favourites_only=True
            )
        )
        assert count == 2
        assert {item["item_type"] for item in items} == {"prompt", "workflow"}
        _, count = await service.list_items(LibraryFilter(q="does not exist"))
        assert count == 0
        _, count = await service.list_items(LibraryFilter(q="%"))
        assert count == 0
        items, count = await service.list_items(LibraryFilter(item_type="workflow", q="TOPIC"))
        assert count == 1
        assert items[0]["id"] == ids["workflow"]


async def test_prompt_history_clear_and_stale_edit(configuration):
    async with get_db(configuration, write=True) as db:
        ids = await seed(db)
        prompt = await PromptService(db).get_prompt(ids["prompt"])
        assert await VersionService(db).clear_history(ids["prompt"]) == 1
        assert await VersionService(db).list_versions(ids["prompt"]) == []
        assert (await PromptService(db).get_prompt(ids["prompt"]))["body"] == prompt["body"]
        await VersionService(db).create_version(ids["prompt"], "new", "", "draft", "After clear")
        assert (await VersionService(db).list_versions(ids["prompt"]))[0]["version_number"] == 1
        with pytest.raises(ConflictError):
            await PromptService(db).update_prompt(ids["prompt"], "Bad", expected_updated_at="stale")


async def test_linked_prompt_copy_and_immutable_runs(configuration):
    async with get_db(configuration, write=True) as db:
        ids = await seed(db)
        workflow = WorkflowService(db)
        copied = await workflow.add_stage(ids["workflow"], "Copy", prompt_id=ids["prompt"])
        await PromptService(db).update_prompt(ids["prompt"], "Changed source", "Changed body")
        stages = (await workflow.require_workflow(ids["workflow"]))["stages"]
        assert stages[0]["body"] == "Changed body"
        assert stages[-1]["id"] == copied
        assert stages[-1]["body"] == "Research {{TOPIC}}"
        run = await RunService(db).get_run(ids["run"])
        assert run["snapshot"]["stages"][0]["body"] == "Research {{TOPIC}}"
        with pytest.raises(ConflictError):
            await PromptService(db).delete_prompt(ids["prompt"])
        await workflow.update_stage(ids["stage"], detach=True)
        await PromptService(db).delete_prompt(ids["prompt"])
        assert (await workflow.require_workflow(ids["workflow"]))["stages"][0][
            "body"
        ] == "Changed body"


async def test_reorder_and_deletion_preserve_dependency_identity(configuration):
    async with get_db(configuration, write=True) as db:
        service = WorkflowService(db)
        workflow = await service.create_workflow("Order")
        first = await service.add_stage(workflow, "A", "Independent")
        second = await service.add_stage(workflow, "B", "Independent")
        third = await service.add_stage(workflow, "C", "Use {{stage_1_output}}")
        await service.reorder_stage(second, 1)
        stages = (await service.require_workflow(workflow))["stages"]
        assert [stage["id"] for stage in stages] == [second, first, third]
        assert stages[2]["body"] == "Use {{stage_2_output}}"
        await db.commit()
        with pytest.raises(ConflictError):
            await service.reorder_stage(first, 3)
        await db.commit()
        assert [stage["id"] for stage in (await service.require_workflow(workflow))["stages"]] == [
            second,
            first,
            third,
        ]
        with pytest.raises(ConflictError):
            await service.delete_stage(first)
        await db.commit()
        assert len((await service.require_workflow(workflow))["stages"]) == 3


async def test_runs_validate_inputs_and_reject_duplicate_outputs(configuration):
    async with get_db(configuration, write=True) as db:
        ids = await seed(db)
        service = RunService(db)
        with pytest.raises(ValueError, match="Missing inputs"):
            await service.start(ids["workflow"], {})
        current = await service.get_run(ids["run"])
        assert current["rendered_input"] == "Be concise.\n\nSummarise First stage output"
        result = await service.complete_step(ids["run"], 2, "Final result")
        assert result["status"] == "completed"
        assert len(result["steps"]) == 2
        with pytest.raises(ConflictError):
            await service.complete_step(ids["run"], 2, "Duplicate")
        assert len((await service.get_run(ids["run"]))["steps"]) == 2


async def test_concurrent_run_completion_advances_once(configuration):
    async with get_db(configuration) as db:
        ids = await seed(db)

    async def complete():
        async with get_db(configuration, write=True) as db:
            result = await RunService(db).complete_step(ids["run"], 2, "Output")
            await db.commit()
            return result["status"]

    results = await asyncio.gather(complete(), complete(), return_exceptions=True)
    assert results.count("completed") == 1
    assert sum(isinstance(result, ConflictError) for result in results) == 1


@pytest.mark.parametrize(
    "content",
    [
        "<script>alert(1)</script>",
        "<img src=x onerror=alert(1)>",
        "[x](javascript:alert%281%29)",
        "[x](data:text/html,test)",
        "[x](http://[invalid)",
        "![tracker](https://attacker.invalid/track)",
    ],
)
def test_markdown_is_not_executable(content):
    rendered = render_markdown(content)
    assert "<script" not in rendered
    assert "<img" not in rendered
    assert 'href="javascript:' not in rendered
    assert 'href="data:' not in rendered


async def test_http_refresh_contract_and_history_controls(client):
    response = await client.post(
        "/prompts", data={"title": "Newly created", "body": "Hello {{TOPIC}}"}
    )
    path = response.headers["X-Page-URL"]
    assert path.startswith("/prompts/")
    assert 'id="prompt-list"' in response.text
    assert 'id="version-history"' in response.text
    assert "data-confirm=" in response.text
    favourite = await client.post(path + "/favourite")
    assert 'aria-pressed="true"' in favourite.text
    saved = await client.post(path + "/save", data={"title": "Renamed now", "body": "Second body"})
    assert "Renamed now" in saved.text
    assert "Newly created" not in saved.text
    cleared = await client.post(path + "/versions/clear")
    assert "Version history (0)" in cleared.text
    assert "Second body" in cleared.text
    deleted = await client.post(path + "/delete")
    assert "Renamed now" not in deleted.text
    assert (await client.get(path)).status_code == 404


async def test_full_page_keeps_list_and_guide_literals(client):
    created = await client.post("/prompts", data={"title": "Deep linked", "body": "Content"})
    client.headers.pop("X-Fragment")
    response = await client.get(created.headers["X-Page-URL"])
    assert "<!doctype html>" in response.text.lower()
    assert 'id="prompt-list"' in response.text
    response = await client.get("/help")
    assert "{{TOPIC}}" in response.text
    assert "{{stage_1_output}}" in response.text
    assert "cdn.tailwindcss.com" not in response.text


async def test_non_javascript_post_redirects_to_detail(client):
    client.headers.pop("X-Fragment")
    response = await client.post(
        "/prompts", data={"title": "No JavaScript"}, headers={"Origin": "http://localhost"}
    )
    assert response.status_code == 303
    assert response.headers["Location"].startswith("/prompts/")


async def test_host_origin_and_response_security(client):
    assert (await client.get("/", headers={"Host": "attacker.invalid"})).status_code == 400
    assert (await client.get("/", headers={"Host": "[::1]"})).status_code == 200
    assert (
        await client.post(
            "/prompts", data={"title": "Blocked"}, headers={"Origin": "https://attacker.invalid"}
        )
    ).status_code == 403
    assert (
        await client.post(
            "/prompts", data={"title": "Blocked"}, headers={"Sec-Fetch-Site": "cross-site"}
        )
    ).status_code == 403
    response = await client.get("/")
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "script-src 'self';" in response.headers["Content-Security-Policy"]


async def test_basic_auth_and_request_limit(configuration):
    secured = configuration.model_copy(
        update={
            "auth_password": Settings(auth_password="a-very-long-test-password").auth_password,
            "max_request_bytes": 1024,
        }
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(secured)), base_url="http://localhost"
    ) as client:
        assert (await client.get("/")).status_code == 401
        assert (await client.get("/health")).status_code == 200
        client.auth = httpx.BasicAuth("promptlibrary", "a-very-long-test-password")
        assert (await client.get("/")).status_code == 200
        response = await client.post(
            "/api/preview", headers={"X-PromptLibrary-Client": "1"}, json={"text": "x" * 2000}
        )
        assert response.status_code == 413


async def test_config_encryption_masking_preservation_and_scope(configuration):
    async with get_db(configuration) as db:
        service = SyncConfigService(db, configuration)
        await service.save(
            {
                "provider": "s3",
                "s3_bucket": "test-bucket",
                "s3_access_key": "access-secret",
                "s3_secret_key": "private-secret",
            }
        )
        row = await (
            await db.execute("SELECT config_json FROM sync_configs WHERE id='active'")
        ).fetchone()
        assert "private-secret" not in row[0]
        public = (await service.load()).public_values()
        assert public["s3_secret_key"] == ""
        assert public["s3_secret_key_stored"]
        await service.save(
            {
                "provider": "s3",
                "s3_bucket": "test-bucket",
                "s3_access_key": "changed-access",
                "s3_secret_key": "",
            }
        )
        assert (await service.load()).s3_secret_key == "private-secret"
        await service.save({"provider": "s3", "s3_bucket": "other-bucket"})
        assert (await service.load()).s3_secret_key == ""
        snapshot = (await ExportService(db).export_all()).model_dump_json()
        assert "sync_configs" not in snapshot
        assert "private-secret" not in snapshot


@pytest.mark.parametrize(
    "remote",
    [
        {"provider": "webdav", "webdav_url": "http://example.invalid"},
        {"provider": "webdav", "webdav_url": "https://user:secret@example.invalid"},
        {"provider": "webdav", "webdav_url": "https://example.invalid/path?query=1"},
        {
            "provider": "sftp",
            "sftp_host": "host",
            "sftp_username": "user",
            "sftp_remote_path": "relative",
        },
        {"provider": "local", "local_backup_path": "relative"},
    ],
)
def test_unsafe_remote_config_is_rejected(remote):
    with pytest.raises(ValueError, match="validation error"):
        RemoteConfig.model_validate(remote)


async def test_mcp_custom_status_workflow_run_and_errors(configuration):
    async def call(name, arguments):
        result, failed = await execute_tool(name, arguments, configuration)
        assert not failed, result
        return result

    status = await call("save_status", {"name": "Reviewed"})
    prompt = await call(
        "create_prompt", {"title": "Agent prompt", "body": "For {{TOPIC}}", "status": status["key"]}
    )
    workflow = await call("create_workflow", {"name": "Agent workflow", "status": status["key"]})
    await call(
        "add_workflow_stage",
        {
            "workflow_id": workflow["id"],
            "title": "Use prompt",
            "prompt_id": prompt["id"],
            "link_prompt": True,
        },
    )
    run = await call(
        "start_workflow_run", {"workflow_id": workflow["id"], "variables": {"TOPIC": "Testing"}}
    )
    assert run["rendered_input"] == "For Testing"
    completed = await call(
        "complete_workflow_step", {"run_id": run["id"], "expected_stage": 1, "output": "Verified"}
    )
    assert completed["status"] == "completed"
    result, failed = await execute_tool(
        "create_prompt", {"title": "Missing body", "password": "must-not-echo"}, configuration
    )
    assert failed
    assert "must-not-echo" not in json.dumps(result)
    assert "password" in result["error"]
    assert all(
        definition.definition.inputSchema.get("additionalProperties") is False
        for definition in TOOLS.values()
    )


async def test_mcp_label_update_preserves_omitted_metadata(configuration):
    created, failed = await execute_tool(
        "create_label", {"name": "Before", "colour": "#123456", "icon": "code"}, configuration
    )
    assert not failed, created
    updated, failed = await execute_tool(
        "update_label",
        {"id": created["id"], "name": "After", "label_type": "language", "icon": "python"},
        configuration,
    )
    assert not failed, updated
    async with get_db(configuration) as db:
        label = await LabelService(db).find_label_by_name("After")
        assert label is not None
        assert label["colour"] == "#123456"
        assert label["icon"] == "python"
        assert label["label_type"] == "language"
        await LabelService(db).update_label(label["id"], "Renamed", "custom", "#654321")
        renamed = await LabelService(db).find_label_by_name("Renamed")
        assert renamed["icon"] == "python"
        assert renamed["colour"] == "#654321"


async def test_blocking_transfer_retains_lock_during_repeated_cancellation(configuration):
    started = threading.Event()
    release = threading.Event()
    service = None

    def upload():
        started.set()
        if not release.wait(5):
            raise RuntimeError("Test worker timed out.")
        return "saved"

    async with get_db(configuration) as db:
        service = SyncConfigService(db, configuration)

        async def transfer():
            with service.operation_lock():
                return await blocking_operation(upload)

        task = asyncio.create_task(transfer())
        try:
            for _ in range(100):
                if started.is_set():
                    break
                await asyncio.sleep(0.01)
            assert started.is_set()
            for _ in range(2):
                task.cancel()
                await asyncio.sleep(0.01)
                assert not task.done()
                with pytest.raises(ConflictError, match="in progress"):
                    with service.operation_lock():
                        pytest.fail("The transfer lock was released before its worker stopped.")
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            with service.operation_lock():
                pass
        finally:
            release.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


async def test_blocking_transfer_returns_results_and_propagates_failures():
    assert await blocking_operation(lambda: "saved") == "saved"

    def fail():
        raise ValueError("Transport failed.")

    with pytest.raises(ValueError, match="Transport failed"):
        await blocking_operation(fail)


async def test_library_type_filter_has_all_supported_options(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert '<option value="prompt"' in response.text
    assert '<option value="workflow"' in response.text
    assert "</option value=" not in response.text
    assert 'aria-label="Type"' in response.text
