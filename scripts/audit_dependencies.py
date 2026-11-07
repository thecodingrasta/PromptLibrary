"""Audit the installed third-party dependency set for known vulnerabilities.

PromptLibrary is not published to PyPI, so ``pip-audit`` cannot resolve the local
distribution and ``--strict`` treats that as a failure (``--skip-editable`` only
covers editable installs, not the wheel install used by CI). This script audits
every other installed distribution (including pip itself), keeps ``--strict`` and never
ignores an advisory.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

LOCAL_DISTRIBUTION = "promptlibrary"


def main() -> int:
    frozen = subprocess.run(
        [sys.executable, "-m", "pip", "freeze", "--all", "--exclude", LOCAL_DISTRIBUTION],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if not frozen.strip():
        print("No third-party distributions were found to audit.", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="promptlibrary-audit-") as directory:
        requirements = Path(directory) / "requirements.txt"
        requirements.write_text(frozen, encoding="utf-8")
        # The freeze already lists every transitive dependency, so resolution is unnecessary.
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip_audit",
                "--strict",
                "--no-deps",
                "--disable-pip",
                "--progress-spinner",
                "off",
                "--requirement",
                str(requirements),
            ],
            check=False,
        )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
