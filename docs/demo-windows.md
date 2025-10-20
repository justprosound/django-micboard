# Windows Demo Container

This document explains how to build and run a Windows container for the Shure System API used in local demos.

Important: Building and running Windows containers requires a Windows host (Windows Server 2019/2022 or Windows 10/11 with containers enabled and Docker for Windows).

## Building the image

Copy the Shure System API installer into the `demo/windows/` directory and build the image:

```powershell
# From project root on Windows host
docker build --build-arg SHURE_INSTALLER_FILE=ShureSystemAPI.msi -t shure-demo:latest demo/windows
```

Alternatively, provide a download URL for the installer at build time:

```powershell
docker build --build-arg SHURE_INSTALLER_URL="https://example.com/ShureSystemAPI.msi" \
  --build-arg SHURE_INSTALLER_FILE=ShureSystemAPI.msi \
  -t shure-demo:latest demo/windows
```

## Running the container

```powershell
docker run -d --name shure-demo -p 10000:10000 shure-demo:latest
```

## Notes

- The container runs the Windows service installed by the MSI and keeps the container alive by sleeping in a loop.
- Installer licensing: Ensure you have a valid license to distribute or use the Shure System API installer.
- This is primarily for local demonstration on Windows hosts; the main `demo/docker` Compose is Linux-focused and will not run this Windows image.
