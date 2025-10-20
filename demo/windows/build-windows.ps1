<#
PowerShell helper to build the Windows Shure System API Docker image from a Windows host.
Usage:
  ./build-windows.ps1 -InstallerPath 'C:\path\to\SystemAPI-Windows-6.6.0.exe' -SilentArgs '/S /quiet' -Tag 'micboard/shure-system-api:win'
#>
param(
  [Parameter(Mandatory=$true)]
  [string]$InstallerPath,
  [string]$SilentArgs = '/S /quiet',
  [string]$Tag = 'micboard/shure-system-api:win'
)

if (-Not (Test-Path $InstallerPath)) {
  Write-Error "Installer not found at $InstallerPath"
  exit 1
}

# Copy installer to a temporary folder accessible by Docker
$tempDir = Join-Path $env:TEMP "micboard-windows-build"
if (-Not (Test-Path $tempDir)) { New-Item -Path $tempDir -ItemType Directory | Out-Null }
$destPath = Join-Path $tempDir (Split-Path $InstallerPath -Leaf)
Copy-Item -Path $InstallerPath -Destination $destPath -Force

Write-Host "Building Docker image with installer $destPath"
cd (Split-Path -Path $PSScriptRoot -Parent)

docker build --progress=plain `
  --build-arg SHURE_INSTALLER_FILE=$(Split-Path $destPath -Leaf) `
  --build-arg SHURE_INSTALLER_SILENT_ARGS="$SilentArgs" `
  -t $Tag demo/windows

Write-Host "Build complete.\nYou may remove the temporary installer: $destPath"
