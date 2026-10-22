"""Category validation and hierarchy maintenance."""

from uuid import uuid4

import aiosqlite

from promptlibrary.services.validation import NotFoundError, colour_value, title_value


class CategoryService:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def create(
        self, name: str, parent_id: str | None = None, colour: str | None = None
    ) -> str:
        identity = str(uuid4())
        await self.db.execute(
            "INSERT INTO categories (id,name,parent_id,colour) VALUES (?,?,?,?)",
            (identity, title_value(name, 100), parent_id, colour_value(colour) if colour else None),
        )
        return identity

    async def update(
        self,
        identity: str,
        name: str,
        colour: str | None = None,
        parent_id: str | None = None,
        *,
        change_parent: bool = False,
    ) -> None:
        if change_parent and parent_id:
            cursor = await self.db.execute(
                """WITH RECURSIVE descendants(id) AS (
                     SELECT id FROM categories WHERE id=? UNION
                     SELECT c.id FROM categories c JOIN descendants d ON c.parent_id=d.id)
                   SELECT 1 FROM descendants WHERE id=?""",
                (identity, parent_id),
            )
            if await cursor.fetchone():
                raise ValueError("A category cannot be its own ancestor.")
        cursor = await self.db.execute(
            """UPDATE categories SET name=?,colour=?,
               parent_id=CASE WHEN ? THEN ? ELSE parent_id END WHERE id=?""",
            (
                title_value(name, 100),
                colour_value(colour) if colour else None,
                change_parent,
                parent_id,
                identity,
            ),
        )
        if not cursor.rowcount:
            raise NotFoundError("Category not found.")

    async def delete(self, identity: str) -> None:
        cursor = await self.db.execute("DELETE FROM categories WHERE id=?", (identity,))
        if not cursor.rowcount:
            raise NotFoundError("Category not found.")
