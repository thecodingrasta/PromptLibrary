"""Project groupings and typed labels shared by the web and agent interfaces."""

from uuid import uuid4

import aiosqlite

from promptlibrary.services.validation import NotFoundError, Record, colour_value, title_value

LABEL_TYPES = ("language", "framework", "platform", "model", "custom")


class ProjectService:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def list_projects(self, include_archived: bool = False) -> list[Record]:
        cursor = await self.db.execute(
            """SELECT p.*,
               (SELECT COUNT(*) FROM prompts WHERE project_id=p.id) AS prompt_count,
               (SELECT COUNT(*) FROM workflows WHERE project_id=p.id) AS workflow_count
               FROM projects p WHERE (? OR is_archived=0) ORDER BY p.name COLLATE NOCASE""",
            (include_archived,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def get_project(self, project_id: str) -> Record | None:
        cursor = await self.db.execute(
            """SELECT p.*,
               (SELECT COUNT(*) FROM prompts WHERE project_id=p.id) AS prompt_count,
               (SELECT COUNT(*) FROM workflows WHERE project_id=p.id) AS workflow_count
               FROM projects p WHERE p.id=?""",
            (project_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row is not None else None

    async def create_project(
        self,
        name: str,
        description: str = "",
        colour: str | None = None,
        icon: str | None = None,
    ) -> str:
        project_id = str(uuid4())
        await self.db.execute(
            "INSERT INTO projects (id,name,description,colour,icon) VALUES (?,?,?,?,?)",
            (
                project_id,
                title_value(name),
                description,
                colour_value(colour) if colour else None,
                icon,
            ),
        )
        return project_id

    async def update_project(
        self,
        project_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        colour: str | None = None,
        icon: str | None = None,
        is_archived: bool | None = None,
    ) -> None:
        cursor = await self.db.execute(
            """UPDATE projects SET name=COALESCE(?,name),
               description=COALESCE(?,description),colour=COALESCE(?,colour),
               icon=COALESCE(?,icon),is_archived=COALESCE(?,is_archived),
               updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?""",
            (
                title_value(name) if name is not None else None,
                description,
                colour_value(colour) if colour else None,
                icon,
                is_archived,
                project_id,
            ),
        )
        if not cursor.rowcount:
            raise NotFoundError("Project not found.")

    async def delete_project(self, project_id: str) -> None:
        cursor = await self.db.execute("DELETE FROM projects WHERE id=?", (project_id,))
        if not cursor.rowcount:
            raise NotFoundError("Project not found.")

    async def archive_project(self, project_id: str) -> None:
        await self.update_project(project_id, is_archived=True)


class LabelService:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def list_labels(self, label_type: str | None = None) -> list[Record]:
        cursor = await self.db.execute(
            "SELECT * FROM labels WHERE (? IS NULL OR label_type=?) ORDER BY label_type,name",
            (label_type, label_type),
        )
        return [dict(row) for row in await cursor.fetchall()]

    @staticmethod
    def _type(value: str) -> str:
        if value not in LABEL_TYPES:
            raise ValueError("Unknown label type.")
        return value

    async def create_label(
        self,
        name: str,
        label_type: str = "custom",
        colour: str | None = None,
        icon: str | None = None,
    ) -> str:
        label_id = str(uuid4())
        await self.db.execute(
            "INSERT INTO labels (id,name,label_type,colour,icon) VALUES (?,?,?,?,?)",
            (
                label_id,
                title_value(name, maximum=60),
                self._type(label_type),
                colour_value(colour) if colour else None,
                icon,
            ),
        )
        return label_id

    async def update_label(
        self,
        label_id: str,
        name: str,
        label_type: str,
        colour: str | None = None,
        icon: str | None = None,
    ) -> None:
        cursor = await self.db.execute(
            "UPDATE labels SET name=?,label_type=?,colour=COALESCE(?,colour),"
            "icon=COALESCE(?,icon) WHERE id=?",
            (
                title_value(name, maximum=60),
                self._type(label_type),
                colour_value(colour) if colour else None,
                icon,
                label_id,
            ),
        )
        if not cursor.rowcount:
            raise NotFoundError("Label not found.")

    async def delete_label(self, label_id: str) -> None:
        cursor = await self.db.execute("DELETE FROM labels WHERE id=?", (label_id,))
        if not cursor.rowcount:
            raise NotFoundError("Label not found.")

    async def assign_label_to_prompt(self, prompt_id: str, label_id: str) -> None:
        await self.db.execute(
            "INSERT OR IGNORE INTO prompt_labels (prompt_id,label_id) VALUES (?,?)",
            (prompt_id, label_id),
        )

    async def remove_label_from_prompt(self, prompt_id: str, label_id: str) -> None:
        await self.db.execute(
            "DELETE FROM prompt_labels WHERE prompt_id=? AND label_id=?",
            (prompt_id, label_id),
        )

    async def get_prompt_labels(self, prompt_id: str) -> list[Record]:
        cursor = await self.db.execute(
            """SELECT l.* FROM labels l JOIN prompt_labels pl ON pl.label_id=l.id
               WHERE pl.prompt_id=? ORDER BY l.label_type,l.name""",
            (prompt_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def assign_label_to_workflow(self, workflow_id: str, label_id: str) -> None:
        await self.db.execute(
            "INSERT OR IGNORE INTO workflow_labels (workflow_id,label_id) VALUES (?,?)",
            (workflow_id, label_id),
        )

    async def remove_label_from_workflow(self, workflow_id: str, label_id: str) -> None:
        await self.db.execute(
            "DELETE FROM workflow_labels WHERE workflow_id=? AND label_id=?",
            (workflow_id, label_id),
        )

    async def set_labels(self, item_type: str, item_id: str, label_ids: list[str]) -> None:
        # Table and column names come only from this closed mapping, never from user input.
        mapping = {
            "prompt": ("prompt_labels", "prompt_id"),
            "workflow": ("workflow_labels", "workflow_id"),
        }
        if item_type not in mapping:
            raise ValueError("Unknown item type.")
        table, column = mapping[item_type]
        await self.db.execute(f"DELETE FROM {table} WHERE {column}=?", (item_id,))  # noqa: S608 - identifiers are selected from a closed schema allowlist.
        await self.db.executemany(
            f"INSERT INTO {table} ({column},label_id) VALUES (?,?)",  # noqa: S608 - identifiers are selected from a closed schema allowlist.
            [(item_id, label_id) for label_id in dict.fromkeys(label_ids)],
        )

    async def find_label_by_name(self, name: str) -> Record | None:
        cursor = await self.db.execute("SELECT * FROM labels WHERE LOWER(name)=LOWER(?)", (name,))
        row = await cursor.fetchone()
        return dict(row) if row is not None else None
