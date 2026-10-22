"""Check a built image's health, authenticated UI, non-root user and persistent volume."""

import base64
import json
import os
import secrets
import shutil
import subprocess
import time
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4

DOCKER = shutil.which("docker")
if not DOCKER:
    raise SystemExit("Docker is required for this check.")


def docker(*arguments: str) -> str:
    return subprocess.check_output([DOCKER, *arguments], text=True).strip()


def main() -> None:
    name = "promptlibrary-smoke-" + uuid4().hex
    volume = name + "-data"
    password = secrets.token_urlsafe(32)
    os.environ["PROMPTLIB_AUTH_PASSWORD"] = password
    docker("volume", "create", volume)
    try:
        for attempt in range(2):
            docker(
                "run",
                "--detach",
                "--name",
                name,
                "--env",
                "PROMPTLIB_AUTH_PASSWORD",
                "--publish",
                "127.0.0.1::8000",
                "--volume",
                volume + ":/data",
                "promptlibrary:test",
            )
            try:
                port = docker("port", name, "8000/tcp").rsplit(":", 1)[1]
                origin = "http://127.0.0.1:" + port
                for _ in range(120):
                    try:
                        with urlopen(origin + "/health", timeout=1) as response:  # noqa: S310 - fixed loopback HTTP URL.
                            if json.load(response)["status"] == "ok":
                                break
                    except (URLError, OSError):
                        pass
                    time.sleep(0.5)
                else:
                    raise RuntimeError("Container did not become healthy.")
                authentication = base64.b64encode(("promptlibrary:" + password).encode()).decode()
                request = Request(  # noqa: S310 - fixed loopback HTTP URL.
                    origin + "/", headers={"Authorization": "Basic " + authentication}
                )
                with urlopen(request, timeout=5) as response:  # noqa: S310 - fixed loopback HTTP URL.
                    if response.status != 200:
                        raise RuntimeError("Authenticated UI check failed.")
                if docker("exec", name, "id", "-u") == "0":
                    raise RuntimeError("Container unexpectedly runs as root.")
                if attempt == 0:
                    docker(
                        "exec",
                        name,
                        "python",
                        "-c",
                        "from pathlib import Path; "
                        "Path('/data/smoke.txt').write_text('persistent')",
                    )
                elif docker("exec", name, "cat", "/data/smoke.txt") != "persistent":
                    raise RuntimeError("Volume did not survive container recreation.")
            finally:
                docker("rm", "--force", name)
    finally:
        docker("volume", "rm", volume)
    print("Docker startup, authentication, non-root and persistence checks passed.")


if __name__ == "__main__":
    main()
