@echo off
REM setup_helper.bat — Double-click helper to register the WSL_ADMIN task.
REM Prompts for UAC elevation once, then runs setup_task.ps1.

echo Requesting administrator privileges...
powershell.exe -Command "Start-Process powershell.exe -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"%~dp0setup_task.ps1\"' -Verb RunAs"
echo.
echo Approve the UAC prompt to register the scheduled task.
echo Setup is complete once the elevated window finishes.
pause
