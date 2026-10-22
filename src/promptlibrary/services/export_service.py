"""Transactional content snapshots with explicit merge and replacement semantics.

Transport credentials are machine-local settings, not portable library content.
"""

import json
import os
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import aiosqlite
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring

from promptlibrary.models import ExportData
from promptlibrary.services.validation import ConflictError, Record, colour_value, title_value

TABLES: dict[str, tuple[str, tuple[str, ...]]] = {
    "status_definitions": ("status_definitions", ("key",)),
    "categories": ("categories", ("id",)),
    "projects": ("projects", ("id",)),
    "labels": ("labels", ("id",)),
    "tags": ("tags", ("id",)),
    "prompts": ("prompts", ("id",)),
    "versions": ("prompt_versions", ("id",)),
    "workflows": ("workflows", ("id",)),
    "workflow_stages": ("workflow_stages", ("id",)),
    "prompt_tags": ("prompt_tags", ("prompt_id", "tag_id")),
    "prompt_labels": ("prompt_labels", ("prompt_id", "label_id")),
    "workflow_tags": ("workflow_tags", ("workflow_id", "tag_id")),
    "workflow_labels": ("workflow_labels", ("workflow_id", "label_id")),
    "workflow_runs": ("workflow_runs", ("id",)),
    "workflow_run_steps": ("workflow_run_steps", ("run_id", "stage_number")),
    "preferences": ("preferences", ("key",)),
}
ImportMode = Literal["merge", "replace"]
MAX_SNAPSHOT_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True)
class ImportResult:
    imported_count: int
    skipped_count: int
    replaced: bool = False
    safety_backup: str | None = None


class ExportService:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def export_all(self) -> ExportData:
        payload: Record = {"version": "2.0", "schema_version": 3, "exported_at": datetime.now(UTC)}
        await self.db.execute("SAVEPOINT content_export")
        try:
            for section, (table, keys) in TABLES.items():
                cursor = await self.db.execute(f"SELECT * FROM {table} ORDER BY {', '.join(keys)}")  # noqa: S608 - identifiers are selected from a closed schema allowlist.
                payload[section] = [dict(row) for row in await cursor.fetchall()]
            return ExportData.model_validate(payload)
        finally:
            await self.db.execute("RELEASE content_export")

    async def export_xml(self) -> str:
        data = (await self.export_all()).model_dump(mode="json")
        root = ET.Element("promptlibrary")
        for key in ("version", "schema_version", "exported_at"):
            ET.SubElement(root, key).text = str(data[key])
        for section in TABLES:
            container = ET.SubElement(root, section)
            for row in data[section]:
                item = ET.SubElement(container, "item")
                for key, value in row.items():
                    cell = ET.SubElement(item, key)
                    if value is None:
                        cell.set("null", "true")
                    else:
                        cell.text = str(value)
        ET.indent(root)
        return ET.tostring(root, encoding="unicode", xml_declaration=True)

    @staticmethod
    def _unique_fields(pairs: list[tuple[str, object]]) -> Record:
        result: Record = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON object field.")
            result[key] = value
        return result

    async def import_json(self, content: str, mode: ImportMode = "merge") -> ImportResult:
        self._check_size(content)
        try:
            data = json.loads(content, object_pairs_hook=self._unique_fields)
        except (ValueError, RecursionError) as exc:
            raise ValueError("The file is not valid JSON.") from exc
        return await self._import_data(data, mode)

    async def import_xml(self, content: str, mode: ImportMode = "merge") -> ImportResult:
        self._check_size(content)
        try:
            root = fromstring(content, forbid_dtd=True, forbid_entities=True, forbid_external=True)
            if root.tag != "promptlibrary":
                raise ValueError("Expected a promptlibrary root element.")
            data: Record = {}
            for node in root:
                if node.tag in {"version", "schema_version", "exported_at"}:
                    data[node.tag] = node.text
                elif node.tag in TABLES:
                    children = list(node)
                    if not children:
                        data.setdefault(node.tag, [])
                        continue
                    rows = children if children[0].tag == "item" else [node]
                    for item in rows:
                        row: Record = {}
                        for cell in item:
                            if cell.tag in row or (len(cell) and cell.tag != "tags"):
                                raise ValueError("Duplicate or nested XML record field.")
                            if cell.tag == "tags":
                                if len(cell):
                                    embedded = list(cell) if cell[0].tag == "item" else [cell]
                                    row.setdefault("tags", []).extend(
                                        {part.tag: part.text for part in tag} for tag in embedded
                                    )
                            else:
                                row[cell.tag] = (
                                    None if cell.get("null") == "true" else (cell.text or "")
                                )
                        data.setdefault(node.tag, []).append(row)
                else:
                    raise ValueError("Unknown snapshot section.")
        except (ET.ParseError, ValueError, DefusedXmlException) as exc:
            raise ValueError("The file is not a valid PromptLibrary XML snapshot.") from exc
        return await self._import_data(data, mode, xml=True)

    @staticmethod
    def _check_size(content: str) -> None:
        if len(content.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
            raise ValueError("Snapshot exceeds the 25 MiB limit.")

    async def _normalise(self, data: Record, *, xml: bool) -> dict[str, list[Record]]:
        result: dict[str, list[Record]] = {}
        legacy = str(data.get("version", "1.0")) == "1.0"
        for section, (table, keys) in TABLES.items():
            rows = data.get(section, []) or []
            if isinstance(rows, dict):
                rows = rows.get("item", rows)
                if isinstance(rows, dict):
                    rows = [rows]
            if not isinstance(rows, list) or len(rows) > 100_000:
                raise ValueError(f"Invalid collection: {section}.")
            cursor = await self.db.execute(f"PRAGMA table_info({table})")
            columns = {column["name"]: dict(column) for column in await cursor.fetchall()}
            normalised: list[Record] = []
            seen: set[tuple[str, ...]] = set()
            for original in rows:
                if not isinstance(original, dict):
                    raise ValueError(f"Invalid record in {section}.")
                row = dict(original)
                if legacy and section == "prompts":
                    row.pop("tags", None)
                if set(row) - columns.keys():
                    raise ValueError(f"Unknown fields in {section}.")
                for key in keys:
                    if key not in row or row[key] in (None, ""):
                        raise ValueError(f"Missing record key in {section}.")
                identity = tuple(str(row[key]) for key in keys)
                if identity in seen:
                    raise ValueError(f"Duplicate record key in {section}.")
                seen.add(identity)
                for key, column in columns.items():
                    if key not in row:
                        if column["notnull"] and column["dflt_value"] is None:
                            raise ValueError(f"Missing {section}.{key}.")
                        continue
                    value = row[key]
                    if xml:
                        if key.endswith("_id") or key in {"parent_id", "colour", "icon", "message"}:
                            value = value or None
                        if column["type"] == "INTEGER" and value is not None:
                            try:
                                value = int(value)
                            except (ValueError, TypeError) as exc:
                                raise ValueError(f"Invalid integer in {section}.{key}.") from exc
                    if value is not None and not isinstance(value, (str, int, float)):
                        raise ValueError(f"Invalid value in {section}.{key}.")
                    if column["notnull"] and value is None:
                        raise ValueError(f"Null value in {section}.{key}.")
                    if column["type"] == "INTEGER" and value is not None and type(value) is not int:
                        raise ValueError(f"Expected integer in {section}.{key}.")
                    if (
                        column["type"] == "TEXT"
                        and value is not None
                        and not isinstance(value, str)
                    ):
                        raise ValueError(f"Expected text in {section}.{key}.")
                    row[key] = value
                    if key == "colour" and value:
                        if not isinstance(value, str):
                            raise ValueError(f"Expected text in {section}.{key}.")
                        colour_value(value)
                    if key in {"title", "name"}:
                        title_value(value)
                    if key.endswith("_json"):
                        try:
                            decoded = json.loads(value)
                        except (TypeError, ValueError, RecursionError) as exc:
                            raise ValueError(f"Invalid JSON field: {section}.{key}.") from exc
                        expected = (
                            list
                            if key == "variables_json" and section == "workflow_stages"
                            else dict
                        )
                        if not isinstance(decoded, expected):
                            raise ValueError(f"Invalid JSON shape: {section}.{key}.")
                for key in ("is_favourite", "is_archived"):
                    if key in row and row[key] not in (0, 1):
                        raise ValueError(f"Invalid boolean in {section}.{key}.")
                normalised.append(row)
            result[section] = normalised
        if legacy:
            existing = {(row["prompt_id"], row["tag_id"]) for row in result["prompt_tags"]}
            legacy_prompts = data.get("prompts", []) or []
            if isinstance(legacy_prompts, dict):
                legacy_prompts = legacy_prompts.get("item", legacy_prompts)
                if isinstance(legacy_prompts, dict):
                    legacy_prompts = [legacy_prompts]
            for prompt in legacy_prompts:
                tags = prompt.get("tags", []) or []
                if isinstance(tags, dict):
                    tags = [tags]
                for tag in tags:
                    if not isinstance(tag, dict) or not isinstance(tag.get("id"), str):
                        raise ValueError("Each legacy prompt tag must have a valid ID.")
                    pair = (prompt["id"], tag["id"])
                    if pair not in existing:
                        result["prompt_tags"].append({"prompt_id": pair[0], "tag_id": pair[1]})
                        existing.add(pair)
        return result

    async def _safety_backup(self) -> str:
        snapshot = await self.export_all()
        content = snapshot.model_dump_json(indent=2)
        if len(content.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
            raise ValueError(
                "The current library exceeds 25 MiB. Use native maintenance backup/restore instead."
            )
        cursor = await self.db.execute("PRAGMA database_list")
        row = await cursor.fetchone()
        if row is None or not row[2]:
            raise ValueError("Replacement requires a file-backed database for its safety backup.")
        directory = Path(row[2]).parent / "backups"
        directory.mkdir(exist_ok=True, mode=0o700)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        destination = directory / f"before-restore-{stamp}.json"
        descriptor, temporary = tempfile.mkstemp(dir=directory, prefix=".snapshot-")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return destination.name

    async def _import_data(
        self, data: Record, mode: ImportMode = "merge", *, xml: bool = False
    ) -> ImportResult:
        if not isinstance(data, dict) or str(data.get("version", "1.0")) not in {"1.0", "2.0"}:
            raise ValueError("Unsupported snapshot version.")
        if mode not in {"merge", "replace"}:
            raise ValueError("Choose merge or replace.")
        unknown = set(data) - TABLES.keys() - {"version", "schema_version", "exported_at"}
        if unknown:
            raise ValueError("Unknown snapshot sections: " + ", ".join(sorted(unknown)))
        if mode == "replace" and (str(data.get("version")) != "2.0" or set(TABLES) - data.keys()):
            raise ValueError("Replacement requires a complete version 2.0 snapshot.")
        if data.get("schema_version") is not None and str(data["schema_version"]) != "3":
            raise ValueError("Unsupported database schema in snapshot.")
        rows_by_section = await self._normalise(data, xml=xml)
        if mode == "replace":
            status_keys = {row["key"] for row in rows_by_section["status_definitions"]}
            if not {"draft", "staged", "published"} <= status_keys:
                raise ValueError("The snapshot is missing its default statuses.")
        imported = skipped = 0
        safety_backup = None
        if not self.db.in_transaction:
            await self.db.execute("BEGIN IMMEDIATE")
        await self.db.execute("SAVEPOINT content_import")
        await self.db.execute("PRAGMA defer_foreign_keys=ON")
        try:
            if mode == "replace":
                safety_backup = await self._safety_backup()
                for table, _ in reversed(list(TABLES.values())):
                    await self.db.execute(f"DELETE FROM {table}")  # noqa: S608 - identifiers are selected from a closed schema allowlist.
            for section, (table, keys) in TABLES.items():
                for row in rows_by_section[section]:
                    where = " AND ".join(f"{key}=?" for key in keys)
                    cursor = await self.db.execute(
                        f"SELECT * FROM {table} WHERE {where}",  # noqa: S608 - identifiers are selected from a closed schema allowlist.
                        [row[key] for key in keys],
                    )
                    existing = await cursor.fetchone()
                    if existing is not None:
                        if all(existing[key] == value for key, value in row.items()):
                            skipped += 1
                            continue
                        identity = "/".join(str(row[key]) for key in keys)
                        raise ConflictError(
                            f"Conflicting {section} record {identity}. No changes were imported. "
                            "Keep your local library or restore the complete snapshot explicitly."
                        )
                    columns = list(row)
                    placeholders = ", ".join("?" for _ in columns)
                    await self.db.execute(
                        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",  # noqa: S608 - identifiers are selected from a closed schema allowlist.
                        [row[key] for key in columns],
                    )
                    imported += 1
            cursor = await self.db.execute("PRAGMA foreign_key_check")
            if await cursor.fetchone():
                raise ValueError("The snapshot contains missing or invalid references.")
            await self._validate_structure()
            await self.db.execute("RELEASE content_import")
        except BaseException:
            await self.db.execute("ROLLBACK TO content_import")
            await self.db.execute("RELEASE content_import")
            raise
        finally:
            await self.db.execute("PRAGMA defer_foreign_keys=OFF")
        return ImportResult(imported, skipped, mode == "replace", safety_backup)

    async def _validate_structure(self) -> None:
        cursor = await self.db.execute(
            """SELECT workflow_id FROM workflow_stages GROUP BY workflow_id
               HAVING MIN(stage_number) != 1 OR MAX(stage_number) != COUNT(*)"""
        )
        if await cursor.fetchone():
            raise ValueError("Workflow stages must form a contiguous order starting at 1.")
        cursor = await self.db.execute("SELECT * FROM workflow_runs")
        for run in await cursor.fetchall():
            snapshot = json.loads(run["snapshot_json"])
            stages = snapshot.get("stages")
            if not isinstance(stages, list) or not stages:
                raise ValueError("Invalid workflow run snapshot.")
            for index, stage in enumerate(stages, 1):
                if (
                    not isinstance(stage, dict)
                    or stage.get("stage_number") != index
                    or not isinstance(stage.get("body"), str)
                    or not isinstance(stage.get("instructions"), str)
                ):
                    raise ValueError("Invalid workflow run stage snapshot.")
            position = run["current_stage"]
            if not 1 <= position <= len(stages) + 1:
                raise ValueError("Invalid workflow run position.")
            if (run["status"] == "completed") != (position == len(stages) + 1):
                raise ValueError("Workflow run status and position disagree.")
            step_cursor = await self.db.execute(
                "SELECT stage_number FROM workflow_run_steps WHERE run_id=? ORDER BY stage_number",
                (run["id"],),
            )
            if [row[0] for row in await step_cursor.fetchall()] != list(range(1, position)):
                raise ValueError("Workflow run history is incomplete.")
