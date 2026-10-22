"""Guided execution records; inference stays with the user's chosen human or agent."""

import json
from uuid import uuid4

import aiosqlite

from promptlibrary.services.validation import ConflictError, NotFoundError, Record
from promptlibrary.services.workflow_service import PLACEHOLDER, STAGE_OUTPUT, WorkflowService


class RunService:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    @staticmethod
    def required_inputs(workflow: Record) -> list[str]:
        required: set[str] = set()
        for stage in workflow["stages"]:
            text = stage["instructions"] + "\n" + stage["body"]
            for variable in PLACEHOLDER.findall(text):
                dependency = STAGE_OUTPUT.fullmatch(variable)
                if dependency:
                    if int(dependency[1]) >= stage["stage_number"]:
                        raise ValueError("Stage outputs must refer to an earlier stage.")
                else:
                    required.add(variable)
        return sorted(required)

    async def start(self, workflow_id: str, variables: dict[str, str]) -> str:
        workflow = await WorkflowService(self.db).require_workflow(workflow_id)
        if not workflow["stages"]:
            raise ValueError("Add at least one stage before starting a run.")
        required = self.required_inputs(workflow)
        missing = [
            name for name in required if name not in variables or not variables[name].strip()
        ]
        if missing:
            raise ValueError("Missing inputs: " + ", ".join(missing))
        if any(STAGE_OUTPUT.fullmatch(key) for key in variables):
            raise ValueError("Stage output variables are supplied by the run, not by user inputs.")
        run_id = str(uuid4())
        await self.db.execute(
            "INSERT INTO workflow_runs "
            "(id,workflow_id,snapshot_json,variables_json) VALUES (?,?,?,?)",
            (run_id, workflow_id, json.dumps(workflow), json.dumps(variables)),
        )
        return run_id

    async def list_runs(self, workflow_id: str) -> list[Record]:
        cursor = await self.db.execute(
            """SELECT id,workflow_id,status,current_stage,created_at,updated_at
               FROM workflow_runs WHERE workflow_id=? ORDER BY created_at DESC, id DESC""",
            (workflow_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def get_run(self, run_id: str) -> Record:
        cursor = await self.db.execute("SELECT * FROM workflow_runs WHERE id=?", (run_id,))
        row = await cursor.fetchone()
        if row is None:
            raise NotFoundError("Run not found.")
        run: Record = dict(row)
        run["snapshot"] = json.loads(run.pop("snapshot_json"))
        run["variables"] = json.loads(run.pop("variables_json"))
        cursor = await self.db.execute(
            "SELECT * FROM workflow_run_steps WHERE run_id=? ORDER BY stage_number",
            (run_id,),
        )
        run["steps"] = [dict(step) for step in await cursor.fetchall()]
        run["rendered_input"] = ""
        if run["status"] == "running":
            run["stage"] = run["snapshot"]["stages"][run["current_stage"] - 1]
            run["rendered_input"] = self._render(run, run["current_stage"])
        return run

    @staticmethod
    def _render(run: Record, position: int) -> str:
        values = dict(run["variables"])
        values.update(
            {f"stage_{step['stage_number']}_output": step["output"] for step in run["steps"]}
        )
        stage = run["snapshot"]["stages"][position - 1]
        text = "\n\n".join(part for part in (stage["instructions"], stage["body"]) if part)
        missing = set(PLACEHOLDER.findall(text)) - values.keys()
        if missing:
            raise ConflictError("Run has unresolved inputs: " + ", ".join(sorted(missing)))
        return PLACEHOLDER.sub(lambda match: values[match[1]], text)

    async def complete_step(self, run_id: str, expected_stage: int, output: str) -> Record:
        if not output.strip() or len(output) > 2_000_000:
            raise ValueError("Output must contain between 1 and 2,000,000 characters.")
        if not self.db.in_transaction:
            await self.db.execute("BEGIN IMMEDIATE")
        await self.db.execute("SAVEPOINT complete_run_step")
        try:
            # Compare-and-swap prevents duplicate submissions from completing the next stage.
            cursor = await self.db.execute(
                """UPDATE workflow_runs SET current_stage=current_stage+1,
                   updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                   WHERE id=? AND current_stage=? AND status='running' RETURNING id""",
                (run_id, expected_stage),
            )
            if await cursor.fetchone() is None:
                raise ConflictError(
                    "This stage has already changed. Reload the run before submitting."
                )
            # Read the saved snapshot without attempting to render the not-yet-completed next step.
            cursor = await self.db.execute(
                "SELECT snapshot_json,variables_json FROM workflow_runs WHERE id=?", (run_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                raise RuntimeError("The database returned no result for an atomic operation.")
            run: Record = {"snapshot": json.loads(row[0]), "variables": json.loads(row[1])}
            cursor = await self.db.execute(
                "SELECT * FROM workflow_run_steps WHERE run_id=? ORDER BY stage_number", (run_id,)
            )
            run["steps"] = [dict(step) for step in await cursor.fetchall()]
            rendered = self._render(run, expected_stage)
            await self.db.execute(
                "INSERT INTO workflow_run_steps "
                "(run_id,stage_number,rendered_input,output) VALUES (?,?,?,?)",
                (run_id, expected_stage, rendered, output),
            )
            if expected_stage == len(run["snapshot"]["stages"]):
                await self.db.execute(
                    "UPDATE workflow_runs SET status='completed' WHERE id=?", (run_id,)
                )
            result = await self.get_run(run_id)
            await self.db.execute("RELEASE complete_run_step")
            return result
        except BaseException:
            await self.db.execute("ROLLBACK TO complete_run_step")
            await self.db.execute("RELEASE complete_run_step")
            raise

    async def cancel(self, run_id: str) -> None:
        cursor = await self.db.execute(
            "UPDATE workflow_runs SET "
            "status='cancelled',updated_at=datetime('now') WHERE id=? AND status='running'",
            (run_id,),
        )
        if not cursor.rowcount:
            raise ConflictError("Only a running workflow can be cancelled.")
