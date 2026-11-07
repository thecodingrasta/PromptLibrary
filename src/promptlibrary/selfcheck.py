"""Verify that an installation or standalone executable contains everything it needs.

Dynamic imports and package data are the usual casualties of freezing an application, so
this check imports every module PromptLibrary loads lazily and confirms the bundled files
exist. It reads no library data and starts no server.
"""

import importlib
import json
import platform
import sys
from pathlib import Path

from promptlibrary import __version__, runtime

PACKAGE_DIR = Path(__file__).parent

#: Modules imported lazily at runtime and therefore invisible to static analysis.
LAZY_MODULES: tuple[str, ...] = (
    "promptlibrary.app",
    "promptlibrary.maintenance",
    "promptlibrary.mcp.server",
    "promptlibrary.mcp.tools",
    "promptlibrary.sync_providers.sftp",
    "promptlibrary.sync_providers.s3",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "python_multipart",
    "aiosqlite",
    "mistune",
    "pygments.lexers",
    "pygments.formatters.html",
    "paramiko",
    "boto3",
    "botocore.config",
    "cryptography.fernet",
    "defusedxml.ElementTree",
    "mcp.server.stdio",
    "mcp.types",
)
WINDOWS_MODULES: tuple[str, ...] = ("pystray", "PIL.Image", "promptlibrary.tray")

#: Files read relative to the package directory.
REQUIRED_FILES: tuple[str, ...] = (
    "templates/pages/settings.html",
    "static/app.css",
    "static/app.js",
    "static/app-icon.png",
    "static/favicon.ico",
    "static/manifest.json",
    "static/LICENSE.txt",
    "static/NOTICE.txt",
    "content/user-guide.md",
)


def _import_failures(names: tuple[str, ...]) -> list[str]:
    failures: list[str] = []
    for name in names:
        try:
            importlib.import_module(name)
        except Exception as error:  # noqa: BLE001 - report every failure, whatever its type.
            failures.append(f"{name}: {type(error).__name__}: {error}")
    return failures


def run() -> dict[str, object]:
    failed_imports = _import_failures(LAZY_MODULES)
    optional_missing: list[str] = []
    if sys.platform == "win32":
        tray_failures = _import_failures(WINDOWS_MODULES)
        # A frozen executable must bundle the tray. A source install gets it only from the
        # optional desktop extra, so its absence there is reported without failing.
        if runtime.is_frozen():
            failed_imports += tray_failures
        else:
            optional_missing += tray_failures
    missing_files = [name for name in REQUIRED_FILES if not (PACKAGE_DIR / name).is_file()]
    return {
        "ok": not failed_imports and not missing_files,
        "version": __version__,
        "frozen": runtime.is_frozen(),
        "python": platform.python_version(),
        "platform": f"{sys.platform}/{platform.machine()}",
        "failed_imports": failed_imports,
        "optional_missing": optional_missing,
        "missing_files": missing_files,
    }


def main() -> None:
    report = run()
    print(json.dumps(report, indent=2))
    if not report["ok"]:
        raise SystemExit(1)
