# Operations and recovery

## Start and stop

Run `promptlibrary` in the installed environment, or use `scripts/manage.py run`.
Keep the terminal open and stop with Ctrl+C. For unattended hosting, supervise the
process with your OS service manager using the installed environment's Python and
an explicit data directory. No system service is silently installed.

The optional tray launcher has Open and Quit actions. It owns its web server and
requests a graceful shutdown on Quit. Tray availability depends on the desktop;
headless installations should use browser mode with a terminal or service manager.

`GET /health` checks the database schema table and returns status plus application
version. It does not perform a full integrity scan or check remote availability.
Use `promptlibrary-maintenance doctor` for SQLite quick-check and foreign keys.

## Content snapshots

JSON/XML snapshots contain every portable content table, including saved workflow
runs and outputs. They are not encrypted and include notes. The 25 MiB cap limits
memory and parsing work. Use native SQLite backups when a library exceeds that cap.

Merge is additive only: identical records are skipped and any conflicting record
rejects the entire import. It does not overwrite edits or propagate deletions.
Replace requires a complete format-2 snapshot and restores its full content state.
A pre-restore JSON copy is written under the data directory's `backups` folder.
Keep copies outside that directory as well. Portable snapshots never restore
startup settings, remote credentials, `sync.key`, or browser preferences.

Remote push overwrites `promptlibrary_backup.json` in the configured destination.
Keep independent backups or remote object versioning. Pull uses the same merge or
replace rules as a local import. There is no background sync, three-way merge or
conflict resolution screen. Resolve a conflict by keeping the local state or
intentionally replacing it from a reviewed complete snapshot.

## Native backup and restore

Run these commands in the installed environment. Paths with spaces need quotes.

```sh
promptlibrary-maintenance doctor
promptlibrary-maintenance backup ./library-backup.db
```

The native backup uses SQLite's backup API, includes the whole database and is
verified before success is reported. Existing destination files are never
overwritten. A live backup is consistent even when WAL mode is active; copying
only the `.db` file by hand while the app runs is not equivalent.

To restore, stop the web server and **all** MCP processes using the library:

```sh
promptlibrary-maintenance restore ./library-backup.db --yes
```

The command validates the backup and makes a native safety copy of the current
database before replacing it through SQLite. Restart the application to migrate
an older schema. Never run an older application against a newer schema. To roll
back an upgrade, restore its pre-upgrade database using the matching old source.
Do not delete WAL or SHM files from a live database.

Native backups include encrypted remote configuration, but not `sync.key` or
`.env`. Preserve those files separately to recover remote credentials on the same
trust boundary. Without the key, reconfigure the remote rather than inventing a
replacement key for an existing encrypted record. Secure the backup directory and
Windows ACLs. Delete old backups deliberately; no automatic retention job removes
your safety copies.

Docker stores the data directory in a named volume. Back it up before changing
images. `docker compose down -v` deletes that volume and is not an upgrade command.
