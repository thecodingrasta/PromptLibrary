"""Explicit snapshot transfer, not automatic multi-writer synchronisation."""

import logging
from dataclasses import dataclass

import aiosqlite

from promptlibrary.config import Settings, settings
from promptlibrary.services.export_service import ExportService, ImportMode
from promptlibrary.services.sync_config_service import RemoteConfig, SyncConfigService
from promptlibrary.services.validation import ConflictError
from promptlibrary.sync_providers.base import SyncProvider

logger = logging.getLogger(__name__)
BACKUP_FILENAME = "promptlibrary_backup.json"


@dataclass(frozen=True)
class SyncResult:
    success: bool
    error: str | None = None
    imported: int = 0
    skipped: int = 0
    safety_backup: str | None = None


class SyncService:
    def __init__(self, db: aiosqlite.Connection, configuration: Settings | None = None) -> None:
        self.db = db
        self.configuration = configuration or settings
        self.config_service = SyncConfigService(db, self.configuration)

    def _get_provider(self, config: RemoteConfig) -> SyncProvider:
        if config.provider == "local":
            from promptlibrary.sync_providers.local import LocalSyncProvider

            return LocalSyncProvider(config)
        if config.provider == "webdav":
            from promptlibrary.sync_providers.webdav import WebDAVSyncProvider

            return WebDAVSyncProvider(config)
        if config.provider == "sftp":
            from promptlibrary.sync_providers.sftp import SFTPSyncProvider

            return SFTPSyncProvider(config)
        if config.provider == "s3":
            from promptlibrary.sync_providers.s3 import S3SyncProvider

            return S3SyncProvider(config)
        raise ValueError("No remote configured. Save a remote in Backups first.")

    async def test_connection(self) -> bool:
        with self.config_service.operation_lock():
            config = await self.config_service.load()
            provider = self._get_provider(config)
            await self.db.commit()
            try:
                return await provider.test_connection()
            except Exception as error:
                logger.warning("Remote connection check failed (%s)", type(error).__name__)
                raise ValueError(
                    "Remote connection failed. Check the address, credentials and permissions."
                ) from error

    async def _record_sync(self) -> None:
        await self.db.execute(
            "UPDATE sync_configs SET "
            "last_synced_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id='active'",
        )
        await self.db.commit()

    async def push(self) -> SyncResult:
        with self.config_service.operation_lock():
            config = await self.config_service.load()
            provider = self._get_provider(config)
            snapshot = await ExportService(self.db).export_all()
            # The captured snapshot is consistent; network latency must not hold a DB writer.
            await self.db.commit()
            try:
                await provider.push(
                    snapshot.model_dump_json(indent=2).encode("utf-8"), BACKUP_FILENAME
                )
            except Exception as error:
                # Provider exceptions may contain credentials or signed URLs. Expose only the type.
                logger.warning("Snapshot push failed (%s)", type(error).__name__)
                raise ValueError(
                    "Remote upload failed. Check the connection, permissions and server logs."
                ) from error
            await self._record_sync()
            return SyncResult(success=True)

    async def pull(self, mode: ImportMode = "merge") -> SyncResult:
        with self.config_service.operation_lock():
            config = await self.config_service.load()
            provider = self._get_provider(config)
            await self.db.commit()
            try:
                content = await provider.pull(BACKUP_FILENAME)
            except Exception as error:
                logger.warning("Snapshot pull failed (%s)", type(error).__name__)
                raise ValueError(
                    "Remote download failed. Check the connection and that a snapshot exists."
                ) from error
            try:
                result = await ExportService(self.db).import_json(
                    content.decode("utf-8"), mode=mode
                )
            except ConflictError:
                await self.db.rollback()
                raise
            await self._record_sync()
            return SyncResult(
                True,
                imported=result.imported_count,
                skipped=result.skipped_count,
                safety_backup=result.safety_backup,
            )
