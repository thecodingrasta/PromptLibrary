# PromptLibrary

A self-hosted library for prompts and ordered workflows, with a browser interface
for people and a local MCP server for agents. Your data lives in SQLite on your
machine. No account, cloud subscription or model provider is required.

## What it does

- Organise prompts and workflows together. Search and filter by type, project,
  category, tag, status and favourite. Create custom statuses and typed labels.
- Keep prompt versions, compare changes, restore earlier content or clear history.
- Build workflows from copied or live-linked prompts. Reorder stages without
  silently changing which earlier output a stage references.
- Run workflows step by step: supply inputs, copy the rendered stage to your
  chosen tool, save its output and continue. Runs retain their starting snapshot.
- Export and restore complete content snapshots in JSON or XML. Configure local
  folder, WebDAV, SFTP or S3-compatible backups in the application.
- Use the same services through MCP for prompt management, workflow composition,
  guided runs, metadata and backup operations.

PromptLibrary does **not** call models, run shell commands, schedule agents, merge
concurrent remote edits, or provide multi-user permissions. Stage modes are advice
for your chosen executor, not provider settings. See the [user guide](src/promptlibrary/content/user-guide.md).

## Start from the source

Install Python 3.12 or newer, extract this repository, and open a terminal in its
root folder. Installation downloads Python packages; normal local use does not
need an internet connection. The web server must remain running.

**Windows**

```powershell
py -3 scripts/manage.py setup
py -3 scripts/manage.py run
```

**Linux and macOS**

```sh
python3 scripts/manage.py setup
python3 scripts/manage.py run
```

Open `http://127.0.0.1:8000`. Press Ctrl+C in the terminal to stop the server.
These commands create a local `.venv` without changing your system Python.
`scripts/install.*`, `scripts/start.*` and `scripts/validate.*` are equivalent wrappers.

For direct installation in an existing virtual environment, run `python -m pip
install .`, then `promptlibrary`. The optional `.[desktop]` extra provides
`promptlibrary-tray`; it needs an interactive desktop and a supported system tray.
Browser mode remains available when a desktop has no tray support.

## First use

Choose **New prompt**, enter its title and body, and save. The saved prompt opens
beside the library. Use **Edit** for project, category, status, tags and labels.
**Version history** opens and closes in place. Deleting content and clearing
history require confirmation when JavaScript is enabled.

For a workflow, choose **New workflow**, save its details, then add stages. A stage
can contain its own text, a copy of an existing prompt, or a live link to one.
Write inputs as `{{TOPIC}}` and earlier outputs as `{{stage_1_output}}`. Select
**Start guided run** after supplying inputs and record outputs. PromptLibrary keeps the run;
you or your agent choose where to execute each stage.

## Configuration and data

Copy `.env.example` to `.env` for startup settings, or set `PROMPTLIB_` environment
variables. The application reads `.env` from its working directory. Keep it out of
version control. Remote backup settings can be saved under **Backups** without
editing a file.

Default data directories are `%LOCALAPPDATA%/PromptLibrary` on Windows,
`~/Library/Application Support/PromptLibrary` on macOS, and
`${XDG_DATA_HOME:-~/.local/share}/promptlibrary` on Linux. Set
`PROMPTLIB_DATA_DIR` to choose another directory, and give web and MCP processes
the same value.

The default listener is loopback only. Network listening requires a password,
explicit allowed hosts, and HTTPS at a reverse proxy. Do not expose this service
to untrusted users. See [configuration](docs/configuration.md) and [security](SECURITY.md).

## Agents

From the installed environment, run:

```sh
promptlibrary-mcp --print-config
```

This prints a stdio client configuration using that interpreter and data directory.
Register it with your MCP client. Tool schemas come from the executing handlers;
clients should discover them with `tools/list`. See [MCP usage](docs/mcp.md).

## Backups and upgrades

A JSON or XML snapshot includes prompts, versions, projects, categories, tags,
labels, statuses, workflows, stages, runs, outputs and database preferences. It
excludes credentials, startup configuration and browser preferences.

**Merge** adds new records, skips identical records and refuses conflicting edits
as one transaction. **Replace** restores a complete snapshot, including deletions,
after saving a local safety copy. Remote push replaces one remote snapshot; it is
not automatic, bidirectional sync. Portable snapshots are limited to 25 MiB.

For larger libraries or a native database backup:

```sh
promptlibrary-maintenance doctor
promptlibrary-maintenance backup ./library-backup.db
```

Before upgrading, make a native backup and stop all web and MCP processes. Install
the new version, then start it. Older supported schemas migrate transactionally
with a pre-migration backup. For rollback and recovery, see [operations](docs/operations.md).

## Docker

Set a long `PROMPTLIB_AUTH_PASSWORD` in `.env`, then run:

```sh
docker compose up --build -d
```

The container runs as an unprivileged user and stores data in a named volume.
Its published port is loopback-only. Sign in as `promptlibrary` with your configured
password. `docker compose down` preserves the volume; `down -v` deletes it.

## Development and release checks

```sh
python scripts/manage.py setup --dev --browsers
python scripts/manage.py validate --browsers --security
python scripts/manage.py build
```

Linux browser tests may also need `python -m playwright install --with-deps chromium`
inside the virtual environment. The validation command fails on missing tools or
failed checks; it does not silently skip them. CI defines native Python jobs for
Windows, Linux and macOS, browser tests, an installed-wheel check and a Docker
smoke test. A CI definition is not evidence that those jobs have passed. Release
sign-off requires the [release checks](docs/releasing.md) for the exact commit.

Read [CONTRIBUTING.md](CONTRIBUTING.md) for local development and
[architecture](docs/architecture.md) for the code layout. For help, see
[troubleshooting](docs/troubleshooting.md) and [SUPPORT.md](SUPPORT.md).

## Licence

GNU GPL-3.0-or-later. See [COPYING](COPYING) and [NOTICE](NOTICE). This applies to
the application, not to your prompts, notes or workflow outputs. Earlier MIT
attributions and permissions are retained in NOTICE.
