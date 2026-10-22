"""Shared domain validation for HTTP, MCP and import operations."""

import re
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

import aiosqlite

Record = dict[str, Any]


class NotFoundError(ValueError):
    pass


class ConflictError(ValueError):
    pass


def title_value(value: str, maximum: int = 200) -> str:
    value = value.strip()
    if not value or len(value) > maximum:
        raise ValueError(f"Name must contain between 1 and {maximum} characters.")
    return value


def status_value(value: str | Enum) -> str:
    return str(value.value) if isinstance(value, Enum) else value


async def ensure_status(db: aiosqlite.Connection, value: str | Enum) -> str:
    key = status_value(value)
    cursor = await db.execute("SELECT key FROM status_definitions WHERE key = ?", (key,))
    if await cursor.fetchone() is None:
        raise ValueError("Unknown status. Choose a configured status.")
    return key


def colour_value(value: str) -> str:
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ValueError("Colour must be a six-digit hex colour, such as #6366f1.")
    return value


def next_revision(previous: str) -> str:
    """Monotonic timestamps remain valid edit tokens even within one clock tick."""
    try:
        prior = datetime.fromisoformat(previous).replace(tzinfo=UTC)
    except ValueError:
        prior = datetime.min.replace(tzinfo=UTC)
    return (
        max(datetime.now(UTC), prior + timedelta(microseconds=1)).isoformat().replace("+00:00", "Z")
    )
