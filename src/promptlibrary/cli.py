"""Single command-line entry point used by the standalone executable.

``promptlibrary`` runs the web server (or the Windows tray controller). The
``tray``, ``mcp`` and ``maintenance`` subcommands expose the other tools through
the same file, so a downloaded binary needs no Python installation.
"""

import os
import sys
from typing import Any, cast

from promptlibrary import __version__, runtime

HELP = f"""PromptLibrary {__version__}

Usage: promptlibrary [--version]
       promptlibrary serve
       promptlibrary tray
       promptlibrary mcp [--print-config | --print-tools]
       promptlibrary maintenance {{doctor|backup|restore}} ...
       promptlibrary self-check

With no subcommand PromptLibrary starts the web interface. On Windows that opens the
notification-area controller; on Linux and macOS it serves in the foreground.

  serve        Run the local web server in this process (never opens the tray)
  tray         Run the Windows notification-area controller
  mcp          Run the MCP stdio server for coding agents
  maintenance  Check, back up or restore the SQLite database
  self-check   Verify this installation contains every module and file it needs

Settings come from PROMPTLIB_* environment variables or a .env file in the working
directory. Run a subcommand with --help for its options.
"""


def _attach_parent_console() -> None:
    """Give a windowless Windows build working standard streams when started from a console.

    The Windows executable is built without a console so double-clicking it never opens a
    terminal window. When it is started from PowerShell or cmd, reconnect to that console so
    ``--version`` and ``--help`` print. Pipes from an MCP client are left untouched.
    """
    if os.name != "nt" or not runtime.is_frozen():
        return
    if sys.stdout is not None and sys.stderr is not None and sys.stdin is not None:
        return
    ctypes_api = cast(Any, __import__("ctypes"))
    attach_parent_process = -1
    if not ctypes_api.windll.kernel32.AttachConsole(attach_parent_process):
        return
    if sys.stdout is None:
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)  # noqa: SIM115
    if sys.stdin is None:
        sys.stdin = open("CONIN$", encoding="utf-8")  # noqa: SIM115


def main(argv: list[str] | None = None) -> None:
    arguments = list(sys.argv[1:] if argv is None else argv)
    _attach_parent_console()
    if arguments[:1] in (["-h"], ["--help"]):
        print(HELP)
        return
    explicit = bool(arguments) and arguments[0] in runtime.SUBCOMMANDS
    command, rest = (arguments[0], arguments[1:]) if explicit else (runtime.SERVE, arguments)
    if explicit and command == runtime.SERVE:
        # An explicit "serve" always runs the server in this process, even on Windows.
        os.environ["PROMPTLIB_SERVER_ROLE"] = "web-server"
    if command == runtime.TRAY:
        from promptlibrary import tray

        tray.run()
    elif command == runtime.MCP:
        from promptlibrary.mcp import server

        server.main(rest)
    elif command == runtime.SELF_CHECK:
        from promptlibrary import selfcheck

        selfcheck.main()
    elif command == runtime.MAINTENANCE:
        from promptlibrary import maintenance

        maintenance.main(rest)
    else:
        from promptlibrary import app

        app.main(rest)


if __name__ == "__main__":
    main()
