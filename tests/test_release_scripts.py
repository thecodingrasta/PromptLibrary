"""Cover the release gate that refuses an incomplete or mismatched set of release files."""

import hashlib
import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name: str) -> ModuleType:
    specification = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


checksums = load("release_checksums")


def populate(directory: Path, version: str = "0.1.3") -> None:
    for name in checksums.expected_files(version):
        (directory / name).write_bytes(name.encode())


def test_expected_files_cover_both_python_packages_and_every_shipped_binary() -> None:
    names = checksums.expected_files("0.1.3")
    assert names[:2] == ["promptlibrary-0.1.3-py3-none-any.whl", "promptlibrary-0.1.3.tar.gz"]
    assert names[2:] == [
        "promptlibrary-0.1.3-windows-x64.exe",
        "promptlibrary-0.1.3-linux-x64",
        "promptlibrary-0.1.3-linux-arm64",
        "promptlibrary-0.1.3-macos-arm64",
    ]


def test_checksums_cover_every_file_in_publication_order(tmp_path: Path) -> None:
    populate(tmp_path)

    checksums.write_checksums(tmp_path, "0.1.3")

    lines = (tmp_path / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
    assert [line.split("  ")[1] for line in lines] == checksums.expected_files("0.1.3")
    name = "promptlibrary-0.1.3-linux-x64"
    assert f"{hashlib.sha256(name.encode()).hexdigest()}  {name}" in lines


def test_a_missing_binary_blocks_the_release(tmp_path: Path) -> None:
    populate(tmp_path)
    (tmp_path / "promptlibrary-0.1.3-macos-arm64").unlink()

    with pytest.raises(SystemExit, match="missing: promptlibrary-0.1.3-macos-arm64"):
        checksums.write_checksums(tmp_path, "0.1.3")

    assert not (tmp_path / "SHA256SUMS.txt").exists()


def test_a_stale_file_from_another_version_blocks_the_release(tmp_path: Path) -> None:
    populate(tmp_path)
    (tmp_path / "promptlibrary-0.1.2-linux-x64").write_bytes(b"old")

    with pytest.raises(SystemExit, match="unexpected: promptlibrary-0.1.2-linux-x64"):
        checksums.write_checksums(tmp_path, "0.1.3")


def test_checksum_file_is_rewritten_not_treated_as_unexpected(tmp_path: Path) -> None:
    populate(tmp_path)
    checksums.write_checksums(tmp_path, "0.1.3")

    checksums.write_checksums(tmp_path, "0.1.3")

    assert (tmp_path / "SHA256SUMS.txt").is_file()


def test_tag_that_differs_from_the_package_version_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RELEASE_TAG", "v9.9.9")
    with pytest.raises(SystemExit, match="must match the package version"):
        checksums.main()


def test_ci_builds_exactly_the_binaries_the_release_gate_requires() -> None:
    """The workflow matrix and the release gate must not drift apart."""
    workflow = (SCRIPTS.parent / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    built = set(re.findall(r"^ +- target: (\S+)", workflow, flags=re.MULTILINE))
    assert built == set(checksums.BINARY_TARGETS)


def test_every_binary_job_installs_the_tools_its_steps_run() -> None:
    """A step can only use a tool that the job's install step provides."""
    workflow = (SCRIPTS.parent / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    binaries = workflow.split("  binaries:", 1)[1].split("\n  docker:", 1)[0]
    assert "python scripts/audit_dependencies.py" in binaries
    assert "python scripts/build_binary.py" in binaries
    extras = re.findall(r"^ +extras: (\S+)", binaries, flags=re.MULTILINE)
    assert extras, "the binaries job declares no extras"
    for entry in extras:
        provided = set(entry.split(","))
        # build_binary.py needs PyInstaller; audit_dependencies.py needs pip-audit.
        assert {"binary", "audit"} <= provided, entry
