"""S3-compatible snapshots with bounded downloads and explicit connection timeouts."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

from promptlibrary.services.export_service import MAX_SNAPSHOT_BYTES
from promptlibrary.services.sync_config_service import RemoteConfig
from promptlibrary.sync_providers.base import SyncProvider, blocking_operation


class S3SyncProvider(SyncProvider):
    def __init__(self, config: RemoteConfig) -> None:
        self.config = config

    def _client(self) -> "S3Client":
        import boto3
        from botocore.config import Config

        return boto3.client(
            "s3",
            endpoint_url=self.config.s3_endpoint or None,
            region_name=self.config.s3_region,
            aws_access_key_id=self.config.s3_access_key or None,
            aws_secret_access_key=self.config.s3_secret_key or None,
            config=Config(connect_timeout=10, read_timeout=30, retries={"max_attempts": 2}),
        )

    async def push(self, content: bytes, filename: str) -> None:
        if len(content) > MAX_SNAPSHOT_BYTES:
            raise ValueError("The snapshot exceeds the supported 25 MiB limit.")

        def upload() -> None:
            client = self._client()
            try:
                client.put_object(
                    Bucket=self.config.s3_bucket,
                    Key=filename,
                    Body=content,
                    ContentType="application/json",
                )
            finally:
                client.close()

        await blocking_operation(upload)

    async def pull(self, filename: str) -> bytes:
        def download() -> bytes:
            client = self._client()
            try:
                response = client.get_object(Bucket=self.config.s3_bucket, Key=filename)
                stream = response["Body"]
                try:
                    content = stream.read(MAX_SNAPSHOT_BYTES + 1)
                finally:
                    stream.close()
                if len(content) > MAX_SNAPSHOT_BYTES:
                    raise ValueError("The remote snapshot exceeds the supported 25 MiB limit.")
                return bytes(content)
            finally:
                client.close()

        return await blocking_operation(download)

    async def test_connection(self) -> bool:
        def probe() -> bool:
            client = self._client()
            try:
                client.head_bucket(Bucket=self.config.s3_bucket)
                return True
            finally:
                client.close()

        return await blocking_operation(probe)
