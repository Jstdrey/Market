param(
    [string]$OutputDir = "deploy/artifacts",
    [switch]$IncludeOutput,
    [switch]$IncludeDataCache
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
$outputPath = Join-Path $projectRoot $OutputDir
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$archivePath = Join-Path $outputPath "market_release_$timestamp.tar.gz"

$tarArgs = @(
    "-czf", $archivePath,
    "--exclude=.git",
    "--exclude=.venv",
    "--exclude=.playwright-cli",
    "--exclude=.streamlit_app.pid",
    "--exclude=.streamlit_app_*.pid",
    "--exclude=.tmp*",
    "--exclude=*.log",
    "--exclude=__pycache__",
    "--exclude=*.pyc",
    "--exclude=*.py[cod]",
    "--exclude=deploy/runtime",
    "--exclude=deploy/artifacts",
    "--exclude=data.csv",
    "--exclude=trades_log.csv",
    "--exclude=strategy_profiles.json",
    "--exclude=Данные и Бекстест",
    "--exclude=*.csv.gz",
    "--exclude=*.parquet",
    "--exclude=*.feather",
    "--exclude=*.h5",
    "--exclude=*.hdf5",
    "--exclude=*.sqlite",
    "--exclude=*.db",
    "--exclude=*.pkl",
    "--exclude=*.pickle"
)

if (-not $IncludeOutput) {
    $tarArgs += "--exclude=output"
}

if (-not $IncludeDataCache) {
    $tarArgs += "--exclude=data/cache"
}

$tarArgs += "."

Push-Location $projectRoot
try {
    & tar @tarArgs
    if ($LASTEXITCODE -ne 0) {
        throw "tar failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

Write-Host "Release archive created: $archivePath"
Write-Host "Upload example:"
Write-Host "  scp $archivePath user@server:/opt/market/incoming/"
