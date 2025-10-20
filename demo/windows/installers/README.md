This folder is intended to hold Windows installers used for the demo builds (for example, the Shure System API MSI or EXE).

Do not commit installer binaries to the repository. Instead, prefer one of the following approaches:

- CI builds: provide a publicly accessible or private artifact URL to the installer at build time and pass it as a build-arg:

```bash
docker build \
	--build-arg SHURE_INSTALLER_URL="https://example.com/SystemAPI-Windows-6.6.0.exe" \
	--build-arg SHURE_INSTALLER_FILE="SystemAPI-Windows-6.6.0.exe" \
	--build-arg SHURE_INSTALLER_SILENT_ARGS="/S /quiet" \
	-t micboard-shure-demo:win demo/windows
```

- Local builds on a Windows host: place the installer file in this folder and reference it during build (the Dockerfile copies the provided installer):

```bash
docker build \
	--build-arg SHURE_INSTALLER_FILE="SystemAPI-Windows-6.6.0.exe" \
	--build-arg SHURE_INSTALLER_SILENT_ARGS="/S /quiet" \
	-t micboard-shure-demo:win demo/windows
```

Silent install flags
- MSI installers typically accept: `/qn /norestart` (fully quiet, no reboot)
- EXE installers vary; for many NSIS/InstallShield/other wrappers, `/S` or `/quiet` are common. The Dockerfile accepts a `SHURE_INSTALLER_SILENT_ARGS` build-arg and will pass it to the installer. Set it to the correct value for your installer.

Notes
- If you have a private installer URL, configure your CI to provide it via build secrets or a secure environment variable.
- The Dockerfile will detect the installer extension and use `msiexec` for `.msi` files, otherwise it will attempt to run the EXE with the provided arguments.

Keep this README tracked so the folder is preserved in repositories and for documentation purposes.

CI Build (GitHub Actions)
-------------------------
The repository has a manual GitHub Actions workflow to build the Windows image on a Windows runner:

- Workflow: .github/workflows/build-windows-image.yml
- Trigger: Run the workflow manually (workflow_dispatch) and provide the installer URL, filename and silent args if needed.
- Secrets: Optionally set DOCKERHUB_USERNAME and DOCKERHUB_TOKEN to push the built image.

Example: Use the GitHub UI to run the workflow, or call the GitHub Actions API with inputs for installer_url, installer_file and silent_args.

Local Windows build helper
--------------------------
If you're building locally on a Windows machine, use the provided PowerShell helper script to copy the installer into a Docker-accessible temp folder and run the build:

```powershell
./demo/windows/build-windows.ps1 -InstallerPath 'C:\path\to\SystemAPI-Windows-6.6.0.exe' -SilentArgs '/S /quiet' -Tag 'micboard/shure-system-api:win'
```

The script copies the installer to a temporary folder and runs `docker build` with the necessary build-args. You can remove the temporary file afterwards.
