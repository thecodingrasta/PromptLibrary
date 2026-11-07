"""Refuse mismatched release tags and checksum every tested release file.

The release carries the Python wheel and source distribution plus one standalone
executable for each target in ``BINARY_TARGETS``. Every file must be present before
checksums are written, so an incomplete release can never be drafted.
"""

import hashlib
import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Operating system and CPU pairs that each have a standalone executable.
#: windows-arm64 and macos-x64 are intentionally absent: cryptography publishes no patched
#: wheel for either. Add them back here and in ci.yml together once it does.
BINARY_TARGETS: tuple[str, ...] = (
    "windows-x64",
    "linux-x64",
    "linux-arm64",
    "macos-arm64",
)
CHECKSUM_FILE = "SHA256SUMS.txt"


def expected_files(version: str) -> list[str]:
    """Return every file name a complete release must contain, in publication order."""
    binaries = [
        f"promptlibrary-{version}-{target}{'.exe' if target.startswith('windows') else ''}"
        for target in BINARY_TARGETS
    ]
    return [
        f"promptlibrary-{version}-py3-none-any.whl",
        f"promptlibrary-{version}.tar.gz",
        *binaries,
    ]


def write_checksums(directory: Path, version: str) -> list[str]:
    """Verify the directory holds exactly the expected files, then write ``SHA256SUMS.txt``."""
    expected = expected_files(version)
    present = sorted(path.name for path in directory.iterdir() if path.name != CHECKSUM_FILE)
    missing = [name for name in expected if name not in present]
    unexpected = [name for name in present if name not in expected]
    if missing or unexpected:
        problems = [f"missing: {name}" for name in missing]
        problems += [f"unexpected: {name}" for name in unexpected]
        raise SystemExit("Release files do not match the expected set:\n" + "\n".join(problems))
    lines = [
        hashlib.sha256((directory / name).read_bytes()).hexdigest() + "  " + name + "\n"
        for name in expected
    ]
    (directory / CHECKSUM_FILE).write_text("".join(lines), encoding="utf-8")
    return expected


def main() -> None:
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    if os.environ.get("RELEASE_TAG") != "v" + version:
        raise SystemExit("Release tag must match the package version.")
    for name in write_checksums(ROOT / "dist", version):
        print(name)


if __name__ == "__main__":
    main()
