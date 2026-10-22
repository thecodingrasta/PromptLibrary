"""SFTP snapshots with known-host verification and closed transport lifetimes."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from paramiko import SSHClient
import io
import posixpath
from pathlib import Path
from uuid import uuid4

from promptlibrary.services.export_service import MAX_SNAPSHOT_BYTES
from promptlibrary.services.sync_config_service import RemoteConfig
from promptlibrary.sync_providers.base import SyncProvider, blocking_operation


class SFTPSyncProvider(SyncProvider):
    def __init__(self, config: RemoteConfig) -> None:
        self.config = config

    def _connect(self) -> "SSHClient":
        import paramiko

        client = paramiko.SSHClient()
        client.load_system_host_keys()
        if self.config.sftp_known_hosts:
            client.load_host_keys(str(Path(self.config.sftp_known_hosts).expanduser()))
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        try:
            client.connect(
                hostname=self.config.sftp_host,
                port=self.config.sftp_port,
                username=self.config.sftp_username,
                password=self.config.sftp_password or None,
                key_filename=str(Path(self.config.sftp_key_path).expanduser())
                if self.config.sftp_key_path
                else None,
                timeout=10,
                auth_timeout=15,
                banner_timeout=15,
                allow_agent=not bool(self.config.sftp_password),
                look_for_keys=not bool(self.config.sftp_password),
            )
        except BaseException:
            client.close()
            raise
        return client

    def _path(self, filename: str) -> str:
        if not filename or posixpath.basename(filename) != filename or "\\" in filename:
            raise ValueError("Backup filename must not contain a path.")
        return posixpath.join(self.config.sftp_remote_path, filename)

    async def push(self, content: bytes, filename: str) -> None:
        if len(content) > MAX_SNAPSHOT_BYTES:
            raise ValueError("The snapshot exceeds the supported 25 MiB limit.")
        target = self._path(filename)
        temporary = target + "." + uuid4().hex + ".tmp"

        def upload() -> None:
            with self._connect() as client:
                with client.open_sftp() as remote:
                    remote.get_channel().settimeout(30)
                    try:
                        remote.putfo(io.BytesIO(content), temporary, confirm=True)
                        remote.chmod(temporary, 0o600)
                        # Fail closed if the server cannot atomically replace an existing snapshot.
                        remote.posix_rename(temporary, target)
                    finally:
                        try:
                            remote.remove(temporary)
                        except FileNotFoundError:
                            pass

        await blocking_operation(upload)

    async def pull(self, filename: str) -> bytes:
        target = self._path(filename)

        def download() -> bytes:
            with self._connect() as client:
                with client.open_sftp() as remote:
                    remote.get_channel().settimeout(30)
                    with remote.open(target, "rb") as stream:
                        content = stream.read(MAX_SNAPSHOT_BYTES + 1)
                    if len(content) > MAX_SNAPSHOT_BYTES:
                        raise ValueError("The remote snapshot exceeds the supported 25 MiB limit.")
                    return bytes(content)

        return await blocking_operation(download)

    async def test_connection(self) -> bool:
        def probe() -> bool:
            with self._connect() as client:
                with client.open_sftp() as remote:
                    remote.get_channel().settimeout(30)
                    remote.stat(self.config.sftp_remote_path)
            return True

        return await blocking_operation(probe)
