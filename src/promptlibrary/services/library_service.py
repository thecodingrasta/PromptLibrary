"""A single searchable view of prompts and workflows without duplicating their storage."""

import aiosqlite
from pydantic import BaseModel, Field

from promptlibrary.services.validation import Record


class LibraryFilter(BaseModel):
    q: str = ""
    category_id: str = ""
    project_id: str = ""
    status: str = ""
    tag: str = ""
    item_type: str = Field(default="", pattern=r"^(|prompt|workflow)$")
    favourites_only: bool = False
    page: int = Field(default=1, ge=1)


class LibraryService:
    PAGE_SIZE = 100

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def list_items(self, filters: LibraryFilter) -> tuple[list[Record], int]:
        query = """WITH items AS (
            SELECT p.id, p.title, p.body || ' ' || p.notes AS search_text,
                   p.status, p.category_id, p.project_id, p.is_favourite,
                   p.updated_at, 'prompt' AS item_type,
                   COALESCE((SELECT group_concat(t.name, ',') FROM tags t
                       JOIN prompt_tags pt ON pt.tag_id=t.id WHERE pt.prompt_id=p.id), '') AS
                    tag_names
            FROM prompts p
            UNION ALL
            SELECT w.id, w.name, w.description || ' ' ||
                   COALESCE((SELECT group_concat(s.title || ' ' || COALESCE(p.body, s.body) || '
                   ' || s.instructions, ' ')
                       FROM workflow_stages s LEFT JOIN prompts p ON p.id=s.prompt_id
                       WHERE s.workflow_id=w.id), ''),
                   w.status, w.category_id, w.project_id, w.is_favourite,
                   w.updated_at, 'workflow',
                   COALESCE((SELECT group_concat(t.name, ',') FROM tags t
                       JOIN workflow_tags wt ON wt.tag_id=t.id WHERE wt.workflow_id=w.id), '')
            FROM workflows w
        ) SELECT i.*, d.name AS status_name, d.colour AS status_colour
          FROM items i JOIN status_definitions d ON i.status=d.key WHERE 1=1"""
        parameters: list[str | int] = []
        if filters.q:
            query += " AND (i.title LIKE ? ESCAPE '\\' OR i.search_text LIKE ? ESCAPE '\\')"
            escaped = filters.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            parameters.extend([f"%{escaped}%", f"%{escaped}%"])
        for column in ("category_id", "project_id", "status", "item_type"):
            value = getattr(filters, column)
            if value:
                query += f" AND i.{column}=?"
                parameters.append(value)
        if filters.tag:
            query += " AND instr(',' || i.tag_names || ',', ',' || ? || ',') > 0"
            parameters.append(filters.tag)
        if filters.favourites_only:
            query += " AND i.is_favourite=1"
        cursor = await self.db.execute(f"SELECT COUNT(*) FROM ({query})", parameters)  # noqa: S608 - identifiers are selected from a closed schema allowlist.
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("The database returned no result for an atomic operation.")
        total = int(row[0])
        query += " ORDER BY i.updated_at DESC, i.title, i.id LIMIT ? OFFSET ?"
        cursor = await self.db.execute(
            query, [*parameters, self.PAGE_SIZE, (filters.page - 1) * self.PAGE_SIZE]
        )
        return [dict(row) for row in await cursor.fetchall()], total
