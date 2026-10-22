"""Application configuration via environment variables."""

import os
import platform
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings


def _default_data_dir() -> Path:
    """Platform-appropriate default data directory."""
    system = platform.system()
    if system == "Windows":
        base = (
            Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
            / "PromptLibrary"
        )
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "PromptLibrary"
    else:
        # Linux / FreeBSD / Android (via Termux)
        xdg = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
        base = xdg / "promptlibrary"
    return base


class Settings(BaseSettings):
    """PromptLibrary settings. Configure via environment variables prefixed with PROMPTLIB_."""

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    data_dir: Path = Field(default_factory=_default_data_dir)
    db_name: str = "promptlibrary.db"

    public_origin: str | None = None
    auth_username: str = "promptlibrary"
    auth_password: SecretStr | None = None
    allowed_hosts: list[str] = ["127.0.0.1", "localhost", "[::1]"]
    max_request_bytes: int = Field(default=26 * 1024 * 1024, ge=1024, le=128 * 1024 * 1024)

    # Debug mode
    debug: bool = False

    # Sync settings
    sync_provider: str | None = None
    webdav_url: str | None = None
    webdav_username: str | None = None
    webdav_password: str | None = None
    sftp_host: str | None = None
    sftp_port: int = 22
    sftp_username: str | None = None
    sftp_password: str | None = None
    sftp_key_path: str | None = None
    sftp_known_hosts: str | None = None
    sftp_remote_path: str = "/prompts"
    s3_endpoint: str | None = None
    s3_bucket: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str = "us-east-1"
    local_backup_path: str | None = None

    model_config = {
        "env_prefix": "PROMPTLIB_",
        "env_file": ".env",
        "extra": "ignore",
        "hide_input_in_errors": True,
    }

    @model_validator(mode="after")
    def validate_network_settings(self) -> "Settings":
        self.data_dir = self.data_dir.expanduser().absolute()
        if self.auth_password and len(self.auth_password.get_secret_value()) < 16:
            raise ValueError("PROMPTLIB_AUTH_PASSWORD must contain at least 16 characters.")
        if self.host not in {"127.0.0.1", "localhost", "::1"} and not self.auth_password:
            raise ValueError("Non-loopback listening requires PROMPTLIB_AUTH_PASSWORD.")
        if not self.allowed_hosts or "*" in self.allowed_hosts:
            raise ValueError("Set explicit allowed hosts; a wildcard host is not supported.")
        if (
            self.db_name in {"", ".", ".."}
            or any(char in self.db_name for char in "/\\\x00")
            or Path(self.db_name).name != self.db_name
        ):
            raise ValueError("Database name must be a filename, not a path.")
        if self.public_origin:
            origin = urlsplit(self.public_origin)
            if (
                origin.scheme not in {"http", "https"}
                or not origin.hostname
                or origin.username
                or origin.password
                or origin.path not in {"", "/"}
                or origin.query
                or origin.fragment
            ):
                raise ValueError(
                    "PROMPTLIB_PUBLIC_ORIGIN must be an origin, without a path or credentials."
                )
            if origin.scheme != "https" and origin.hostname not in {
                "localhost",
                "127.0.0.1",
                "::1",
            }:
                raise ValueError("A network-facing public origin must use HTTPS.")
            _ = origin.port
            self.public_origin = self.public_origin.rstrip("/")
        if not self.auth_username or ":" in self.auth_username:
            raise ValueError("Authentication username cannot be empty or contain a colon.")
        return self

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_name

    @property
    def platform_info(self) -> dict[str, str]:
        """System information for diagnostics."""
        return {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "data_dir": str(self.data_dir),
        }


settings = Settings()
