"""Native SQLite backup and integrity checks, independent of the web server."""

import argparse
import json
import os
import sqlite3
import sys
import time
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from promptlibrary import __version__
from promptlibrary.config import settings
from promptlibrary.database import SCHEMA_VERSION


def inspect_database(path: Path) -> dict[str, str | int | bool]:
    if not path.is_file():
        raise ValueError("Database not found. Start PromptLibrary once to initialise it.")
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        integrity = [row[0] for row in connection.execute("PRAGMA quick_check")]
        references = connection.execute("PRAGMA foreign_key_check").fetchall()
        row = connection.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        if row is None:
            raise ValueError("The file is not an initialised PromptLibrary database.")
        return {
            "ok": integrity == ["ok"] and not references,
            "schema_version": int(row[0]),
            "application_version": __version__,
            "foreign_key_errors": len(references),
            "bytes": path.stat().st_size,
        }


def _copy_database(source: Path, destination: Path) -> None:
    deadline = time.monotonic() + 60

    def progress(status: int, remaining: int, total: int) -> None:
        if time.monotonic() > deadline:
            raise TimeoutError("Database stayed busy. Stop the application and retry.")

    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as reader:
        with closing(sqlite3.connect(destination, timeout=15)) as writer:
            reader.backup(writer, pages=256, progress=progress, sleep=0.1)


def backup_database(source: Path, destination: Path) -> Path:
    source, destination = source.resolve(), destination.expanduser().resolve()
    report = inspect_database(source)
    if not report["ok"]:
        raise ValueError(
            "Database integrity failed. Preserve the original file before repairing it."
        )
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Exclusive creation prevents a typo from overwriting the live library or another backup.
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        _copy_database(source, destination)
        if not inspect_database(destination)["ok"]:
            raise ValueError("Backup verification failed.")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination


def restore_database(source: Path, destination: Path) -> Path | None:
    source, destination = source.expanduser().resolve(), destination.resolve()
    if source == destination:
        raise ValueError("The backup and live database must be different files.")
    report = inspect_database(source)
    if not report["ok"] or not 1 <= int(report["schema_version"]) <= SCHEMA_VERSION:
        raise ValueError("The backup is corrupt or requires a newer PromptLibrary version.")
    safety = None
    if destination.exists():
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        safety = backup_database(
            destination, destination.parent / "backups" / f"before-native-restore-{stamp}.db"
        )
    else:
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
    # SQLite's backup API commits the replacement atomically; replacing a .db file
    # directly would leave any WAL sidecars and open connections pointing at stale data.
    try:
        _copy_database(source, destination)
    except BaseException:
        if safety is None:
            destination.unlink(missing_ok=True)
        raise
    destination.chmod(0o600)
    return safety


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="PromptLibrary database maintenance")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--data-dir", type=Path, default=settings.data_dir)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Check database integrity without changing it")
    backup = commands.add_parser("backup", help="Create a verified native SQLite backup")
    backup.add_argument("destination", type=Path)
    restore = commands.add_parser(
        "restore", help="Restore a native backup; stop web and MCP processes first"
    )
    restore.add_argument("source", type=Path)
    restore.add_argument(
        "--yes", action="store_true", help="Confirm replacement after stopping every process"
    )
    arguments = parser.parse_args(argv)
    database = arguments.data_dir.expanduser() / settings.db_name
    try:
        if arguments.command == "doctor":
            report = inspect_database(database)
            print(json.dumps(report, indent=2))
            if not report["ok"]:
                raise SystemExit(1)
        elif arguments.command == "backup":
            print(backup_database(database, arguments.destination))
        else:
            if not arguments.yes:
                parser.error(
                    "Stop the web server and every MCP process, then pass --yes to confirm "
                    "replacement."
                )
            safety = restore_database(arguments.source, database)
            print("Database restored. Start PromptLibrary to apply any schema migration.")
            if safety:
                print(f"Previous database: {safety}")
    except (OSError, sqlite3.Error, ValueError, TimeoutError) as error:
        print(f"Maintenance failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
