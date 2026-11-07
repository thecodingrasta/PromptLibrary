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
environment and run Docker startup/persistence checks. Verify the scripts from a
path containing spaces. Test every advertised remote transport against a disposable
real endpoint, including failed authentication, read/write denial and interrupted
uploads. Mocks cannot certify a provider or its server-specific extensions.

Run a fresh dependency audit in an isolated environment and review the result.
Resolve supported dependencies and retain the resolved versions with the release.
The source dependency ranges are bounded but are not a transitive lockfile.
Do not fabricate a lock or vulnerability result when package access is unavailable.

## Repository and publication

Confirm README, guide, help, About, package metadata, LICENSE and NOTICE agree.
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


## Standalone executables

Each release carries four standalone executables built with PyInstaller from `packaging/promptlibrary.spec`: Windows x64, Linux x64 and arm64, and macOS arm64. They are the files most users download, so they are a release gate rather than an extra.

The `binaries` job in `.github/workflows/ci.yml` builds each one on a native runner, because PyInstaller cannot cross-compile:

| Target | Runner |
| --- | --- |
| `windows-x64` | `windows-latest` |
| `linux-x64` | `ubuntu-22.04` |
| `linux-arm64` | `ubuntu-22.04-arm` |
| `macos-arm64` | `macos-15` |

The Linux builds use the oldest supported Ubuntu so the files run on any distribution with glibc 2.35 or newer. Each job then runs `scripts/binary_smoke.py` against the finished file: `--version`, `--help`, `self-check`, the printed MCP configuration, a real server with page and asset requests, a full MCP stdio session and a clean shutdown. A job that cannot pass this smoke test uploads nothing.

`scripts/release_checksums.py` refuses to write `SHA256SUMS.txt` unless `dist/` holds exactly the wheel, the source archive and every executable for the tagged version, so an incomplete or stale release cannot be drafted.

Known limits to review before publishing:

- **Two targets are deliberately not built.** `windows-arm64` (runner `windows-11-arm`) and `macos-x64` (runner `macos-15-intel`) are missing because `cryptography` has no patched wheel for them. Windows arm64 wheels exist only for 46.0.0 to 46.0.3, and macOS Intel wheels stop at 48.0.1. Both ranges have published advisories, and a source build failed on the arm64 runner. A binary built from those versions would ship known vulnerabilities. Users on those systems install the wheel with Python or use Docker.
- **To restore a target,** wait until `cryptography` 50 or newer publishes a wheel for it, add the matrix entry back in `.github/workflows/ci.yml`, and add the target to `BINARY_TARGETS` in `scripts/release_checksums.py`. A test fails if the two disagree. Every binary job runs `scripts/audit_dependencies.py` on its own bundled dependencies, so an unpatched build cannot pass.
- **Runners are the only proof for Linux arm64 and macOS.** Docker emulation was unavailable here, so those builds were first exercised by their CI jobs. Read those job results, and run the executables on real hardware where you can.
- **Not signed or notarised.** Windows users see SmartScreen and macOS users see Gatekeeper. See the signing sections below. Signing a Windows executable changes its bytes, so regenerate `SHA256SUMS.txt` afterwards.
- **The Windows tray is not exercised by the smoke test.** The smoke test runs `serve`; the notification-area icon needs an interactive desktop. Start the Windows executable by hand and confirm the icon, the notification, **Open** and **Stop** before publishing.

## macOS CI build and release artifact

The authoritative `package` job runs on `macos-latest` and has `needs: native`. This means the macOS native Python matrix must pass before the package is built, smoke-tested and uploaded as the `distributions` artifact. The release workflow calls this CI workflow and downloads that validated artifact when creating its draft release.

For a tag release, verify the draft contains the wheel, source distribution and generated checksum file. Do not replace the downloaded artifact with a locally rebuilt file unless the release is restarted from a newly validated commit.

## Windows Authenticode signing

The repository does not contain a certificate, private key, or signing secret. Signing is an operator-controlled release step. Never commit a `.pfx`, private key, password, or certificate secret.

### One-time certificate preparation

1. Obtain an approved Authenticode code-signing certificate from your organisation or certificate authority. Prefer a hardware-backed or Windows certificate-store key where policy requires it.
2. On the Windows signing machine, confirm the certificate is intended for code signing:

   ```powershell
   Get-ChildItem Cert:\CurrentUser\My | Where-Object {
       $_.EnhancedKeyUsageList.ObjectId -contains '1.3.6.1.5.5.7.3.3'
   } | Format-List Subject,Thumbprint,NotAfter,HasPrivateKey
   ```

3. If CI signing is required, store the certificate as an encrypted repository or environment secret and provide the password through a separate protected secret. Do not write either value to the repository, workflow logs, or command history. A certificate-store/KMS-backed signer is preferred over exporting a PFX.
4. Restrict the certificate's private-key use to the release operator or signing environment and record its expiry/renewal owner outside the repository.

### Sign and verify a Windows release bundle

Run these commands from a clean, reviewed release staging directory. Replace the placeholder certificate thumbprint; do not paste a real secret into documentation or source control.

```powershell
$ErrorActionPreference = 'Stop'
$thumbprint = '<AUTHENTICODE_CERTIFICATE_THUMBPRINT>'
$files = Get-ChildItem -LiteralPath .\windows-release -Recurse -File |
    Where-Object Extension -in '.ps1', '.exe', '.msi', '.dll'

foreach ($file in $files) {
    $result = Set-AuthenticodeSignature -LiteralPath $file.FullName `
        -Certificate (Get-Item "Cert:\CurrentUser\My\$thumbprint") `
        -HashAlgorithm SHA256 `
        -TimestampServer 'http://timestamp.digicert.com'
    if ($result.Status -ne 'Valid') {
        throw "Signing failed for $($file.FullName): $($result.Status)"
    }
}

Get-ChildItem -LiteralPath .\windows-release -Recurse -File |
    Where-Object Extension -in '.ps1', '.exe', '.msi', '.dll' |
    ForEach-Object {
        $signature = Get-AuthenticodeSignature -LiteralPath $_.FullName
        if ($signature.Status -ne 'Valid') {
            throw "Signature verification failed for $($_.FullName): $($signature.Status)"
        }
        [pscustomobject]@{ Path = $_.FullName; Status = $signature.Status; Signer = $signature.SignerCertificate.Subject }
    }
```

For binaries, use the Windows SDK `signtool.exe` when that is the approved organisational signer; use `/fd SHA256`, `/tr <RFC3161 timestamp URL>` and `/td SHA256`, then verify with `signtool verify /pa /all /tw`. The timestamp is required so signatures remain verifiable after the certificate expires.

### What to do after signing

1. Keep the unsigned CI artifact immutable and copy the validated Windows files into a separate staging directory.
2. Sign every distributed Windows script and binary that policy requires; do not sign unrelated source files.
3. Verify every signature on a clean Windows machine, including the certificate chain, timestamp, publisher name and SHA-256 digest. Test launching the signed scripts with the intended PowerShell execution policy.
4. Generate checksums **after** signing. If a signed bundle is archived, checksum the final archive as well as its individual files.
5. Attach the signed Windows bundle and its checksum file to the existing GitHub draft release. Keep the macOS-validated `distributions` artifact unchanged.
6. Record the certificate subject/serial, timestamp authority, signing time, verification result and release commit in the private release record. Never record the private key or password.
7. If any signature or checksum fails, stop. Replace the draft assets with corrected files and repeat verification; do not publish a partially signed release.
8. Only after CI, package smoke, macOS artifact validation, dependency review, signature verification and manual release review are complete should the maintainer publish the draft.

There is no signing secret or certificate configured in the repository by this change. The certificate acquisition, secret provisioning, signing-machine trust and final publication remain explicit approval boundaries.
