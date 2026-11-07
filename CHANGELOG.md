# Changelog

## 0.1.3

### Standalone downloads

Releases now include a standalone executable for Windows (x64), Linux (x64 and arm64)
and macOS (Apple silicon), so the application runs without installing Python. One `promptlibrary`
program provides the web interface, the Windows tray controller, the MCP stdio server
(`promptlibrary mcp`), database maintenance and a `self-check`. The executables are
built with PyInstaller on native runners and smoke-tested before they are uploaded.
The release gate refuses to draft a release that is missing any of them. They are not
yet code-signed or notarised; the README explains the first-run prompts. Windows on
Arm and Intel Mac users install the wheel with Python or use Docker, because `cryptography`
publishes no patched build for those two targets.

### Documentation

README and MCP usage now include screenshots of the library, prompt editor,
workflow view, built-in guide and MCP settings. The duplicate `COPYING` file was
removed; `LICENSE` is the single licence text.

### Dependencies and CI

Updated FastAPI, pydantic-settings, paramiko (5.1, which fixes the SHA-1 RSA
advisory PYSEC-2026-2858), pip-audit and the MCP SDK (2.x, with the stdio server
ported to constructor-registered handlers). Updated the GitHub Actions
checkout, setup-python, upload-artifact and download-artifact majors. The
dependency audit now covers every installed third-party distribution, including
pip, through `scripts/audit_dependencies.py` instead of failing on the unpublished
local package. The release-asset check now also validates HTML image and link
targets and the documented screenshots.

## 0.1.2

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

Licence metadata aligned to GPL-3.0-or-later, retaining the
original MIT notice. Source installation scripts, community files, configuration
examples and release checks are included. PWA/offline browser, automated inference,
automatic sync and unimplemented integrations are not advertised.

This entry describes the 0.1.2 source changes. Publication and platform validation
are separate release gates; see docs/releasing.md.
