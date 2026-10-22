"""Cross-platform source checkout setup, validation and packaging."""

import argparse
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENT = ROOT / ".venv"
PYTHON = ENVIRONMENT / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(*arguments: str, interpreter: Path = PYTHON) -> None:
    subprocess.run([str(interpreter), *arguments], cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and run PromptLibrary from this checkout")
    subparsers = parser.add_subparsers(dest="command", required=True)
    setup = subparsers.add_parser("setup")
    setup.add_argument("--dev", action="store_true")
    setup.add_argument("--desktop", action="store_true")
    setup.add_argument(
        "--browsers",
        action="store_true",
        help="Install Playwright Chromium and browser test dependencies",
    )
    subparsers.add_parser("run")
    subparsers.add_parser("mcp")
    validation = subparsers.add_parser("validate")
    validation.add_argument("--browsers", action="store_true")
    validation.add_argument("--security", action="store_true")
    subparsers.add_parser("build")
    arguments = parser.parse_args()
    if sys.version_info < (3, 12):  # noqa: UP036 - this entry point also diagnoses older interpreters.
        parser.error("Python 3.12 or newer is required.")
    if arguments.command == "setup":
        if not PYTHON.exists():
            venv.EnvBuilder(with_pip=True).create(ENVIRONMENT)
        extras = [
            name
            for enabled, name in (
                (arguments.dev, "dev"),
                (arguments.desktop, "desktop"),
                (arguments.browsers, "e2e"),
            )
            if enabled
        ]
        target = "." + ("[" + ",".join(extras) + "]" if extras else "")
        run("-m", "pip", "install", "-e", target)
        if arguments.browsers:
            run("-m", "playwright", "install", "chromium")
    elif not PYTHON.exists():
        parser.error("Run setup first. This script uses only the checkout's .venv.")
    elif arguments.command == "run":
        run("-m", "promptlibrary.app")
    elif arguments.command == "mcp":
        run("-m", "promptlibrary.mcp.server")
    elif arguments.command == "build":
        run("-m", "build")
    else:
        run("-m", "ruff", "check", ".")
        run("-m", "ruff", "format", "--check", ".")
        run("-m", "mypy", "src/promptlibrary")
        run("-m", "pytest", "-q", "--ignore=tests/e2e", "--ignore=tests/integration")
        run("-m", "pytest", "-q", "tests/integration/test_mcp_stdio.py")
        if arguments.browsers:
            run("-m", "pytest", "-q", "tests/e2e", "--browser", "chromium")
        if arguments.security:
            run("-m", "pip_audit", "--strict", "--progress-spinner", "off")


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"Command failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
