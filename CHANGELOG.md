# Changelog

## 1.0.0

### Library and workflows

Unified prompt and workflow browsing with project, category, tag, status, type and
favourite filters. Custom statuses and typed label management. Project browsing
and reassignment while editing. Copied and live-linked prompt stages, dependency-
aware ordering, and guided workflow runs with saved inputs, outputs and snapshots.

### Correctness and interface

The list and selected detail refresh together after mutations. New prompts open
in detail; direct links retain the library panel. Accessible sidebar controls,
theme switching, modal confirmations, collapsible history and history clearing.
Local CSS and JavaScript replace runtime CDN dependencies. The guide displays
placeholder syntax literally and distinguishes stored workflows from inference.

### Data and security

Complete version-2 JSON/XML content snapshots, transactional conflict-refusing
merge, explicit replacement with safety copies, and schema-3 migration backups.
Configurable remote backups with encrypted stored secrets and masked fields.
Verified TLS, explicit SFTP host-key checks, safe Markdown rendering, bounded
requests, host/origin checks and optional network authentication. Native SQLite
maintenance commands support larger libraries and recovery.

### Distribution

Version and licence metadata aligned to 1.0.0 and GPL-3.0-or-later, retaining the
original MIT notice. Source installation scripts, community files, configuration
examples and release checks are included. PWA/offline browser, automated inference,
automatic sync and unimplemented integrations are not advertised.

This entry describes the 1.0.0 source changes. Publication and platform validation
are separate release gates; see docs/releasing.md.
