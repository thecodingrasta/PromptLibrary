"""Exercise a built standalone executable as a user would, with a temporary data directory.

Usage: python scripts/binary_smoke.py dist-binary/promptlibrary-<version>-<os>-<arch>

The argument may contain ``*``; it is expanded here so Windows shells behave like Unix ones,
and it must match exactly one file.

Needs the ``mcp`` package (installed with the project) for the stdio client. The
executable must be the file under test; this script never imports the application.
"""

import asyncio
import glob
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
STARTUP_SECONDS = 90


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAILED: {message}")
    print(f"ok: {message}")


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def port_open(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def environment(data_dir: Path, port: int) -> dict[str, str]:
    values = dict(os.environ)
    for name in [key for key in values if key.startswith("PROMPTLIB_")]:
        del values[name]
    values.update(
        {
            "PROMPTLIB_DATA_DIR": str(data_dir),
            "PROMPTLIB_HOST": "127.0.0.1",
            "PROMPTLIB_PORT": str(port),
        }
    )
    return values


def run(binary: Path, *arguments: str, env: dict[str, str], cwd: Path) -> tuple[int, str, str]:
    completed = subprocess.run(  # noqa: S603 - the executable under test and fixed arguments.
        [str(binary), *arguments],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=120,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        # A one-file Windows executable is a launcher around the real server process.
        taskkill = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "taskkill.exe"
        subprocess.run(  # noqa: S603 - fixed system executable and a numeric process id.
            [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        process.terminate()
    with suppress(subprocess.TimeoutExpired):
        process.wait(timeout=20)
    if process.poll() is None:
        process.kill()


@contextmanager
def server(binary: Path, env: dict[str, str], cwd: Path, port: int) -> Iterator[str]:
    process = subprocess.Popen(  # noqa: S603 - the executable under test and fixed arguments.
        [str(binary), "serve"],
        env=env,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    origin = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + STARTUP_SECONDS
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise SystemExit(f"FAILED: server exited early with code {process.returncode}")
            with suppress(OSError, urllib.error.URLError, ValueError):
                with urllib.request.urlopen(origin + "/health", timeout=2) as response:  # noqa: S310
                    if json.load(response).get("status") == "ok":
                        yield origin
                        return
            time.sleep(0.5)
        raise SystemExit("FAILED: server did not become healthy.")
    finally:
        stop(process)
        deadline = time.monotonic() + 15
        while port_open(port) and time.monotonic() < deadline:
            time.sleep(0.25)
        check(not port_open(port), f"server shut down and released port {port}")


def fetch(origin: str, path: str) -> tuple[int, str]:
    with urllib.request.urlopen(origin + path, timeout=15) as response:  # noqa: S310
        return int(response.status), response.read().decode("utf-8", "replace")


def text_of(content: object) -> str:
    """Return the text of an MCP text content block, failing the check otherwise."""
    text = getattr(content, "text", None)
    if not isinstance(text, str):
        raise SystemExit("FAILED: MCP result did not contain text.")
    return text


async def mcp_session(binary: Path, env: dict[str, str], cwd: Path) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    parameters = StdioServerParameters(command=str(binary), args=["mcp"], env=env, cwd=str(cwd))
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=60) as client:
            await asyncio.wait_for(client.initialize(), timeout=90)
            names = {tool.name for tool in (await client.list_tools()).tools}
            check({"create_prompt", "get_prompt", "export_library"} <= names, "MCP lists tools")
            created = await client.call_tool("create_prompt", {"title": "Binary", "body": "Works"})
            check(not created.is_error, "MCP creates a prompt")
            identity = json.loads(text_of(created.content[0]))["id"]
            fetched = await client.call_tool("get_prompt", {"id": identity})
            check(
                json.loads(text_of(fetched.content[0]))["body"] == "Works",
                "MCP reads the prompt back",
            )
            rejected = await client.call_tool("create_prompt", {"title": "x", "secret": "hunter2"})
            check(
                bool(rejected.is_error) and "hunter2" not in rejected.model_dump_json(),
                "MCP rejects bad input without echoing it",
            )
            stats = await client.read_resource("library://stats")
            check(bool(stats.contents), "MCP serves a resource")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    matches = sorted(glob.glob(sys.argv[1]))
    if len(matches) != 1:
        raise SystemExit(f"FAILED: expected exactly one file for {sys.argv[1]!r}, found {matches}")
    binary = Path(matches[0]).resolve()
    check(binary.is_file(), f"executable exists: {binary.name}")
    if os.name != "nt":
        check(os.access(binary, os.X_OK), "executable bit is set")
    with tempfile.TemporaryDirectory(prefix="promptlibrary-binary-") as scratch:
        cwd = Path(scratch)
        data_dir = cwd / "data library"
        port = free_port()
        env = environment(data_dir, port)

        code, out, err = run(binary, "--version", env=env, cwd=cwd)
        check(code == 0 and out.strip() == VERSION, f"--version prints {VERSION}")
        code, out, err = run(binary, "--help", env=env, cwd=cwd)
        check(code == 0 and "promptlibrary mcp" in out, "--help lists the subcommands")
        code, out, err = run(binary, "self-check", env=env, cwd=cwd)
        report = json.loads(out) if out.strip() else {}
        check(code == 0 and report.get("ok") is True, "self-check finds every module and file")
        check(report.get("frozen") is True, "self-check reports a frozen executable")
        code, out, err = run(binary, "mcp", "--print-config", env=env, cwd=cwd)
        entry = json.loads(out)["mcpServers"]["promptlibrary"] if code == 0 else {}
        check(
            Path(entry.get("command", "")).resolve() == binary and entry.get("args") == ["mcp"],
            "mcp --print-config points at this executable",
        )
        code, out, err = run(binary, "mcp", "--print-tools", env=env, cwd=cwd)
        check(code == 0 and "create_prompt" in out, "mcp --print-tools lists tools")

        with server(binary, env, cwd, port) as origin:
            for path, marker in (
                ("/", "PromptLibrary"),
                ("/help", "{{TOPIC}}"),
                ("/about", VERSION),
                ("/static/app.css", "{"),
                ("/static/manifest.json", "name"),
            ):
                status, body = fetch(origin, path)
                check(status == 200 and marker in body, f"GET {path} returns expected content")
            status, body = fetch(origin, "/settings")
            check(
                status == 200 and "&#34;mcp&#34;" in body.replace('"mcp"', "&#34;mcp&#34;"),
                "Settings shows the frozen MCP command",
            )
            status, _ = fetch(origin, "/static/app-icon.png")
            check(status == 200, "bundled icon is served")

        code, out, err = run(binary, "maintenance", "doctor", env=env, cwd=cwd)
        check(code == 0 and json.loads(out)["ok"] is True, "maintenance doctor passes")
        asyncio.run(mcp_session(binary, env, cwd))
        code, out, err = run(binary, "maintenance", "doctor", env=env, cwd=cwd)
        check(code == 0 and json.loads(out)["ok"] is True, "database is healthy after MCP writes")
    print(f"All binary checks passed for {binary.name}.")


if __name__ == "__main__":
    main()
