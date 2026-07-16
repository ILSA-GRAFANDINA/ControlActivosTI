[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ServiceName = "ControlActivosTI",
    [switch]$SkipTests
)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $ProjectRoot
$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath ".env")) { throw "Falta el archivo .env" }
if (-not (Test-Path -LiteralPath $python)) { throw "Falta el entorno virtual .venv" }

& $python -m pip install --requirement requirements.txt
if ($LASTEXITCODE) { throw "Fallo al instalar dependencias" }
& $python manage.py check --deploy
if ($LASTEXITCODE) { throw "Django check fallo" }
if (-not $SkipTests) {
    & $python manage.py test
    if ($LASTEXITCODE) { throw "Las pruebas fallaron" }
}
& $python manage.py showmigrations --plan
if ($LASTEXITCODE) { throw "No se pudo obtener el plan de migraciones" }
if ($PSCmdlet.ShouldProcess("base de datos", "Aplicar migraciones")) {
    & $python manage.py migrate --noinput
    if ($LASTEXITCODE) { throw "Las migraciones fallaron" }
}
if ($PSCmdlet.ShouldProcess("archivos estaticos", "Ejecutar collectstatic")) {
    & $python manage.py collectstatic --noinput
    if ($LASTEXITCODE) { throw "collectstatic fallo" }
}
$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($service -and $PSCmdlet.ShouldProcess($ServiceName, "Reiniciar servicio")) {
    Restart-Service -Name $ServiceName
}
