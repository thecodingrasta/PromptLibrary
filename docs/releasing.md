# Releasing

A version string is not a sign-off. Validate the exact commit and keep evidence
for each gate before publishing a stable release.

## Required checks

Run formatting, linting, the configured type checker, unit/HTTP/data regression
tests, real MCP stdio tests and browser journeys. The tests must include old-schema
migration, complete JSON/XML round-trips, conflict rollback, linked-stage deletion,
run ordering, duplicate submission, stale edits, host/origin checks and masked
remote credentials. A skipped or blocked check is still unverified.

Run the native Windows, macOS and Linux CI jobs, install the built wheel in a fresh
environment, and run Docker startup/persistence checks. Verify the scripts from a
path containing spaces. Test every advertised remote transport against a disposable
real endpoint, including failed authentication, read/write denial and interrupted
uploads. Mocks cannot certify a provider or its server-specific extensions.

Run a fresh dependency audit in an isolated environment and review the result.
Resolve supported dependencies and retain the resolved versions with the release.
The source dependency ranges are bounded but are not a transitive lockfile.
Do not fabricate a lock or vulnerability result when package access is unavailable.

## Repository and publication

Confirm README, guide, help, About, package metadata, COPYING and NOTICE agree.
Review the final archive for credentials, databases, caches, private screenshots,
internal notes and stale artefacts. Preserve third-party licence notices.

Enable private vulnerability reporting, configure maintainer contact channels and
review branch protection and required status checks in the hosting service.
Repository files cannot enable those settings themselves. Confirm ownership of
all contributed code and artwork before publishing.

Tag the validated commit with its package version. The release workflow reruns CI
for that tag and prepares a **draft** release with distribution files and checksums.
Publishing the draft remains a maintainer decision after reviewing test results,
provider/platform evidence, dependency audit and migration/rollback checks. The
workflow does not publish to PyPI or push container images automatically.

Keep validation reports truthful: include tool versions, commands, pass/fail counts
and unavailable environments. Do not label an untested platform as certified.
