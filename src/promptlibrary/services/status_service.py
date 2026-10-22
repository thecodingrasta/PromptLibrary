"""User-defined library statuses with stable keys and safe deletion rules."""

import re
from uuid import uuid4

import aiosqlite

from promptlibrary.services.validation import (
    ConflictError,
    NotFoundError,
    Record,
    colour_value,
    title_value,
)


class StatusService:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def list_statuses(self) -> list[Record]:
        cursor = await self.db.execute("SELECT * FROM status_definitions ORDER BY sort_order, name")
        return [dict(row) for row in await cursor.fetchall()]

    async def save_status(
        self,
        name: str,
        colour: str = "#6366f1",
        sort_order: int = 0,
        key: str | None = None,
    ) -> str:
        name = title_value(name, 60)
        colour = colour_value(colour)
        if key is None:
            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "status"
            key = f"{slug[:40]}-{uuid4().hex[:8]}"
            await self.db.execute(
                "INSERT INTO status_definitions (key,name,colour,sort_order) VALUES (?,?,?,?)",
                (key, name, colour, sort_order),
            )
        else:
            cursor = await self.db.execute(
                "UPDATE status_definitions SET name=?,colour=?,sort_order=? WHERE key=?",
                (name, colour, sort_order, key),
            )
            if not cursor.rowcount:
                raise NotFoundError("Status not found.")
        return key

    async def delete_status(self, key: str) -> None:
        if key in {"draft", "staged", "published"}:
            raise ConflictError("Default statuses can be renamed, but not deleted.")
        cursor = await self.db.execute(
            """SELECT 1 FROM prompts WHERE status=?
               UNION ALL SELECT 1 FROM workflows WHERE status=?
               UNION ALL SELECT 1 FROM prompt_versions WHERE status=? LIMIT 1""",
            (key, key, key),
        )
        if await cursor.fetchone():
            raise ConflictError(
                "This status is used by library items or version history. Rename it instead."
            )
        cursor = await self.db.execute("DELETE FROM status_definitions WHERE key=?", (key,))
        if not cursor.rowcount:
            raise NotFoundError("Status not found.")
