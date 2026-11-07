"""Cover how PromptLibrary re-launches itself and describes its MCP command.

A standalone executable has no ``python -m`` switch, so every self-launch must become a
subcommand of the executable when frozen while source installs keep their module launches.
"""

import json
import sys
from pathlib import Path

import pytest

from promptlibrary import cli, runtime, selfcheck, tray


@pytest.fixture
def frozen(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(Path("C:/apps/promptlibrary.exe")))
    return sys.executable


def test_source_launches_use_python_modules() -> None:
    assert not runtime.is_frozen()
    command = runtime.child_command(runtime.SERVE, "promptlibrary.app")
    assert command[1:] == ["-m", "promptlibrary.app"]
    assert runtime.mcp_client_command() == ("promptlibrary-mcp", [])


def test_frozen_launches_rerun_the_executable(frozen: str) -> None:
    assert runtime.is_frozen()
    assert runtime.child_command(runtime.SERVE, "promptlibrary.app") == [frozen, "serve"]
    assert runtime.child_command(runtime.TRAY, "promptlibrary.tray") == [frozen, "tray"]
    command, arguments = runtime.mcp_client_command()
    assert Path(command).name == "promptlibrary.exe"
    assert arguments == ["mcp"]


def test_unknown_subcommand_is_refused() -> None:
    with pytest.raises(ValueError, match="Unknown PromptLibrary subcommand"):
        runtime.child_command("shell", "promptlibrary.app")


def test_tray_starts_server_through_the_executable_when_frozen(
    frozen: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Process:
        pid = 1

        def poll(self) -> None:
            return None

    calls: list[list[str]] = []
    probes = iter([False, True])
    monkeypatch.setattr(tray, "_probe_server", lambda _url: next(probes))
    monkeypatch.setattr(
        tray.subprocess, "Popen", lambda command, **_kwargs: calls.append(command) or Process()
    )

    tray.ServerController("http://127.0.0.1:8000", 8000).start()

    assert calls == [[frozen, "serve"]]


@pytest.mark.parametrize(
    ("is_windows", "is_frozen", "expected"),
    [(True, True, True), (True, False, False), (False, True, False), (False, False, False)],
)
def test_process_tree_kill_only_for_frozen_windows(
    is_windows: bool, is_frozen: bool, expected: bool
) -> None:
    system = "nt" if is_windows else "posix"
    assert tray._needs_process_tree_kill(system, is_frozen) is expected


def test_frozen_mcp_print_config_names_the_executable(
    frozen: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from promptlibrary.mcp import server

    server.main(["--print-config"])

    entry = json.loads(capsys.readouterr().out)["mcpServers"]["promptlibrary"]
    assert Path(entry["command"]).name == "promptlibrary.exe"
    assert entry["args"] == ["mcp"]


def test_cli_dispatches_subcommands(monkeypatch: pytest.MonkeyPatch) -> None:
    from promptlibrary import app, maintenance
    from promptlibrary.mcp import server

    seen: dict[str, list[str]] = {}
    monkeypatch.setattr(app, "main", lambda argv: seen.setdefault("serve", argv))
    monkeypatch.setattr(server, "main", lambda argv: seen.setdefault("mcp", argv))
    monkeypatch.setattr(maintenance, "main", lambda argv: seen.setdefault("maintenance", argv))

    cli.main(["--version"])
    cli.main(["mcp", "--print-tools"])
    cli.main(["maintenance", "doctor"])

    assert seen == {
        "serve": ["--version"],
        "mcp": ["--print-tools"],
        "maintenance": ["doctor"],
    }


def test_explicit_serve_never_opens_the_tray(monkeypatch: pytest.MonkeyPatch) -> None:
    from promptlibrary import app

    monkeypatch.delenv("PROMPTLIB_SERVER_ROLE", raising=False)
    monkeypatch.setattr(app, "main", lambda argv: None)

    cli.main(["serve"])

    import os

    assert os.environ["PROMPTLIB_SERVER_ROLE"] == "web-server"
    monkeypatch.delenv("PROMPTLIB_SERVER_ROLE")


def test_cli_help_lists_every_subcommand(capsys: pytest.CaptureFixture[str]) -> None:
    cli.main(["--help"])
    output = capsys.readouterr().out
    for name in runtime.SUBCOMMANDS:
        assert name in output


def test_self_check_finds_every_module_and_packaged_file() -> None:
    report = selfcheck.run()
    assert report["failed_imports"] == []
    assert report["missing_files"] == []
    assert report["ok"] is True


def _break_tray_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = selfcheck.importlib.import_module

    def fake_import(name: str, package: str | None = None) -> object:
        if name in selfcheck.WINDOWS_MODULES:
            raise ModuleNotFoundError(f"No module named {name!r}")
        return real_import(name, package)

    monkeypatch.setattr(selfcheck.importlib, "import_module", fake_import)
    monkeypatch.setattr(selfcheck.sys, "platform", "win32")


def test_self_check_tolerates_a_missing_tray_in_a_source_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A plain pip install on Windows has no desktop extra; that must not fail the check."""
    _break_tray_imports(monkeypatch)
    monkeypatch.setattr(runtime, "is_frozen", lambda: False)

    report = selfcheck.run()

    assert report["ok"] is True
    assert report["failed_imports"] == []
    assert len(report["optional_missing"]) == len(selfcheck.WINDOWS_MODULES)  # type: ignore[arg-type]


def test_self_check_requires_the_tray_in_a_frozen_windows_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A standalone executable that lost its tray modules is broken and must fail."""
    _break_tray_imports(monkeypatch)
    monkeypatch.setattr(runtime, "is_frozen", lambda: True)

    report = selfcheck.run()

    assert report["ok"] is False
    assert any(item.startswith("pystray") for item in report["failed_imports"])  # type: ignore[attr-defined]
    assert report["optional_missing"] == []


def test_self_check_reports_a_missing_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(selfcheck, "REQUIRED_FILES", ("static/does-not-exist.css",))
    report = selfcheck.run()
    assert report["ok"] is False
    assert report["missing_files"] == ["static/does-not-exist.css"]
