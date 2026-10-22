"""Core prompt management service."""

from uuid import UUID, uuid4

import aiosqlite

from promptlibrary.models import PromptStatus
from promptlibrary.services.validation import (
    ConflictError,
    NotFoundError,
    Record,
    ensure_status,
    next_revision,
    status_value,
    title_value,
)


class PromptService:
    """Handles prompt CRUD operations."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def list_prompts(
        self,
        search: str | None = None,
        category_id: UUID | None = None,
        status: str | PromptStatus | None = None,
        tag: str | None = None,
        favourites_only: bool = False,
        project_id: str | None = None,
    ) -> list[Record]:
        """List prompts with optional filters."""
        query = """
            SELECT DISTINCT p.id, p.title, p.status, p.category_id,
                   p.project_id, p.is_favourite, p.updated_at, p.created_at
            FROM prompts p
            LEFT JOIN prompt_tags pt ON pt.prompt_id = p.id
            LEFT JOIN tags t ON t.id = pt.tag_id
            WHERE 1=1
        """
        params: list[str | int] = []

        if search:
            query += " AND (p.title LIKE ? OR p.body LIKE ? OR p.notes LIKE ?)"
            like = f"%{search}%"
            params.extend([like, like, like])

        if category_id:
            query += " AND p.category_id = ?"
            params.append(str(category_id))

        if status:
            query += " AND p.status = ?"
            params.append(status_value(status))

        if tag:
            query += " AND t.name = ?"
            params.append(tag)

        if project_id:
            query += " AND p.project_id = ?"
            params.append(project_id)

        if favourites_only:
            query += " AND p.is_favourite = 1"

        query += " ORDER BY p.updated_at DESC"

        cursor = await self.db.execute(query, params)
        rows = await cursor.fetchall()

        prompts = []
        for row in rows:
            prompt = dict(row)
            # Fetch tags for each prompt
            tag_cursor = await self.db.execute(
                "SELECT t.id, t.name FROM tags t JOIN prompt_tags pt ON pt.tag_id = "
                "t.id WHERE pt.prompt_id = ?",
                (prompt["id"],),
            )
            prompt["tags"] = [dict(t) for t in await tag_cursor.fetchall()]
            prompts.append(prompt)

        return prompts

    async def get_prompt(self, prompt_id: UUID | str) -> Record | None:
        """Get a single prompt with full details."""
        cursor = await self.db.execute("SELECT * FROM prompts WHERE id = ?", (str(prompt_id),))
        row = await cursor.fetchone()
        if row is None:
            return None

        prompt = dict(row)
        tag_cursor = await self.db.execute(
            "SELECT t.id, t.name FROM tags t JOIN prompt_tags pt ON pt.tag_id = "
            "t.id WHERE pt.prompt_id = ?",
            (prompt["id"],),
        )
        prompt["tags"] = [dict(t) for t in await tag_cursor.fetchall()]
        return prompt

    async def create_prompt(
        self,
        prompt_id: str,
        title: str,
        body: str = "",
        notes: str = "",
        status: str | PromptStatus = PromptStatus.DRAFT,
        category_id: str | None = None,
        project_id: str | None = None,
        tags: list[str] | None = None,
    ) -> str:
        """Create a new prompt."""
        title = title_value(title)
        if len(body) > 2_000_000 or len(notes) > 2_000_000:
            raise ValueError("Prompt body and notes must each be at most 2,000,000 characters.")
        status = await ensure_status(self.db, status)
        await self.db.execute(
            """INSERT INTO prompts (id, title, body, notes, status, category_id, project_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (prompt_id, title, body, notes, status_value(status), category_id, project_id),
        )
        if tags:
            await self._set_tags(prompt_id, tags)
        return prompt_id

    async def update_prompt(
        self,
        prompt_id: str,
        title: str,
        body: str = "",
        notes: str = "",
        status: str | PromptStatus = PromptStatus.DRAFT,
        category_id: str | None = None,
        tags: list[str] | None = None,
        project_id: str | None = None,
        expected_updated_at: str | None = None,
    ) -> None:
        title = title_value(title)
        if len(body) > 2_000_000 or len(notes) > 2_000_000:
            raise ValueError("Prompt body and notes must each be at most 2,000,000 characters.")
        key = await ensure_status(self.db, status)
        current = await self.get_prompt(prompt_id)
        if current is None:
            raise NotFoundError("Prompt not found.")
        cursor = await self.db.execute(
            """UPDATE prompts SET title=?, body=?, notes=?, status=?, category_id=?,
               project_id=CASE WHEN ? IS NULL THEN project_id ELSE NULLIF(?, '') END,
               updated_at=? WHERE id=? AND (? IS NULL OR
               updated_at=?)""",
            (
                title,
                body,
                notes,
                key,
                category_id,
                project_id,
                project_id,
                next_revision(current["updated_at"]),
                prompt_id,
                expected_updated_at,
                expected_updated_at,
            ),
        )
        if not cursor.rowcount:
            if await self.get_prompt(prompt_id) is None:
                raise NotFoundError("Prompt not found.")
            raise ConflictError("This prompt changed elsewhere. Copy your edits before reloading.")
        if tags is not None:
            await self._set_tags(prompt_id, tags)

    async def delete_prompt(self, prompt_id: str) -> None:
        """Delete a prompt and cascade to versions and tags."""
        cursor = await self.db.execute(
            "SELECT id FROM workflow_stages WHERE prompt_id=? LIMIT 1", (prompt_id,)
        )
        if await cursor.fetchone():
            raise ConflictError(
                "This prompt is linked to a workflow. Detach its linked stages before deleting it."
            )
        cursor = await self.db.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
        if not cursor.rowcount:
            raise NotFoundError("Prompt not found.")

    async def toggle_favourite(self, prompt_id: str) -> bool:
        """Toggle favourite status. Returns new state."""
        cursor = await self.db.execute(
            "UPDATE prompts SET is_favourite=1-is_favourite WHERE id=? RETURNING is_favourite",
            (prompt_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise NotFoundError("Prompt not found.")
        return bool(row[0])

    async def list_categories(self) -> list[Record]:
        """List all categories."""
        cursor = await self.db.execute("SELECT * FROM categories ORDER BY sort_order, name")
        return [dict(row) for row in await cursor.fetchall()]

    async def list_tags(self) -> list[Record]:
        """List all tags."""
        cursor = await self.db.execute("SELECT * FROM tags ORDER BY name")
        return [dict(row) for row in await cursor.fetchall()]

    async def _set_tags(self, prompt_id: str, tag_names: list[str]) -> None:
        """Replace all tags on a prompt."""
        await self.db.execute("DELETE FROM prompt_tags WHERE prompt_id = ?", (prompt_id,))
        for name in tag_names:
            name = name.strip()
            if name and (len(name) > 50 or "," in name):
                raise ValueError("Tags must be at most 50 characters and cannot contain commas.")
            if not name:
                continue
            # Get or create tag
            cursor = await self.db.execute("SELECT id FROM tags WHERE name = ?", (name,))
            row = await cursor.fetchone()
            if row:
                tag_id = row["id"]
            else:
                tag_id = str(uuid4())
                await self.db.execute("INSERT INTO tags (id, name) VALUES (?, ?)", (tag_id, name))
            await self.db.execute(
                "INSERT OR IGNORE INTO prompt_tags (prompt_id, tag_id) VALUES (?, ?)",
                (prompt_id, tag_id),
            )
