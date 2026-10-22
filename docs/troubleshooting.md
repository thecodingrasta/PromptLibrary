# Troubleshooting

## Python or installation failure

Run `python --version` or `py -3 --version`. Python 3.12 or newer is required.
Run setup from the extracted repository root. The setup script uses `.venv` and
reports dependency download failures instead of continuing with a partial install.
Network access is needed for initial installation. Linux may need its distribution's
Python venv package. Do not use sudo pip or install into the system interpreter.

## The browser cannot connect

Keep the server terminal open and check its startup error. Open the configured
host and port, normally `http://127.0.0.1:8000`. A port already in use prevents a
second server from starting. Change `PROMPTLIB_PORT` or stop the other process.
A firewall, corporate browser policy or proxy can also block localhost.

## Invalid Host, origin or login

Allowed hosts are a JSON list of hostnames, not URLs. Add the hostname used by the
browser. For an HTTPS proxy, preserve Host and configure `PROMPTLIB_PUBLIC_ORIGIN`.
Use the origin root, not a subdirectory. Non-browser HTTP mutations need
`X-PromptLibrary-Client: 1`; browser JavaScript handles its own requests.

A network listener without a password fails deliberately. The default username
is `promptlibrary`. HTTP Basic credentials may be cached by the browser; there is
no application logout button. Close the browser profile or clear saved credentials
when changing users. Do not share a single-operator deployment between trust groups.

## Changes, history and workflow order

A stale edit returns a conflict without discarding the form. Copy your changes,
reload and apply them to the latest version. Direct links include the library;
filters may still hide an item that does not match them. Clear filters to find it.

History clearing leaves the current prompt untouched and cannot be undone except
from a backup. Live-linked prompts cannot be deleted while stages use them.
Detach or remove those stages first. Reordering cannot introduce forward/self
output references or silently rewrite a shared prompt; detach a referenced stage
when its positional placeholders need to change.

## Remote transfer or import failure

Check the configured path on the server machine, not your browser device. Verify
WebDAV collection support, SFTP host keys and POSIX rename, or S3 bucket credentials.
Unknown SFTP hosts are rejected by design; verify fingerprints before trusting them.
Connection checks do not prove that a complete upload and restore will succeed.

A merge conflict means no records were imported. Review both libraries before
choosing Replace. Replacement requires a complete format-2 snapshot; older partial
exports can only be merged. A 25 MiB limit error needs a native database backup,
not a larger browser upload. Invalid or unsupported snapshots are refused.

## Database or missing credentials

Stop the application and preserve the entire data directory before investigating
corruption. Run `promptlibrary-maintenance doctor` and retain its output without
sharing content. Restore a known-good backup rather than deleting tables.

A missing or mismatched `sync.key` prevents saved credentials from being decrypted.
Restore the matching key or explicitly reconfigure the remote. Do not regenerate
a key and claim that old encrypted secrets were recovered.

## Tests do not run

Install development and browser extras. Missing tools, browser binaries, system
libraries, unavailable Docker or a browser policy block are not passing results.
Run the affected gate in an environment that supports it and keep the exact log.
MCP transport tests require the installed 1.x SDK; the source pins its compatible
major version. Service-level tests alone do not prove stdio interoperability.
