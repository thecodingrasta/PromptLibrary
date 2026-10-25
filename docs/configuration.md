# Configuration

Startup settings use `PROMPTLIB_` environment variables. A `.env` in the working
directory is also read; explicit environment variables take precedence. Restart
the process after changing startup settings. Relative paths are relative to that
working directory, so use absolute paths for service and MCP installations.

| Setting | Default | Purpose |
| --- | --- | --- |
| `PROMPTLIB_HOST` | `127.0.0.1` | Listening address. Network addresses require a password. |
| `PROMPTLIB_PORT` | `8000` | HTTP port. |
| `PROMPTLIB_DATA_DIR` | OS application-data directory | SQLite, local key and safety backups. |
| `PROMPTLIB_DB_NAME` | `promptlibrary.db` | Filename only, not a path. |
| `PROMPTLIB_AUTH_USERNAME` | `promptlibrary` | HTTP Basic username. |
| `PROMPTLIB_AUTH_PASSWORD` | unset | Optional locally; required for network listening. Minimum 16 characters. |
| `PROMPTLIB_ALLOWED_HOSTS` | `["127.0.0.1","localhost","[::1]"]` | JSON array of hostnames without ports. No wildcard. |
| `PROMPTLIB_PUBLIC_ORIGIN` | unset | Exact externally visible HTTPS origin when using a reverse proxy. |
| `PROMPTLIB_MAX_REQUEST_BYTES` | `27262976` | Request-body cap, independent of the 25 MiB snapshot cap. |
| `PROMPTLIB_DEBUG` | `false` | More verbose server logging, not a browser traceback page. |

## Reverse proxy

Use a private interface or loopback binding and an HTTPS proxy. Restrict access at
the firewall and proxy, preserve the request's Host and add that hostname to
`PROMPTLIB_ALLOWED_HOSTS`. Set `PROMPTLIB_PUBLIC_ORIGIN` to the proxy's exact HTTPS
origin. Include its port only when non-standard. Do not use a URL path prefix;
the application is served at the origin root.

Enable a strong application password even if the proxy also authenticates users.
Do not expose an unauthenticated loopback listener through a proxy or tunnel.
The application ignores forwarded headers and has no trusted-header login mode.
A network deployment needs external TLS and rate limiting; it is not multi-tenant.

## Remote backups

Open **Backups**, select a provider and save its fields. A successful connection
check confirms basic reachability, not that a restore has been tested. Start with
a disposable library and perform a push/pull round-trip before relying on it.

Local folder paths are paths on the machine running PromptLibrary, not the browser.
WebDAV needs a pre-existing collection supporting GET, PUT, MOVE, DELETE and
PROPFIND. SFTP needs a writable absolute remote path and a verified host key;
uploads require the OpenSSH POSIX rename extension. S3-compatible storage needs
an existing bucket and permission for the snapshot object. IAM/default credential
resolution is used when S3 keys are left empty.

Blank password fields preserve saved values only when the destination identity
is unchanged. Changing the destination does not carry secrets to a new server.
Choose **None** to disable a saved remote. UI configuration takes precedence over
legacy environment-provider fields. A saved disabled remote also suppresses those
legacy fields until explicitly reconfigured.

Legacy settings remain readable for existing installations: `PROMPTLIB_SYNC_PROVIDER`,
`PROMPTLIB_LOCAL_BACKUP_PATH`, `PROMPTLIB_WEBDAV_URL`, `PROMPTLIB_WEBDAV_USERNAME`,
`PROMPTLIB_WEBDAV_PASSWORD`, `PROMPTLIB_SFTP_HOST`, `PROMPTLIB_SFTP_PORT`,
`PROMPTLIB_SFTP_USERNAME`, `PROMPTLIB_SFTP_PASSWORD`, `PROMPTLIB_SFTP_KEY_PATH`,
`PROMPTLIB_SFTP_KNOWN_HOSTS`, `PROMPTLIB_SFTP_REMOTE_PATH`, `PROMPTLIB_S3_ENDPOINT`,
`PROMPTLIB_S3_BUCKET`, `PROMPTLIB_S3_ACCESS_KEY`, `PROMPTLIB_S3_SECRET_KEY` and
`PROMPTLIB_S3_REGION`. Prefer the UI for new configurations.
