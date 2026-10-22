"""Refuse mismatched release tags and checksum the tested distributions."""

import hashlib
import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
if os.environ.get("RELEASE_TAG") != "v" + version:
    raise SystemExit("Release tag must match the package version.")
artifacts = sorted((ROOT / "dist").glob("*.whl")) + sorted((ROOT / "dist").glob("*.tar.gz"))
if len(artifacts) != 2:
    raise SystemExit("Expected exactly one wheel and one source distribution.")
(ROOT / "dist/SHA256SUMS.txt").write_text(
    "".join(
        hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n"
        for path in artifacts
    )
)
