# setup_task.ps1 — Register the WSL_ADMIN scheduled task. Run ONCE as Administrator.
#
# This registers a scheduled task that runs C:\temp\wsl_admin_cmd.bat at highest
# privilege. From then on, WSL can trigger admin commands via `schtasks /run` with
# no further UAC prompts. The .bat file is rewritten by win_admin.py on each call.

$ErrorActionPreference = "Stop"

$TaskName = "WSL_ADMIN"
$TempDir  = "C:\temp"
$BatFile  = "$TempDir\wsl_admin_cmd.bat"

# Ensure the scratch directory exists
New-Item -ItemType Directory -Force -Path $TempDir | Out-Null

# Seed an empty trigger file so the task target is valid before first use
if (-not (Test-Path $BatFile)) {
    "@echo off" | Set-Content $BatFile -Encoding ASCII
}

# Register the task: runs the .bat with highest privileges, as the current user.
schtasks /create /tn "$TaskName" /tr "$BatFile" /sc once /st 00:00 /rl highest /f

Write-Host ""
Write-Host "Scheduled task '$TaskName' registered."
Write-Host "Trigger file: $BatFile"
Write-Host "From WSL, test with:  python3 win_admin.py test"
