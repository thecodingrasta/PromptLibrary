"""A clean native server for browser tests, with no fixed ports or repository data."""

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn
from playwright.sync_api import Page

from promptlibrary.app import create_app
from promptlibrary.config import Settings


@pytest.fixture(scope="session")
def base_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    data: Path = tmp_path_factory.mktemp("browser library")
    configuration = Settings(data_dir=data, host="127.0.0.1", _env_file=None)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    listener.setblocking(False)
    url = f"http://127.0.0.1:{listener.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(create_app(configuration), log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            try:
                if httpx.get(url + "/health", timeout=0.3, trust_env=False).status_code == 200:
                    break
            except httpx.TransportError:
                pass
            if not thread.is_alive():
                raise RuntimeError("Browser test server stopped during startup.")
            time.sleep(0.1)
        else:
            raise RuntimeError("Browser test server did not become healthy.")
        yield url
    finally:
        server.should_exit = True
        thread.join(timeout=20)
        listener.close()
        if thread.is_alive():
            raise RuntimeError("Browser test server did not shut down.")


@pytest.fixture
def app_page(page: Page, base_url: str) -> Page:
    page.goto(base_url)
    return page
