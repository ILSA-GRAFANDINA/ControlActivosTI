[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$Python = "$ProjectRoot\.venv\Scripts\python.exe"
)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $ProjectRoot
if (-not (Test-Path -LiteralPath "$ProjectRoot\.env")) { throw "Falta $ProjectRoot\.env" }
if (-not (Test-Path -LiteralPath $Python)) { throw "No existe el interprete: $Python" }
& $Python -m waitress --listen=127.0.0.1:8000 config.wsgi:application
exit $LASTEXITCODE
