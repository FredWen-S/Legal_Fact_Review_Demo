@echo off
setlocal
if exist "%~dp0app\main.py" (
    cd /d "%~dp0"
) else (
    cd /d "%~dp0..\.."
)

echo 正在尝试停止本项目启动的 Streamlit 服务……

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and ($_.CommandLine -like '*streamlit*') -and (($_.CommandLine -like '*app\main.py*') -or ($_.CommandLine -like '*app/main.py*')) }; if ($procs) { $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('已停止进程 PID=' + $_.ProcessId) } } else { Write-Host '未找到可精确识别的 Streamlit 服务。若服务仍在运行，请关闭 start.bat 对应窗口，或在任务管理器中结束对应 Python 进程。' }"

echo.
pause
endlocal
