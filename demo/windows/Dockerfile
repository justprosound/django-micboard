### Windows Server Core image for Shure System API demo
### NOTE: This requires a Windows Docker host (Windows Server or Windows 10/11 with Containers enabled).

FROM mcr.microsoft.com/windows/servercore:ltsc2022

SHELL ["powershell", "-Command", "$ErrorActionPreference = 'Stop';"]

ARG SHURE_INSTALLER_URL=""
ARG SHURE_INSTALLER_FILE="ShureSystemAPI.msi"

# Prepare temp dir
RUN New-Item -Path C:\temp -ItemType Directory -Force | Out-Null

# Copy local installer if present in build context
COPY ${SHURE_INSTALLER_FILE} C:\temp\${SHURE_INSTALLER_FILE}

# Download the installer if not present and URL provided
RUN powershell -Command "if ((Test-Path 'C:\temp\${env:SHURE_INSTALLER_FILE}') -eq $false -and -not [string]::IsNullOrEmpty('${SHURE_INSTALLER_URL}')) { Write-Host 'Downloading installer...'; Invoke-WebRequest -Uri '${SHURE_INSTALLER_URL}' -OutFile 'C:\temp\${env:SHURE_INSTALLER_FILE}' } else { Write-Host 'Installer already present or no URL provided.' }"

# Install if present
RUN powershell -Command "if (Test-Path 'C:\temp\${env:SHURE_INSTALLER_FILE}') { Write-Host 'Installing Shure System API...'; Start-Process -FilePath 'msiexec.exe' -ArgumentList '/i','C:\temp\${env:SHURE_INSTALLER_FILE}','/qn','/norestart' -Wait } else { Write-Host 'Installer not found; skipping installation' }"

# Expose default Shure API port
EXPOSE 10000

# Copy entrypoint script
COPY entrypoint.ps1 C:\entrypoint.ps1

RUN powershell -Command "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope LocalMachine -Force"

ENTRYPOINT ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-File","C:\entrypoint.ps1"]
