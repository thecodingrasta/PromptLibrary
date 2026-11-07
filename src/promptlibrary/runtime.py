"""Describe how PromptLibrary is running: from source, an installed package or a frozen binary."""

import os
import sys
from pathlib import Path

#: Subcommands understood by the single ``promptlibrary`` executable.
SERVE = "serve"
TRAY = "tray"
MCP = "mcp"
MAINTENANCE = "maintenance"
SELF_CHECK = "self-check"
SUBCOMMANDS: tuple[str, ...] = (SERVE, TRAY, MCP, MAINTENANCE, SELF_CHECK)


def is_frozen() -> bool:
    """Return True when running from a PyInstaller-built standalone executable."""
    return bool(getattr(sys, "frozen", False))


def interpreter(*, windowless: bool = False) -> str:
    """Return the Python interpreter to use for ``-m`` launches from a source install."""
    executable = Path(sys.executable)
    if windowless and os.name == "nt":
        candidate = executable.with_name("pythonw.exe")
        if candidate.exists():
            return str(candidate)
    return str(executable)


def child_command(subcommand: str, module: str, *, windowless: bool = False) -> list[str]:
    """Build the command that re-launches PromptLibrary as ``subcommand``.

    A frozen executable has no ``-m`` switch, so it re-runs itself with the subcommand.
    A source or installed checkout runs the equivalent module under Python.
    """
    if subcommand not in SUBCOMMANDS:
        raise ValueError(f"Unknown PromptLibrary subcommand: {subcommand}")
    if is_frozen():
        return [sys.executable, subcommand]
    return [interpreter(windowless=windowless), "-m", module]


def mcp_client_command() -> tuple[str, list[str]]:
    """Return the command and arguments an MCP client should use to start the stdio server."""
    if is_frozen():
        return os.path.abspath(sys.executable), [MCP]
    return "promptlibrary-mcp", []
