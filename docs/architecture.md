# Architecture

PromptLibrary is a Python application with a FastAPI HTTP server, Jinja templates,
local CSS/JavaScript, SQLite and an MCP stdio adapter. There is no frontend build
chain or runtime CDN dependency. The HTTP and MCP transports call shared services.

## Boundaries

`app.py`, `config.py` and `security.py` own startup, settings, authentication, host
and origin checks, request limits and response headers. `routers` translate HTTP
forms into service calls and render responses. `services` own library rules,
workflow state, metadata, snapshots and remote configuration. `sync_providers`
implement transport-specific snapshot IO. `mcp/registry.py` derives tool schemas
from annotated handlers; `mcp/server.py` is the 1.x SDK transport adapter. Its small
registration helper contains the untyped third-party decorator-factory boundary;
the handlers and domain services remain checked.

`database.py` owns schema version 3 and transactional migrations. Each request or
tool call gets a connection with foreign keys and a busy timeout. Writers take
`BEGIN IMMEDIATE`; errors roll back. SQLite is a single-writer database, not a
multi-node database server. Keep its live file on a local filesystem rather than
an SMB/NFS share; transfer snapshots between machines instead.

The library query combines prompts and workflows, with deterministic ordering
and pages of 100 items. Status keys remain stable while names, colours and order
are editable. SQLite row dictionaries and versioned snapshot payloads are the
explicit `Record` boundary. SQL values are bound, while generated identifiers come
only from application-owned allowlists.

## Browser state

A fragment response replaces the shared application region, including navigation,
list and selected detail. This avoids independent stale list/detail updates.
Mutations are not aborted to perform navigation. Obsolete read responses are
ignored; unsaved forms prompt before leaving. Direct HTTP links render the same
layout. Theme and sidebar state stay in browser storage, not the portable database.

The UI uses native details elements for history and native dialog elements for
confirmations. With JavaScript disabled, ordinary pages/forms remain available,
but modal confirmations, clipboard and live navigation are unavailable.

## Workflows and runs

A stage contains copied text or a live prompt reference. Deleting a referenced
prompt is refused until its stages are detached or removed. Ordered output
placeholders are updated during reordering, subject to dependency checks. A saved
run copies its resolved workflow definition and variables, so later edits do not
rewrite that run. Compare-and-swap stage completion rejects duplicate submissions.
No model call or execution engine is hidden behind the Run action.

## Portability and security

Format-2 snapshots enumerate portable content tables explicitly. Imports validate
collections, references, ordering and saved-run structure, then merge or replace
transactionally. Credentials and local startup settings stay outside portable
content. Remote operations are serialized across processes with an OS file lock. Cancellation
waits for blocking upload workers before releasing that lock. Network transfers
do not retain a database write transaction.
Local and SFTP uploads use temporary files plus atomic replacement; WebDAV uses a
staged upload and MOVE; S3 uses object replacement. No multi-writer remote conflict
resolution is implied.

Markdown is escaped and rendered with a restricted link policy; imported prompt
text is never evaluated as a template. The single-operator trust model, storage
limitations and network requirements are documented in SECURITY.md.
