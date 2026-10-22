"""WebDAV snapshots over verified TLS, with bounded reads and no credential redirects."""

from urllib.parse import quote
from uuid import uuid4

import httpx

from promptlibrary.services.export_service import MAX_SNAPSHOT_BYTES
from promptlibrary.services.sync_config_service import RemoteConfig
from promptlibrary.sync_providers.base import SyncProvider


class WebDAVSyncProvider(SyncProvider):
    def __init__(self, config: RemoteConfig) -> None:
        self.config = config

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            auth=(self.config.webdav_username, self.config.webdav_password),
            timeout=httpx.Timeout(30, connect=10),
            follow_redirects=False,
            trust_env=False,
        )

    def _url(self, filename: str = "") -> str:
        return self.config.webdav_url.rstrip("/") + "/" + quote(filename, safe="")

    async def push(self, content: bytes, filename: str) -> None:
        if len(content) > MAX_SNAPSHOT_BYTES:
            raise ValueError("The snapshot exceeds the supported 25 MiB limit.")
        async with self._client() as client:
            temporary = self._url(".promptlibrary-" + uuid4().hex + ".tmp")
            try:
                response = await client.put(
                    temporary, content=content, headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                response = await client.request(
                    "MOVE",
                    temporary,
                    headers={
                        "Destination": self._url(filename),
                        "Overwrite": "T",
                    },
                )
                response.raise_for_status()
            finally:
                # Best-effort cleanup must not hide the upload or MOVE failure.
                try:
                    await client.delete(temporary)
                except httpx.HTTPError:
                    pass

    async def pull(self, filename: str) -> bytes:
        content = bytearray()
        async with self._client() as client:
            async with client.stream("GET", self._url(filename)) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > MAX_SNAPSHOT_BYTES:
                        raise ValueError("The remote snapshot exceeds the supported 25 MiB limit.")
                    content.extend(chunk)
        return bytes(content)

    async def test_connection(self) -> bool:
        async with self._client() as client:
            response = await client.request("PROPFIND", self._url(), headers={"Depth": "0"})
            response.raise_for_status()
        return True
