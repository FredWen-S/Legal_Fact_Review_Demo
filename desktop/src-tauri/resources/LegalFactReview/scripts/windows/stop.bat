@echo off
setlocal EnableExtensions
chcp 65001 >nul

if exist "%~dp0app\main.py" (
    cd /d "%~dp0"
) else (
    cd /d "%~dp0..\.."
)

echo Trying to stop LegalFactReview Streamlit service...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and ($_.CommandLine -like '*streamlit*') -and (($_.CommandLine -like '*app\main.py*') -or ($_.CommandLine -like '*app/main.py*')) }; if ($procs) { $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('Stopped PID=' + $_.ProcessId) } } else { Write-Host 'No matching Streamlit process was found. Close the start.bat window if the service is still running.' }"

pause
endlocal
