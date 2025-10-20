# Entry point for Windows Shure System API demo image
# This script will start the Shure System API Windows service if it's installed

$serviceName = 'Shure System API'

Write-Host "Starting entrypoint script..."

try {
    $svc = Get-Service -Name $serviceName -ErrorAction Stop
    if ($svc.Status -ne 'Running') {
        Write-Host "Starting service $serviceName"
        Start-Service -Name $serviceName
    } else {
        Write-Host "$serviceName is already running"
    }
} catch {
    Write-Host "Service $serviceName not found - ensure installer is present or run configuration manually"
}

# Keep the container running by tailing the Windows event logs (or sleeping)
while ($true) {
    Start-Sleep -Seconds 60
}
