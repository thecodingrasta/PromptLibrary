"""Version control service for prompts."""

import difflib
from uuid import uuid4

import aiosqlite

from promptlibrary.models import PromptStatus
from promptlibrary.services.validation import (
    NotFoundError,
    Record,
    ensure_status,
    next_revision,
    status_value,
)


class VersionService:
    """Handles prompt versioning - history, diffs, and restoration."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def create_version(
        self,
        prompt_id: str,
        body: str,
        notes: str,
        status: str | PromptStatus,
        message: str | None = None,
    ) -> int:
        """Create a new version for a prompt. Returns the new version number."""
        cursor = await self.db.execute(
            """INSERT INTO prompt_versions
               (id, prompt_id, version_number, body, notes, status, message)
               SELECT ?, ?, COALESCE(MAX(version_number), 0)+1, ?, ?, ?, ?
               FROM prompt_versions WHERE prompt_id=? RETURNING version_number""",
            (str(uuid4()), prompt_id, body, notes, status_value(status), message, prompt_id),
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("The database returned no result for an atomic operation.")
        return int(row[0])

    async def clear_history(self, prompt_id: str) -> int:
        cursor = await self.db.execute("SELECT id FROM prompts WHERE id=?", (prompt_id,))
        if await cursor.fetchone() is None:
            raise NotFoundError("Prompt not found.")
        cursor = await self.db.execute(
            "DELETE FROM prompt_versions WHERE prompt_id=?", (prompt_id,)
        )
        return cursor.rowcount

    async def list_versions(self, prompt_id: str) -> list[Record]:
        """List all versions for a prompt, newest first."""
        cursor = await self.db.execute(
            """SELECT id, prompt_id, version_number, status, message, created_at
               FROM prompt_versions
               WHERE prompt_id = ?
               ORDER BY version_number DESC""",
            (prompt_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def get_version(self, prompt_id: str, version_number: int) -> Record | None:
        """Get a specific version."""
        cursor = await self.db.execute(
            "SELECT * FROM prompt_versions WHERE prompt_id = ? AND version_number = ?",
            (prompt_id, version_number),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_diff(self, prompt_id: str, version_number: int) -> list[str]:
        """Get unified diff between a version and its predecessor."""
        current = await self.get_version(prompt_id, version_number)
        if current is None:
            return []

        if version_number <= 1:
            # First version - diff against empty
            previous_body = ""
        else:
            previous = await self.get_version(prompt_id, version_number - 1)
            previous_body = previous["body"] if previous else ""

        diff = difflib.unified_diff(
            previous_body.splitlines(keepends=True),
            current["body"].splitlines(keepends=True),
            fromfile=f"v{version_number - 1}",
            tofile=f"v{version_number}",
            lineterm="",
        )
        return list(diff)

    async def restore_version(self, prompt_id: str, version_number: int) -> None:
        """Restore a prompt to a specific version. Creates a new version with the old content."""
        version = await self.get_version(prompt_id, version_number)
        if version is None:
            raise NotFoundError("Version not found.")
        await ensure_status(self.db, version["status"])

        cursor = await self.db.execute("SELECT updated_at FROM prompts WHERE id=?", (prompt_id,))
        current = await cursor.fetchone()
        if current is None:
            raise NotFoundError("Prompt not found.")

        await self.db.execute(
            """UPDATE prompts
               SET body = ?, notes = ?, status = ?, updated_at = ?
               WHERE id = ?""",
            (
                version["body"],
                version["notes"],
                version["status"],
                next_revision(current[0]),
                prompt_id,
            ),
        )

        # Create a new version recording the restoration
        await self.create_version(
            prompt_id=prompt_id,
            body=version["body"],
            notes=version["notes"],
            status=version["status"],
            message=f"Restored from version {version_number}",
        )
