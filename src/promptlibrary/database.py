"""SQLite database setup and schema management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, closing

import aiosqlite

from promptlibrary.config import Settings, settings

SCHEMA_VERSION = 3

SCHEMA_SQL = """
-- Core version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

-- Organisation: Categories (hierarchical folders)
CREATE TABLE IF NOT EXISTS categories (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    parent_id TEXT REFERENCES categories(id) ON DELETE SET NULL,
    colour TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Organisation: Projects (group prompts by project/task)
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    colour TEXT,
    icon TEXT,
    is_archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Organisation: Labels (framework/language/context markers)
CREATE TABLE IF NOT EXISTS labels (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    label_type TEXT NOT NULL DEFAULT 'custom' CHECK (label_type IN ('language', 'framework',
    'platform', 'model', 'custom')),
    colour TEXT,
    icon TEXT
);

CREATE TABLE IF NOT EXISTS status_definitions (
    key TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    colour TEXT NOT NULL DEFAULT '#6366f1',
    sort_order INTEGER NOT NULL DEFAULT 0
);

-- Core: Prompts
CREATE TABLE IF NOT EXISTS prompts (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft' REFERENCES status_definitions(key),
    category_id TEXT REFERENCES categories(id) ON DELETE SET NULL,
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    is_favourite INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Core: Version history
CREATE TABLE IF NOT EXISTS prompt_versions (
    id TEXT PRIMARY KEY,
    prompt_id TEXT NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    body TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(prompt_id, version_number)
);

-- Taxonomy: Tags (freeform)
CREATE TABLE IF NOT EXISTS tags (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS prompt_tags (
    prompt_id TEXT NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    tag_id TEXT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (prompt_id, tag_id)
);

-- Taxonomy: Label assignments
CREATE TABLE IF NOT EXISTS prompt_labels (
    prompt_id TEXT NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    label_id TEXT NOT NULL REFERENCES labels(id) ON DELETE CASCADE,
    PRIMARY KEY (prompt_id, label_id)
);

-- Workflows: Multi-stage prompt chains
CREATE TABLE IF NOT EXISTS workflows (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'draft' REFERENCES status_definitions(key),
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    category_id TEXT REFERENCES categories(id) ON DELETE SET NULL,
    is_favourite INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Workflow stages: ordered steps within a workflow
CREATE TABLE IF NOT EXISTS workflow_stages (
    id TEXT PRIMARY KEY,
    prompt_id TEXT REFERENCES prompts(id) ON DELETE SET NULL,
    workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    stage_number INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    instructions TEXT NOT NULL DEFAULT '',
    variables_json TEXT NOT NULL DEFAULT '[]',
    mode TEXT NOT NULL DEFAULT 'standard' CHECK (mode IN ('standard', 'deep_research',
    'high_reasoning', 'extra_high_reasoning')),
    output_type TEXT NOT NULL DEFAULT 'text' CHECK (output_type IN ('text', 'markdown', 'code',
    'json')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(workflow_id, stage_number)
);

CREATE TABLE IF NOT EXISTS workflow_runs (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    snapshot_json TEXT NOT NULL,
    variables_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed', 'cancelled')),
    current_stage INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS workflow_run_steps (
    run_id TEXT NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
    stage_number INTEGER NOT NULL,
    rendered_input TEXT NOT NULL,
    output TEXT NOT NULL,
    completed_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (run_id, stage_number)
);
CREATE INDEX IF NOT EXISTS idx_runs_workflow ON workflow_runs(workflow_id, created_at DESC);

-- Workflow labels
CREATE TABLE IF NOT EXISTS workflow_labels (
    workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    label_id TEXT NOT NULL REFERENCES labels(id) ON DELETE CASCADE,
    PRIMARY KEY (workflow_id, label_id)
);

-- Workflow tags
CREATE TABLE IF NOT EXISTS workflow_tags (
    workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    tag_id TEXT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (workflow_id, tag_id)
);

-- Sync configs
CREATE TABLE IF NOT EXISTS sync_configs (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    config_json TEXT NOT NULL DEFAULT '{}',
    last_synced_at TEXT,
    auto_sync INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- User preferences (key-value store for UI settings)
CREATE TABLE IF NOT EXISTS preferences (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_prompts_status ON prompts(status);
CREATE INDEX IF NOT EXISTS idx_prompts_category ON prompts(category_id);
CREATE INDEX IF NOT EXISTS idx_prompts_project ON prompts(project_id);
CREATE INDEX IF NOT EXISTS idx_prompts_favourite ON prompts(is_favourite);
CREATE INDEX IF NOT EXISTS idx_prompts_updated ON prompts(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_versions_prompt ON prompt_versions(prompt_id, version_number DESC);
CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name);
CREATE INDEX IF NOT EXISTS idx_labels_type ON labels(label_type);
CREATE INDEX IF NOT EXISTS idx_workflows_project ON workflows(project_id);
CREATE INDEX IF NOT EXISTS idx_workflow_stages_order ON workflow_stages(workflow_id, stage_number);
"""

# Pre-seed common labels for languages/frameworks
SEED_LABELS = [
    # Languages
    ("lbl-python", "Python", "language", "#3776ab", "🐍"),
    ("lbl-javascript", "JavaScript", "language", "#f7df1e", "📜"),
    ("lbl-typescript", "TypeScript", "language", "#3178c6", "📘"),
    ("lbl-rust", "Rust", "language", "#dea584", "🦀"),
    ("lbl-go", "Go", "language", "#00add8", "🐹"),
    ("lbl-csharp", "C#", "language", "#239120", "♯"),
    ("lbl-java", "Java", "language", "#ed8b00", "☕"),
    ("lbl-ruby", "Ruby", "language", "#cc342d", "💎"),
    ("lbl-swift", "Swift", "language", "#fa7343", "🐦"),
    ("lbl-kotlin", "Kotlin", "language", "#7f52ff", "🎯"),
    # Frameworks
    ("lbl-react", "React", "framework", "#61dafb", "⚛️"),
    ("lbl-nextjs", "Next.js", "framework", "#000000", "▲"),
    ("lbl-fastapi", "FastAPI", "framework", "#009688", "⚡"),
    ("lbl-django", "Django", "framework", "#092e20", "🎸"),
    ("lbl-flask", "Flask", "framework", "#000000", "🧪"),
    ("lbl-dotnet", ".NET", "framework", "#512bd4", "🔷"),
    ("lbl-vue", "Vue", "framework", "#4fc08d", "🌿"),
    ("lbl-angular", "Angular", "framework", "#dd0031", "🅰️"),
    ("lbl-svelte", "Svelte", "framework", "#ff3e00", "🔥"),
    ("lbl-tailwind", "Tailwind", "framework", "#06b6d4", "🎨"),
    # Platforms
    ("lbl-web", "Web", "platform", "#4285f4", "🌐"),
    ("lbl-mobile", "Mobile", "platform", "#34a853", "📱"),
    ("lbl-desktop", "Desktop", "platform", "#7c3aed", "🖥️"),
    ("lbl-cli", "CLI", "platform", "#22c55e", "⌨️"),
    ("lbl-api", "API", "platform", "#f59e0b", "🔌"),
    # AI Models
    ("lbl-claude", "Claude", "model", "#d97706", "🤖"),
    ("lbl-gpt", "GPT", "model", "#10a37f", "🧠"),
    ("lbl-gemini", "Gemini", "model", "#4285f4", "✨"),
    ("lbl-llama", "Llama", "model", "#7c3aed", "🦙"),
]


@asynccontextmanager
async def get_db(
    configuration: Settings | None = None, *, write: bool = False
) -> AsyncGenerator[aiosqlite.Connection, None]:
    """Connections never commit implicitly. Closing an unsuccessful operation rolls it back."""
    active_settings = configuration or settings
    active_settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = await aiosqlite.connect(str(active_settings.db_path), timeout=15)
    db.row_factory = aiosqlite.Row
    try:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute("PRAGMA busy_timeout=15000")
        if write:
            await db.execute("BEGIN IMMEDIATE")
        yield db
    finally:
        await db.close()


async def init_db(configuration: Settings | None = None) -> None:
    """Migrate atomically, preserving pre-v1 databases and their foreign-key relationships."""
    import asyncio
    import sqlite3
    from datetime import UTC, datetime

    active_settings = configuration or settings
    active_settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    async with get_db(active_settings) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        )
        existing = await cursor.fetchone()
        version = 0
        if existing:
            cursor = await db.execute("SELECT version FROM schema_version LIMIT 1")
            row = await cursor.fetchone()
            version = int(row[0]) if row else 0
        if version > SCHEMA_VERSION:
            raise RuntimeError("This database requires a newer version of PromptLibrary.")
        if 0 < version < SCHEMA_VERSION:
            backup_dir = active_settings.data_dir / "backups"
            backup_dir.mkdir(exist_ok=True, mode=0o700)
            name = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
            backup_path = backup_dir / f"before-schema-{SCHEMA_VERSION}-{name}.db"

            def backup() -> None:
                with closing(sqlite3.connect(active_settings.db_path)) as source:
                    with closing(sqlite3.connect(backup_path)) as target:
                        source.backup(target)
                backup_path.chmod(0o600)

            await asyncio.to_thread(backup)
        # SQLite requires disabling foreign keys before the table-rebuild transaction.
        await db.execute("PRAGMA foreign_keys=OFF")
        await db.execute("BEGIN IMMEDIATE")
        try:
            # Another process may have migrated while this connection waited for the writer lock.
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
            )
            if await cursor.fetchone():
                cursor = await db.execute("SELECT version FROM schema_version LIMIT 1")
                row = await cursor.fetchone()
                version = int(row[0]) if row else 0
            if version > SCHEMA_VERSION:
                raise RuntimeError("This database requires a newer version of PromptLibrary.")
            if version and version < 3:
                cursor = await db.execute("PRAGMA table_info(prompts)")
                columns = {row["name"] for row in await cursor.fetchall()}
                if "project_id" not in columns:
                    await db.execute("ALTER TABLE prompts ADD COLUMN project_id TEXT")
                await db.execute("""CREATE TABLE prompts_v3 (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'draft' REFERENCES status_definitions(key),
                    category_id TEXT REFERENCES categories(id) ON DELETE SET NULL,
                    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
                    is_favourite INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )""")
                await db.execute("""INSERT INTO prompts_v3
                    SELECT id,title,body,notes,status,category_id,project_id,is_favourite,
                           created_at,updated_at FROM prompts""")
                await db.execute("DROP TABLE prompts")
                await db.execute("ALTER TABLE prompts_v3 RENAME TO prompts")
                for table, column, definition in (
                    (
                        "workflows",
                        "status",
                        "TEXT NOT NULL DEFAULT 'draft' REFERENCES status_definitions(key)",
                    ),
                    (
                        "workflow_stages",
                        "prompt_id",
                        "TEXT REFERENCES prompts(id) ON DELETE SET NULL",
                    ),
                ):
                    cursor = await db.execute(f"PRAGMA table_info({table})")
                    columns = {row["name"] for row in await cursor.fetchall()}
                    if columns and column not in columns:
                        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            # executescript commits implicitly, so execute statements separately.
            for statement in SCHEMA_SQL.split(";"):
                if statement.strip():
                    await db.execute(statement)
            for key, name, colour, order in (
                ("draft", "Draft", "#d97706", 0),
                ("staged", "Staged", "#2563eb", 1),
                ("published", "Published", "#16a34a", 2),
            ):
                if version < SCHEMA_VERSION:
                    await db.execute(
                        "INSERT OR IGNORE INTO status_definitions VALUES (?, ?, ?, ?)",
                        (key, name, colour, order),
                    )
            if not version:
                for label_id, name, label_type, colour, icon in SEED_LABELS:
                    await db.execute(
                        "INSERT OR IGNORE INTO labels (id,name,label_type,colour,icon) VALUES "
                        "(?,?,?,?,?)",
                        (label_id, name, label_type, colour, icon),
                    )
            await db.execute("DELETE FROM schema_version")
            await db.execute("INSERT INTO schema_version VALUES (?)", (SCHEMA_VERSION,))
            cursor = await db.execute("PRAGMA foreign_key_check")
            if await cursor.fetchone():
                raise RuntimeError(
                    "Database migration found invalid references; no changes were committed."
                )
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
        finally:
            await db.execute("PRAGMA foreign_keys=ON")
    active_settings.db_path.chmod(0o600)
