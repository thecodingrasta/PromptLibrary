"""Operator-managed remote configuration, kept outside portable library snapshots."""

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import aiosqlite
from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, ConfigDict, Field, model_validator

from promptlibrary.config import Settings
from promptlibrary.services.validation import ConflictError, Record

SECRET_FIELDS = ("webdav_password", "sftp_password", "s3_access_key", "s3_secret_key")


def secure_url(value: str, name: str) -> str:
    parsed = urlsplit(value)
    if parsed.username or parsed.password or parsed.fragment or parsed.query or not parsed.hostname:
        raise ValueError(f"{name} must be a URL without embedded credentials or a fragment.")
    loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
        raise ValueError(f"{name} requires HTTPS. HTTP is supported only on loopback addresses.")
    return value.rstrip("/")


class RemoteConfigInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["none", "local", "webdav", "sftp", "s3"] = "none"
    local_backup_path: str = ""
    webdav_url: str = ""
    webdav_username: str = ""
    webdav_password: str = Field(default="", repr=False)
    sftp_host: str = ""
    sftp_port: int = Field(default=22, ge=1, le=65535)
    sftp_username: str = ""
    sftp_password: str = Field(default="", repr=False)
    sftp_key_path: str = ""
    sftp_known_hosts: str = ""
    sftp_remote_path: str = "/prompts"
    s3_endpoint: str = ""
    s3_bucket: str = ""
    s3_access_key: str = Field(default="", repr=False)
    s3_secret_key: str = Field(default="", repr=False)
    s3_region: str = "us-east-1"


class RemoteConfig(RemoteConfigInput):
    @model_validator(mode="after")
    def validate_provider(self) -> "RemoteConfig":
        if self.provider == "local" and not self.local_backup_path.strip():
            raise ValueError("Choose an absolute backup directory.")
        if self.provider == "local" and not Path(self.local_backup_path).expanduser().is_absolute():
            raise ValueError("The backup directory must be an absolute path on the server.")
        if self.provider == "webdav":
            self.webdav_url = secure_url(self.webdav_url, "WebDAV URL")
        if self.provider == "sftp":
            if not self.sftp_host or any(character in self.sftp_host for character in "/\\\r\n@ "):
                raise ValueError("Enter a valid SFTP hostname or IP address.")
            if not self.sftp_username.strip():
                raise ValueError("SFTP username is required.")
            if not self.sftp_remote_path.startswith("/"):
                raise ValueError("SFTP directory must be an absolute POSIX path.")
        if self.provider == "s3":
            if not self.s3_bucket.strip():
                raise ValueError("S3 bucket is required.")
            if self.s3_endpoint:
                self.s3_endpoint = secure_url(self.s3_endpoint, "S3 endpoint")
            if bool(self.s3_access_key) != bool(self.s3_secret_key):
                raise ValueError(
                    "Provide both S3 credentials, or neither to use the server's IAM credentials."
                )
        return self

    def public_values(self) -> Record:
        values = self.model_dump()
        for name in SECRET_FIELDS:
            values[name + "_stored"] = bool(values[name])
            values[name] = ""
        return values

    def identity(self) -> tuple[str, ...]:
        return (
            self.provider,
            self.webdav_url,
            self.webdav_username,
            self.sftp_host,
            str(self.sftp_port),
            self.sftp_username,
            self.s3_endpoint,
            self.s3_bucket,
        )


class SyncConfigService:
    def __init__(self, db: aiosqlite.Connection, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    @contextmanager
    def operation_lock(self) -> Iterator[None]:
        """OS locks coordinate web and MCP processes and release after a crash."""
        self.settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(self.settings.data_dir / "sync.lock", os.O_RDWR | os.O_CREAT, 0o600)
        locked = False
        try:
            if sys.platform == "win32":
                import msvcrt

                if os.fstat(descriptor).st_size == 0:
                    os.write(descriptor, b"0")
                os.lseek(descriptor, 0, os.SEEK_SET)
                try:
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                except OSError as error:
                    raise ConflictError("Another backup operation is in progress.") from error
            else:
                import fcntl

                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    raise ConflictError("Another backup operation is in progress.") from error
            locked = True
            yield
        finally:
            if locked:
                if sys.platform == "win32":
                    import msvcrt

                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _cipher(self, create: bool = False) -> Fernet:
        path = self.settings.data_dir / "sync.key"
        if create and not path.exists():
            try:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(Fernet.generate_key())
                    stream.flush()
                    os.fsync(stream.fileno())
        if not path.is_file():
            raise ConflictError(
                "The remote configuration key is missing. Restore sync.key or "
                "reconfigure the remote."
            )
        return Fernet(path.read_bytes())

    async def load(self) -> RemoteConfig:
        cursor = await self.db.execute("SELECT config_json FROM sync_configs WHERE id='active'")
        row = await cursor.fetchone()
        if row:
            try:
                plaintext = self._cipher().decrypt(row[0].encode("ascii"))
                return RemoteConfig.model_validate_json(plaintext)
            except (InvalidToken, UnicodeError) as error:
                raise ConflictError(
                    "Remote credentials could not be decrypted. Reconfigure the remote."
                ) from error
        values = {
            name: getattr(self.settings, name)
            for name in RemoteConfig.model_fields
            if name != "provider" and getattr(self.settings, name, None) is not None
        }
        values["provider"] = self.settings.sync_provider or "none"
        return RemoteConfig.model_validate(values)

    async def save(self, values: Record, *, preserve_secrets: bool = True) -> None:
        with self.operation_lock():
            candidate = RemoteConfig.model_validate({**values, **dict.fromkeys(SECRET_FIELDS, "")})
            supplied = dict(values)
            if preserve_secrets:
                try:
                    previous = await self.load()
                except (ConflictError, ValueError):
                    previous = RemoteConfig()
                if previous.identity() == candidate.identity():
                    for name in SECRET_FIELDS:
                        if not supplied.get(name):
                            supplied[name] = getattr(previous, name)
            # Validate the final pair of S3 credentials after preservation as well.
            candidate = RemoteConfig.model_validate(supplied)
            encrypted = self._cipher(create=True).encrypt(
                candidate.model_dump_json().encode("utf-8")
            )
            await self.db.execute(
                """INSERT INTO sync_configs (id,provider,config_json,auto_sync)
                   VALUES ('active',?,?,0)
                   ON CONFLICT(id) DO UPDATE SET provider=excluded.provider,
                   config_json=excluded.config_json,last_synced_at=NULL,auto_sync=0""",
                (candidate.provider, encrypted.decode("ascii")),
            )
            await self.db.commit()

    async def last_synced(self) -> str | None:
        cursor = await self.db.execute("SELECT last_synced_at FROM sync_configs WHERE id='active'")
        row = await cursor.fetchone()
        return str(row[0]) if row and row[0] else None
