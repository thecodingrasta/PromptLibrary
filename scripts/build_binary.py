"""Build the standalone PromptLibrary executable for the current platform.

PyInstaller cannot cross-compile, so run this on each target operating system and CPU.
The result is written to ``dist-binary/`` as ``promptlibrary-<version>-<os>-<arch>``
(with ``.exe`` on Windows).
"""

import argparse
import platform
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist-binary"
SPEC = ROOT / "packaging" / "promptlibrary.spec"

OPERATING_SYSTEMS = {"win32": "windows", "linux": "linux", "darwin": "macos"}
ARCHITECTURES = {
    "amd64": "x64",
    "x86_64": "x64",
    "arm64": "arm64",
    "aarch64": "arm64",
}


def target_name() -> str:
    """Return the ``<os>-<arch>`` label for this machine, refusing unknown platforms."""
    operating_system = OPERATING_SYSTEMS.get(sys.platform)
    architecture = ARCHITECTURES.get(platform.machine().lower())
    if operating_system is None or architecture is None:
        raise SystemExit(f"Unsupported platform: {sys.platform} / {platform.machine()}")
    return f"{operating_system}-{architecture}"


def project_version() -> str:
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    return str(version)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-name", action="store_true", help="Print the output file name")
    arguments = parser.parse_args()
    suffix = ".exe" if sys.platform == "win32" else ""
    final_name = f"promptlibrary-{project_version()}-{target_name()}{suffix}"
    if arguments.print_name:
        print(final_name)
        return 0
    work = ROOT / "build" / "pyinstaller"
    staging = work / "dist"
    shutil.rmtree(work, ignore_errors=True)
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(staging),
        "--workpath",
        str(work / "work"),
        str(SPEC),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    built = staging / f"promptlibrary{suffix}"
    if not built.is_file():
        raise SystemExit(f"PyInstaller did not produce {built}")
    OUTPUT.mkdir(exist_ok=True)
    destination = OUTPUT / final_name
    shutil.copy2(built, destination)
    destination.chmod(0o755)
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
