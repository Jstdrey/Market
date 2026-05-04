param(
    [Parameter(Mandatory = $true)]
    [string]$ArchivePath,
    [Parameter(Mandatory = $true)]
    [string]$ServerHost,
    [string]$ServerUser = "root",
    [string]$RemoteDir = "/opt/market/incoming"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ArchivePath)) {
    throw "Archive not found: $ArchivePath"
}

$remoteTarget = "$ServerUser@$ServerHost"

Write-Host "Creating remote directory: $RemoteDir"
& ssh $remoteTarget "mkdir -p $RemoteDir"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create remote directory: $RemoteDir"
}

Write-Host "Uploading archive to $remoteTarget`:$RemoteDir/"
& scp $ArchivePath "${remoteTarget}:$RemoteDir/"
if ($LASTEXITCODE -ne 0) {
    throw "Upload failed"
}

Write-Host "Upload completed."
