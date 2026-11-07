# PyInstaller specification for the single-file PromptLibrary executable.
#
# Build with `python scripts/build_binary.py`. PyInstaller cannot cross-compile, so each
# operating system and CPU architecture is built on a matching native runner.
# ruff: noqa
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

from promptlibrary import __version__

ROOT = Path(SPECPATH).parent
PACKAGE = ROOT / "src" / "promptlibrary"
IS_WINDOWS = sys.platform == "win32"
OUTPUT_NAME = os.environ.get("PROMPTLIB_BINARY_NAME", "promptlibrary")

# Resources the application reads relative to its package directory.
datas = [
    (str(PACKAGE / "templates"), "promptlibrary/templates"),
    (str(PACKAGE / "static"), "promptlibrary/static"),
    (str(PACKAGE / "content"), "promptlibrary/content"),
]

# Modules that are imported dynamically and are therefore invisible to static analysis.
hiddenimports = (
    collect_submodules("promptlibrary")
    + collect_submodules("uvicorn")
    + collect_submodules("paramiko")
    + collect_submodules("boto3")
    + collect_submodules("botocore.config")
    + collect_submodules("pygments.lexers")
    + collect_submodules("pygments.formatters")
    + collect_submodules("pygments.styles")
    + collect_submodules("mistune")
    + ["aiosqlite", "python_multipart", "email.mime.text"]
)

# The notification-area controller exists only on Windows.
excludes = ["tkinter", "pytest", "_pytest", "mypy", "ruff", "playwright", "pip_audit"]
if IS_WINDOWS:
    hiddenimports += collect_submodules("pystray") + ["PIL.Image", "PIL.ImageDraw"]
else:
    excludes += ["pystray", "PIL"]

block_cipher = None

analysis = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
archive = PYZ(analysis.pure)

version_resource = None
if IS_WINDOWS:
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    numbers = tuple(int(part) for part in (__version__.split(".") + ["0", "0", "0"])[:3]) + (0,)
    version_resource = VSVersionInfo(
        ffi=FixedFileInfo(filevers=numbers, prodvers=numbers, mask=0x3F, flags=0x0, OS=0x40004),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        "040904B0",
                        [
                            StringStruct("CompanyName", "PromptLibrary"),
                            StringStruct("FileDescription", "PromptLibrary prompt and workflow library"),
                            StringStruct("FileVersion", __version__),
                            StringStruct("InternalName", "promptlibrary"),
                            StringStruct("OriginalFilename", "promptlibrary.exe"),
                            StringStruct("ProductName", "PromptLibrary"),
                            StringStruct("ProductVersion", __version__),
                            StringStruct("LegalCopyright", "GPL-3.0-or-later"),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )

# The Windows build has no console so a double-click never opens a terminal window.
# promptlibrary.cli reattaches to the parent console for --version, --help and the
# maintenance commands when the executable is started from PowerShell or cmd.
executable = EXE(
    archive,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name=OUTPUT_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=not IS_WINDOWS,
    icon=str(PACKAGE / "static" / "favicon.ico") if IS_WINDOWS else None,
    version=version_resource,
    runtime_tmpdir=None,
)
