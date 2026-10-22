"""Install the built wheel into a clean environment and exercise packaged assets."""

import os
import subprocess
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMOKE = r"""
import asyncio
from pathlib import Path
import httpx
from promptlibrary.app import create_app
from promptlibrary.config import Settings
from promptlibrary.database import init_db

async def check():
    settings = Settings(_env_file=None)
    await init_db(settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(settings)),
                                  base_url='http://localhost') as client:
        for path in ['/', '/help', '/about', '/health', '/static/app.css', '/static/app.js',
                     '/static/LICENSE.txt', '/static/NOTICE.txt']:
            response = await client.get(path)
            if response.status_code != 200:
                raise RuntimeError(f'{path}: {response.status_code}')
        assert '{{TOPIC}}' in (await client.get('/help')).text
asyncio.run(check())
"""


def main() -> None:
    wheels = list((ROOT / "dist").glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit("Build exactly one wheel before running this check.")
    with tempfile.TemporaryDirectory(prefix="promptlibrary package ") as directory:
        target = Path(directory)
        environment = target / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        process_environment = dict(os.environ)
        process_environment.pop("PYTHONPATH", None)
        process_environment["PROMPTLIB_DATA_DIR"] = str(target / "library")
        process_environment["PROMPTLIB_HOST"] = "127.0.0.1"
        for arguments in [
            ["-m", "pip", "install", str(wheels[0])],
            ["-m", "promptlibrary.app", "--version"],
            ["-m", "promptlibrary.mcp.server", "--print-tools"],
            ["-c", SMOKE],
        ]:
            subprocess.run(
                [str(python), *arguments], cwd=target, env=process_environment, check=True
            )
    print("Clean wheel installation and packaged asset smoke checks passed.")


if __name__ == "__main__":
    main()
