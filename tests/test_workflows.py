"""Tests for workflows, projects, labels, and new MCP tools."""

import json
import os

import pytest

os.environ.setdefault("PROMPTLIB_DEBUG", "true")

from promptlibrary.database import get_db, init_db
from promptlibrary.mcp.server import call_tool
from promptlibrary.services.project_service import LabelService, ProjectService
from promptlibrary.services.workflow_service import WorkflowService


def _parse(result) -> dict | list:
    return json.loads(result[0].text)


@pytest.fixture(autouse=True)
async def setup_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTLIB_DATA_DIR", str(tmp_path))
    from promptlibrary.config import Settings

    new_settings = Settings()
    monkeypatch.setattr("promptlibrary.database.settings", new_settings)
    monkeypatch.setattr("promptlibrary.config.settings", new_settings)
    await init_db()


# === Workflow Service Tests ===


@pytest.mark.asyncio
async def test_workflow_create_and_get():
    async with get_db() as db:
        svc = WorkflowService(db)
        wf_id = await svc.create_workflow(name="Test Flow", description="A test")
        await db.commit()

        wf = await svc.get_workflow(wf_id)
        assert wf is not None
        assert wf["name"] == "Test Flow"
        assert wf["stages"] == []


@pytest.mark.asyncio
async def test_workflow_add_stages():
    async with get_db() as db:
        svc = WorkflowService(db)
        wf_id = await svc.create_workflow(name="Multi-Stage")

        await svc.add_stage(wf_id, title="Stage 1", body="Research {{TOPIC}}", mode="standard")
        await svc.add_stage(
            wf_id, title="Stage 2", body="{{stage_1_output}}\n\nAnalyze.", mode="high_reasoning"
        )
        await db.commit()

        wf = await svc.get_workflow(wf_id)
        assert len(wf["stages"]) == 2
        assert wf["stages"][0]["stage_number"] == 1
        assert wf["stages"][1]["stage_number"] == 2
        assert wf["stages"][0]["mode"] == "standard"
        assert wf["stages"][1]["mode"] == "high_reasoning"


@pytest.mark.asyncio
async def test_workflow_render_stage_variables():
    async with get_db() as db:
        svc = WorkflowService(db)
        wf_id = await svc.create_workflow(name="Render Test")
        await svc.add_stage(wf_id, title="S1", body="Topic: {{TOPIC}}\nSources: {{SOURCES}}")
        await db.commit()

        wf = await svc.get_workflow(wf_id)
        rendered = svc.render_stage(wf["stages"][0], {"TOPIC": "Rust async", "SOURCES": "tokio.rs"})
        assert "Rust async" in rendered
        assert "tokio.rs" in rendered
        assert "{{TOPIC}}" not in rendered


@pytest.mark.asyncio
async def test_workflow_extract_variables():
    svc = WorkflowService(None)  # DB not needed for this
    variables = svc.extract_variables("Hello {{NAME}}, research {{TOPIC}} using {{SOURCES}}")
    assert set(variables) == {"NAME", "TOPIC", "SOURCES"}


@pytest.mark.asyncio
async def test_workflow_delete_stage():
    async with get_db() as db:
        svc = WorkflowService(db)
        wf_id = await svc.create_workflow(name="Delete Stage")
        await svc.add_stage(wf_id, title="S1", body="first")
        s2 = await svc.add_stage(wf_id, title="S2", body="second")
        await svc.add_stage(wf_id, title="S3", body="third")
        await db.commit()

        await svc.delete_stage(s2)
        await db.commit()

        wf = await svc.get_workflow(wf_id)
        assert len(wf["stages"]) == 2
        assert wf["stages"][0]["title"] == "S1"
        assert wf["stages"][1]["title"] == "S3"
        # Renumbered
        assert wf["stages"][1]["stage_number"] == 2


@pytest.mark.asyncio
async def test_workflow_delete():
    async with get_db() as db:
        svc = WorkflowService(db)
        wf_id = await svc.create_workflow(name="To Delete")
        await svc.add_stage(wf_id, title="S1", body="x")
        await db.commit()

        await svc.delete_workflow(wf_id)
        await db.commit()

        assert await svc.get_workflow(wf_id) is None


@pytest.mark.asyncio
async def test_workflow_list():
    async with get_db() as db:
        svc = WorkflowService(db)
        await svc.create_workflow(name="Alpha")
        await svc.create_workflow(name="Beta")
        await db.commit()

        all_wf = await svc.list_workflows()
        assert len(all_wf) == 2

        searched = await svc.list_workflows(search="Alpha")
        assert len(searched) == 1


# === Project Service Tests ===


@pytest.mark.asyncio
async def test_project_crud():
    async with get_db() as db:
        svc = ProjectService(db)
        proj_id = await svc.create_project(
            name="My App", description="Main project", colour="#4f46e5"
        )
        await db.commit()

        proj = await svc.get_project(proj_id)
        assert proj["name"] == "My App"
        assert proj["prompt_count"] == 0

        await svc.update_project(proj_id, name="Renamed App")
        await db.commit()

        proj = await svc.get_project(proj_id)
        assert proj["name"] == "Renamed App"


@pytest.mark.asyncio
async def test_project_archive():
    async with get_db() as db:
        svc = ProjectService(db)
        proj_id = await svc.create_project(name="Archive Me")
        await db.commit()

        await svc.archive_project(proj_id)
        await db.commit()

        active = await svc.list_projects(include_archived=False)
        assert not any(p["id"] == proj_id for p in active)

        all_projects = await svc.list_projects(include_archived=True)
        assert any(p["id"] == proj_id for p in all_projects)


@pytest.mark.asyncio
async def test_project_delete():
    async with get_db() as db:
        svc = ProjectService(db)
        proj_id = await svc.create_project(name="Delete Me")
        await db.commit()

        await svc.delete_project(proj_id)
        await db.commit()

        assert await svc.get_project(proj_id) is None


# === Label Service Tests ===


@pytest.mark.asyncio
async def test_labels_seeded():
    """Pre-seeded labels exist after init_db."""
    async with get_db() as db:
        svc = LabelService(db)
        labels = await svc.list_labels()
        assert len(labels) >= 29  # All seeded labels

        languages = await svc.list_labels(label_type="language")
        assert any(label["name"] == "Python" for label in languages)
        assert any(label["name"] == "Rust" for label in languages)

        frameworks = await svc.list_labels(label_type="framework")
        assert any(label["name"] == "FastAPI" for label in frameworks)

        models = await svc.list_labels(label_type="model")
        assert any(label["name"] == "Claude" for label in models)


@pytest.mark.asyncio
async def test_label_assign_to_prompt():
    async with get_db() as db:
        # Create a prompt first
        from promptlibrary.services.prompt_service import PromptService

        psvc = PromptService(db)
        await psvc.create_prompt(prompt_id="lbl-test-1", title="Label Test", body="x")
        await db.commit()

        lsvc = LabelService(db)
        python = await lsvc.find_label_by_name("Python")
        assert python is not None

        await lsvc.assign_label_to_prompt("lbl-test-1", python["id"])
        await db.commit()

        labels = await lsvc.get_prompt_labels("lbl-test-1")
        assert len(labels) == 1
        assert labels[0]["name"] == "Python"


@pytest.mark.asyncio
async def test_label_create_custom():
    async with get_db() as db:
        svc = LabelService(db)
        await svc.create_label(name="MyCustomLabel", label_type="custom", colour="#ff0000")
        await db.commit()

        found = await svc.find_label_by_name("MyCustomLabel")
        assert found is not None
        assert found["label_type"] == "custom"


@pytest.mark.asyncio
async def test_label_delete():
    async with get_db() as db:
        svc = LabelService(db)
        label_id = await svc.create_label(name="ToDelete", label_type="custom")
        await db.commit()

        await svc.delete_label(label_id)
        await db.commit()

        assert await svc.find_label_by_name("ToDelete") is None


# === MCP Workflow Tools Tests ===


@pytest.mark.asyncio
async def test_mcp_create_workflow():
    result = await call_tool(
        "create_workflow", {"name": "MCP Workflow", "description": "Created via agent"}
    )
    data = _parse(result)
    assert data["status"] == "created"
    assert "id" in data


@pytest.mark.asyncio
async def test_mcp_add_and_get_workflow_stages():
    # Create
    r = await call_tool("create_workflow", {"name": "Stage Test"})
    wf_id = _parse(r)["id"]

    # Add stages
    r = await call_tool(
        "add_workflow_stage",
        {"workflow_id": wf_id, "title": "Prep", "body": "Research {{TOPIC}}", "mode": "standard"},
    )
    assert _parse(r)["status"] == "added"

    r = await call_tool(
        "add_workflow_stage",
        {
            "workflow_id": wf_id,
            "title": "Execute",
            "body": "{{stage_1_output}}\nDo the work.",
            "mode": "deep_research",
            "output_type": "markdown",
        },
    )
    assert _parse(r)["status"] == "added"

    # Get workflow
    r = await call_tool("get_workflow", {"id": wf_id})
    wf = _parse(r)
    assert wf["name"] == "Stage Test"
    assert len(wf["stages"]) == 2
    assert wf["stages"][0]["mode"] == "standard"
    assert wf["stages"][1]["mode"] == "deep_research"


@pytest.mark.asyncio
async def test_mcp_render_workflow_stage():
    r = await call_tool("create_workflow", {"name": "Render Test"})
    wf_id = _parse(r)["id"]
    await call_tool(
        "add_workflow_stage",
        {"workflow_id": wf_id, "title": "S1", "body": "Topic: {{TOPIC}}, Sources: {{SOURCES}}"},
    )

    r = await call_tool(
        "render_workflow_stage",
        {
            "workflow_id": wf_id,
            "stage_number": 1,
            "variables": {"TOPIC": "AI safety", "SOURCES": "arxiv.org"},
        },
    )
    data = _parse(r)
    assert "AI safety" in data["rendered_body"]
    assert "arxiv.org" in data["rendered_body"]
    assert "{{TOPIC}}" not in data["rendered_body"]


@pytest.mark.asyncio
async def test_mcp_list_workflows():
    await call_tool("create_workflow", {"name": "WF Alpha"})
    await call_tool("create_workflow", {"name": "WF Beta"})

    r = await call_tool("list_workflows", {})
    wfs = _parse(r)
    assert len(wfs) >= 2


@pytest.mark.asyncio
async def test_mcp_list_projects():
    await call_tool("create_project", {"name": "Proj1"})
    r = await call_tool("list_projects", {})
    projects = _parse(r)
    assert any(p["name"] == "Proj1" for p in projects)


@pytest.mark.asyncio
async def test_mcp_create_project():
    r = await call_tool(
        "create_project",
        {"name": "Agent Project", "description": "Made by agent", "colour": "#10b981"},
    )
    data = _parse(r)
    assert data["status"] == "created"
    assert data["name"] == "Agent Project"


@pytest.mark.asyncio
async def test_mcp_assign_labels():
    # Create a prompt
    r = await call_tool("create_prompt", {"title": "Labeled", "body": "x"})
    prompt_id = _parse(r)["id"]

    # Assign labels
    r = await call_tool(
        "assign_labels", {"prompt_id": prompt_id, "labels": ["Python", "FastAPI", "Web"]}
    )
    data = _parse(r)
    assert "Python" in data["assigned"]
    assert "FastAPI" in data["assigned"]
    assert "Web" in data["assigned"]


@pytest.mark.asyncio
async def test_mcp_list_labels():
    r = await call_tool("list_labels", {"type": "framework"})
    labels = _parse(r)
    assert any(label["name"] == "React" for label in labels)
    assert any(label["name"] == "FastAPI" for label in labels)

    r = await call_tool("list_labels", {})
    all_labels = _parse(r)
    assert len(all_labels) >= 29


@pytest.mark.asyncio
async def test_mcp_workflow_not_found():
    r = await call_tool("get_workflow", {"id": "00000000-0000-0000-0000-000000000000"})
    data = _parse(r)
    assert "error" in data


@pytest.mark.asyncio
async def test_mcp_render_stage_not_found():
    r = await call_tool("create_workflow", {"name": "X"})
    wf_id = _parse(r)["id"]

    r = await call_tool("render_workflow_stage", {"workflow_id": wf_id, "stage_number": 99})
    data = _parse(r)
    assert "error" in data
