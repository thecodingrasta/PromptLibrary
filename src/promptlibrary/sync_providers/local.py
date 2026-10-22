"""Atomic local snapshots. This directory may also be managed by the user's sync client."""

import os
import tempfile
from pathlib import Path

from promptlibrary.config import settings
from promptlibrary.services.export_service import MAX_SNAPSHOT_BYTES
from promptlibrary.services.sync_config_service import RemoteConfig
from promptlibrary.sync_providers.base import SyncProvider, blocking_operation


class LocalSyncProvider(SyncProvider):
    def __init__(self, config: RemoteConfig | None = None) -> None:
        self.directory = Path(
            config.local_backup_path
            if config
            else settings.local_backup_path or str(settings.data_dir / "backups")
        ).expanduser()

    def _target(self, filename: str) -> Path:
        if (
            not filename
            or Path(filename).name != filename
            or filename in {".", ".."}
            or any(character in filename for character in "/\\\x00")
        ):
            raise ValueError("Backup filename must not contain a path.")
        return self.directory / filename

    async def push(self, content: bytes, filename: str) -> None:
        target = self._target(filename)
        if len(content) > MAX_SNAPSHOT_BYTES:
            raise ValueError("The snapshot exceeds the supported 25 MiB limit.")

        def write() -> None:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor, temporary = tempfile.mkstemp(prefix=".promptlibrary-", dir=self.directory)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)

        await blocking_operation(write)

    async def pull(self, filename: str) -> bytes:
        target = self._target(filename)

        def read() -> bytes:
            with target.open("rb") as stream:
                content = stream.read(MAX_SNAPSHOT_BYTES + 1)
            if len(content) > MAX_SNAPSHOT_BYTES:
                raise ValueError("The remote snapshot exceeds the supported 25 MiB limit.")
            return content

        return await blocking_operation(read)

    async def test_connection(self) -> bool:
        # A probe uses a unique file and cannot overwrite a library snapshot.
        def probe() -> bool:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor, path = tempfile.mkstemp(prefix=".promptlibrary-check-", dir=self.directory)
            os.close(descriptor)
            os.unlink(path)
            return True

        return await blocking_operation(probe)
