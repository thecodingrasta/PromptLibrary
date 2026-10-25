# Security

## Reporting a vulnerability

Use the repository's **Security > Report a vulnerability** option for a private
report. Maintainers must enable private vulnerability reporting before a public
release. If that option is unavailable, use a maintainer's privately listed
contact channel and ask for a secure reporting route. Do not publish exploit
details, access tokens, prompt content or database files in a public issue.

Include the affected version, a minimal reproduction using invented data, impact
and relevant configuration with secrets removed. Reports are assessed by the
maintainers; there is no guaranteed response-time or paid support commitment.
Security fixes target the latest published 1.x release. A development build is not
a security certification.

## Deployment boundary

PromptLibrary is a single-operator application. Every person or MCP client with
access can read and change the whole library, including notes and backup settings.
It has no account roles, per-project access controls or audit-grade activity log.
Use a dedicated OS account and data directory for untrusted or separate clients.
MCP tool annotations describe risk; the client must enforce approvals.

Web mode binds to loopback by default. Non-loopback binding requires a password
of at least 16 characters. Built-in HTTP Basic authentication protects network
requests, but it is not rate-limited and does not provide session revocation or a
logout flow. Add HTTPS, access restrictions and rate limiting at your reverse
proxy. Keep the origin service private. `/health` deliberately reveals only status
and application version without authentication.

Explicit Host checks help prevent DNS rebinding. Cross-origin writes are refused;
non-browser HTTP writers must send `X-PromptLibrary-Client: 1`. The app does not
trust forwarded headers. Set `PROMPTLIB_PUBLIC_ORIGIN` for a TLS reverse proxy.
Responses include a restrictive content security policy. Markdown HTML is escaped,
harmful link schemes are rejected and remote images are not loaded automatically.

## Data and credentials

SQLite content and portable snapshots are not encrypted. Notes are not a separate
permission boundary. Use disk encryption and protect backups accordingly. Never
store provider credentials inside prompts or workflow inputs.

UI-saved remote credentials are encrypted with a local Fernet key in `sync.key`.
The key and database together can decrypt them. POSIX files are created with
restricted modes; on Windows, directory ACLs must protect the account's data.
This is at-rest protection against accidental disclosure, not a defence against
someone who controls the application account. Startup secrets in `.env` remain
plaintext. Back up the key separately when retaining a native database's remote
configuration and never commit either file.

WebDAV requires verified HTTPS except on literal loopback hosts. Redirects are not
followed. SFTP rejects unknown host keys: verify a server's fingerprint through a
trusted channel before adding it to `known_hosts`. Scope remote credentials to a
dedicated folder or bucket prefix. Snapshot transfer can overwrite remote data;
use remote versioning or independent retention where recovery matters.

Portable imports are bounded, parsed without XML entities, validated and applied
transactionally. Treat prompts and imported outputs as untrusted instructions when
passing them to another agent. The application stores and renders text; it does
not make that text safe for autonomous execution.
