"""Reusable prompt stages and deterministic, ordered workflow composition."""

import json
import re
from uuid import uuid4

import aiosqlite

from promptlibrary.services.validation import (
    ConflictError,
    NotFoundError,
    Record,
    ensure_status,
    title_value,
)

PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
STAGE_OUTPUT = re.compile(r"stage_([1-9][0-9]*)_output\Z")
MODES = {"standard", "deep_research", "high_reasoning", "extra_high_reasoning"}
OUTPUT_TYPES = {"text", "markdown", "code", "json"}


class WorkflowService:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    @staticmethod
    def _validate_text(*values: str | None) -> None:
        if any(value is not None and len(value) > 2_000_000 for value in values):
            raise ValueError("Each text field must be at most 2,000,000 characters.")

    async def list_workflows(
        self,
        search: str | None = None,
        project_id: str | None = None,
    ) -> list[Record]:
        query = """SELECT w.*, (SELECT COUNT(*) FROM workflow_stages s
                    WHERE s.workflow_id=w.id) AS stage_count FROM workflows w WHERE 1=1"""
        parameters: list[str] = []
        if search:
            query += " AND (name LIKE ? OR description LIKE ?)"
            parameters.extend([f"%{search}%", f"%{search}%"])
        if project_id:
            query += " AND project_id=?"
            parameters.append(project_id)
        cursor = await self.db.execute(query + " ORDER BY updated_at DESC, name", parameters)
        return [dict(row) for row in await cursor.fetchall()]

    async def get_workflow(self, workflow_id: str) -> Record | None:
        cursor = await self.db.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        workflow: Record = dict(row)
        cursor = await self.db.execute(
            """SELECT s.*, p.title AS source_title, p.body AS source_body
               FROM workflow_stages s LEFT JOIN prompts p ON p.id=s.prompt_id
               WHERE s.workflow_id=? ORDER BY s.stage_number""",
            (workflow_id,),
        )
        workflow["stages"] = [dict(stage) for stage in await cursor.fetchall()]
        for stage in workflow["stages"]:
            stage["variables"] = json.loads(stage["variables_json"])
            if stage["prompt_id"]:
                if stage["source_body"] is None:
                    raise ConflictError("A linked prompt is missing. Repair or detach that stage.")
                stage["body"] = stage["source_body"]
        for name, table, foreign_key in (
            ("labels", "labels", "label_id"),
            ("tags", "tags", "tag_id"),
        ):
            cursor = await self.db.execute(
                f"SELECT t.* FROM {table} t JOIN workflow_{name} j ON j.{foreign_key}=t.id "  # noqa: S608 - identifiers are selected from a closed schema allowlist.
                "WHERE j.workflow_id=? ORDER BY t.name",
                (workflow_id,),
            )
            workflow[name] = [dict(item) for item in await cursor.fetchall()]
        return workflow

    async def require_workflow(self, workflow_id: str) -> Record:
        workflow = await self.get_workflow(workflow_id)
        if workflow is None:
            raise NotFoundError("Workflow not found.")
        return workflow

    async def create_workflow(
        self,
        name: str,
        description: str = "",
        project_id: str | None = None,
        category_id: str | None = None,
        status: str = "draft",
        tags: list[str] | None = None,
    ) -> str:
        name = title_value(name)
        self._validate_text(description)
        status = await ensure_status(self.db, status)
        workflow_id = str(uuid4())
        await self.db.execute(
            "INSERT INTO workflows "
            "(id,name,description,project_id,category_id,status) VALUES (?,?,?,?,?,?)",
            (workflow_id, name, description, project_id, category_id, status),
        )
        if tags is not None:
            await self.set_tags(workflow_id, tags)
        return workflow_id

    async def update_workflow(
        self,
        workflow_id: str,
        name: str | None = None,
        description: str | None = None,
        project_id: str | None = None,
        category_id: str | None = None,
        status: str | None = None,
        tags: list[str] | None = None,
    ) -> None:
        await self.require_workflow(workflow_id)
        self._validate_text(description)
        assignments = ["updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')"]
        parameters: list[str | None] = []
        for field, value in (
            ("name", title_value(name) if name is not None else None),
            ("description", description),
            ("project_id", project_id),
            ("category_id", category_id),
            ("status", await ensure_status(self.db, status) if status is not None else None),
        ):
            if value is not None:
                assignments.append(f"{field}=?")
                parameters.append(None if field.endswith("_id") and not value else value)
        parameters.append(workflow_id)
        await self.db.execute(
            f"UPDATE workflows SET {', '.join(assignments)} WHERE id=?",  # noqa: S608 - closed field list.
            parameters,
        )
        if tags is not None:
            await self.set_tags(workflow_id, tags)

    async def set_tags(self, workflow_id: str, names: list[str]) -> None:
        names = sorted({title_value(name, 50) for name in names if name.strip()})
        if len(names) > 100 or any("," in name for name in names):
            raise ValueError("Use at most 100 tags, without commas inside a tag.")
        await self.db.execute("DELETE FROM workflow_tags WHERE workflow_id=?", (workflow_id,))
        for name in names:
            await self.db.execute(
                "INSERT OR IGNORE INTO tags (id,name) VALUES (?,?)", (str(uuid4()), name)
            )
            await self.db.execute(
                "INSERT INTO workflow_tags SELECT ?, id FROM tags WHERE name=?",
                (workflow_id, name),
            )

    async def toggle_favourite(self, workflow_id: str) -> bool:
        cursor = await self.db.execute(
            "UPDATE workflows SET is_favourite=1-is_favourite WHERE id=? RETURNING is_favourite",
            (workflow_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise NotFoundError("Workflow not found.")
        return bool(row[0])

    async def delete_workflow(self, workflow_id: str) -> None:
        cursor = await self.db.execute("DELETE FROM workflows WHERE id=?", (workflow_id,))
        if not cursor.rowcount:
            raise NotFoundError("Workflow not found.")

    async def add_stage(
        self,
        workflow_id: str,
        title: str,
        body: str = "",
        instructions: str = "",
        variables: list[Record] | None = None,
        mode: str = "standard",
        output_type: str = "text",
        prompt_id: str | None = None,
        link_prompt: bool = False,
    ) -> str:
        title = title_value(title)
        self._validate_text(body, instructions)
        if mode not in MODES or output_type not in OUTPUT_TYPES:
            raise ValueError("Unknown stage mode or output type.")
        await self.require_workflow(workflow_id)
        if prompt_id:
            cursor = await self.db.execute("SELECT body FROM prompts WHERE id=?", (prompt_id,))
            row = await cursor.fetchone()
            if row is None:
                raise NotFoundError("Prompt not found.")
            body = row[0]
        if link_prompt and not prompt_id:
            raise ValueError("Choose a prompt to link.")
        stage_id = str(uuid4())
        await self.db.execute(
            """INSERT INTO workflow_stages
(id,workflow_id,stage_number,title,body,instructions,variables_json,mode,output_type,prompt_id)
               SELECT ?, ?, COALESCE(MAX(stage_number),0)+1, ?, ?, ?, ?, ?, ?, ?
               FROM workflow_stages WHERE workflow_id=?""",
            (
                stage_id,
                workflow_id,
                title,
                body,
                instructions,
                json.dumps(variables or []),
                mode,
                output_type,
                prompt_id if link_prompt else None,
                workflow_id,
            ),
        )
        await self._touch(workflow_id)
        return stage_id

    async def require_stage(self, stage_id: str, workflow_id: str | None = None) -> Record:
        cursor = await self.db.execute("SELECT * FROM workflow_stages WHERE id=?", (stage_id,))
        row = await cursor.fetchone()
        if row is None or (workflow_id is not None and row["workflow_id"] != workflow_id):
            raise NotFoundError("Stage not found in this workflow.")
        return dict(row)

    async def update_stage(
        self,
        stage_id: str,
        title: str | None = None,
        body: str | None = None,
        instructions: str | None = None,
        variables: list[Record] | None = None,
        mode: str | None = None,
        output_type: str | None = None,
        detach: bool = False,
    ) -> None:
        stage = await self.require_stage(stage_id)
        self._validate_text(body, instructions)
        if mode is not None and mode not in MODES:
            raise ValueError("Unknown stage mode.")
        if output_type is not None and output_type not in OUTPUT_TYPES:
            raise ValueError("Unknown output type.")
        if stage["prompt_id"] and body is not None and not detach:
            raise ConflictError(
                "Edit the source prompt, or detach this stage before changing its body."
            )
        if detach and stage["prompt_id"]:
            cursor = await self.db.execute(
                "SELECT body FROM prompts WHERE id=?", (stage["prompt_id"],)
            )
            source = await cursor.fetchone()
            if source and body is None:
                body = source[0]
            await self.db.execute(
                "UPDATE workflow_stages SET prompt_id=NULL WHERE id=?", (stage_id,)
            )
        assignments: list[str] = []
        parameters: list[str] = []
        for field, value in (
            ("title", title_value(title) if title is not None else None),
            ("body", body),
            ("instructions", instructions),
            ("variables_json", json.dumps(variables) if variables is not None else None),
            ("mode", mode),
            ("output_type", output_type),
        ):
            if value is not None:
                assignments.append(f"{field}=?")
                parameters.append(value)
        if assignments:
            await self.db.execute(
                f"UPDATE workflow_stages SET {', '.join(assignments)} WHERE id=?",  # noqa: S608 - identifiers are selected from a closed schema allowlist.
                [*parameters, stage_id],
            )
        await self._touch(stage["workflow_id"])

    async def _apply_order(
        self, workflow_id: str, stages: list[Record], mapping: dict[int, int]
    ) -> None:
        updates: list[tuple[int, str, str, str]] = []
        for number, stage in enumerate(stages, 1):

            def replace(
                match: re.Match[str], current_stage: Record = stage, position: int = number
            ) -> str:
                dependency = STAGE_OUTPUT.fullmatch(match[1])
                if not dependency:
                    return match[0]
                old = int(dependency[1])
                if old not in mapping:
                    raise ConflictError(
                        "Another stage uses this stage's output. Remove that reference first."
                    )
                new = mapping[old]
                if current_stage["prompt_id"] and new != old:
                    raise ConflictError(
                        "Detach linked stages with positional output references before reordering."
                    )
                if new >= position:
                    raise ConflictError(
                        "This order would make a stage depend on its own or a later output."
                    )
                return "{{stage_" + str(new) + "_output}}"

            body = PLACEHOLDER.sub(replace, stage["body"])
            instructions = PLACEHOLDER.sub(replace, stage["instructions"])
            updates.append((number, body, instructions, stage["id"]))
        # A temporary negative order avoids the UNIQUE constraint during swaps.
        await self.db.execute(
            "UPDATE workflow_stages SET stage_number=-stage_number WHERE workflow_id=?",
            (workflow_id,),
        )
        await self.db.executemany(
            "UPDATE workflow_stages SET stage_number=?,body=?,instructions=? WHERE id=?", updates
        )
        await self._touch(workflow_id)

    async def delete_stage(self, stage_id: str) -> None:
        stage = await self.require_stage(stage_id)
        workflow = await self.require_workflow(stage["workflow_id"])
        remaining = [item for item in workflow["stages"] if item["id"] != stage_id]
        mapping = {int(item["stage_number"]): index for index, item in enumerate(remaining, 1)}
        await self.db.execute("SAVEPOINT delete_stage")
        try:
            await self.db.execute("DELETE FROM workflow_stages WHERE id=?", (stage_id,))
            await self._apply_order(stage["workflow_id"], remaining, mapping)
            await self.db.execute("RELEASE delete_stage")
        except BaseException:
            await self.db.execute("ROLLBACK TO delete_stage")
            await self.db.execute("RELEASE delete_stage")
            raise

    async def reorder_stage(self, stage_id: str, new_position: int) -> None:
        stage = await self.require_stage(stage_id)
        workflow = await self.require_workflow(stage["workflow_id"])
        stages = workflow["stages"]
        if not 1 <= new_position <= len(stages):
            raise ValueError("Stage position is outside this workflow.")
        selected = next(item for item in stages if item["id"] == stage_id)
        stages.remove(selected)
        stages.insert(new_position - 1, selected)
        mapping = {int(item["stage_number"]): index for index, item in enumerate(stages, 1)}
        await self._apply_order(stage["workflow_id"], stages, mapping)

    async def _touch(self, workflow_id: str) -> None:
        await self.db.execute(
            "UPDATE workflows SET updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
            (workflow_id,),
        )

    def render_stage(self, stage: Record, variables: dict[str, str] | None = None) -> str:
        # One pass keeps placeholders in supplied values literal, rather than executing another
        # expansion.
        values = variables or {}
        return PLACEHOLDER.sub(lambda match: values.get(match[1], match[0]), stage["body"])

    def extract_variables(self, body: str) -> list[str]:
        return list(dict.fromkeys(PLACEHOLDER.findall(body)))
