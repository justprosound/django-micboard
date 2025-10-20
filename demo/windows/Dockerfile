### Windows Server image for Shure System API demo
### NOTE: This requires a Windows Docker host (Windows Server 2025 or Windows 11/10 with Containers
### enabled and proper host support). Per Shure System API server requirements, use a full Windows
### Server 2025 base image for compatibility where possible.

FROM mcr.microsoft.com/windows/server:ltsc2025

SHELL ["powershell", "-Command", "$ErrorActionPreference = 'Stop';"]

ARG SHURE_INSTALLER_URL=""
ARG SHURE_INSTALLER_FILE="ShureSystemAPI.msi"
ARG SHURE_INSTALLER_SILENT_ARGS="/qn /norestart"

# Prepare temp dir
RUN New-Item -Path C:\temp -ItemType Directory -Force | Out-Null

# Copy local installer if present in build context
COPY ${SHURE_INSTALLER_FILE} C:\temp\${SHURE_INSTALLER_FILE}

# Download the installer if not present and URL provided
RUN powershell -Command "if ((Test-Path 'C:\temp\${env:SHURE_INSTALLER_FILE}') -eq $false -and -not [string]::IsNullOrEmpty('${SHURE_INSTALLER_URL}')) { Write-Host 'Downloading installer...'; Invoke-WebRequest -Uri '${SHURE_INSTALLER_URL}' -OutFile 'C:\temp\${env:SHURE_INSTALLER_FILE}' } else { Write-Host 'Installer already present or no URL provided.' }"

# Install if present (support MSI and EXE installers; use provided silent args)
RUN powershell -Command "if (Test-Path 'C:\temp\${env:SHURE_INSTALLER_FILE}') { $file = 'C:\temp\' + ${env:SHURE_INSTALLER_FILE}; $ext = [System.IO.Path]::GetExtension($file).ToLower(); Write-Host 'Found installer:' $file; if ($ext -eq '.msi') { Write-Host 'Installing MSI via msiexec with silent args...'; Start-Process -FilePath 'msiexec.exe' -ArgumentList '/i',$file, ${env:SHURE_INSTALLER_SILENT_ARGS} -Wait } else { Write-Host 'Assuming EXE installer; running with provided args...'; Start-Process -FilePath $file -ArgumentList ${env:SHURE_INSTALLER_SILENT_ARGS} -Wait } } else { Write-Host 'Installer not found; skipping installation' }"

# Expose default Shure API port
EXPOSE 10000

# Copy entrypoint script
COPY entrypoint.ps1 C:\entrypoint.ps1

RUN powershell -Command "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope LocalMachine -Force"

ENTRYPOINT ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-File","C:\entrypoint.ps1"]
