$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 "$Root/scripts/manage.py" setup @args
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python "$Root/scripts/manage.py" setup @args
} else {
    throw "Install Python 3.12 or newer, then run this script again."
}
exit $LASTEXITCODE
