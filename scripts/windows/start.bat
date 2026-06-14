@echo off
setlocal
if exist "%~dp0app\main.py" (
    cd /d "%~dp0"
) else (
    cd /d "%~dp0..\.."
)

if not exist "logs" mkdir logs
set "LOG_FILE=logs\startup.log"
echo ===============================================>> "%LOG_FILE%"
echo 启动时间：%date% %time%>> "%LOG_FILE%"
echo 当前目录：%cd%>> "%LOG_FILE%"

echo.
echo 律师文书基础信息与关键事实复核助手正在启动……
echo 启动日志：%cd%\%LOG_FILE%
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON_CMD=py -3"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PYTHON_CMD=python"
    ) else (
        echo 未检测到 Python。
        echo 请先安装 Python 3.10 或更高版本，并勾选 Add Python to PATH。
        echo 下载地址：https://www.python.org/downloads/windows/
        echo 错误：未检测到 Python。>> "%LOG_FILE%"
        echo.
        pause
        exit /b 1
    )
)

%PYTHON_CMD% --version >> "%LOG_FILE%" 2>&1

if not exist ".venv\Scripts\python.exe" (
    echo 正在创建本地虚拟环境 .venv ...
    echo 是否创建虚拟环境：是>> "%LOG_FILE%"
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo 创建虚拟环境失败。请确认 Python 版本为 3.10 或更高。
        echo 错误：创建虚拟环境失败。>> "%LOG_FILE%"
        pause
        exit /b 1
    )
) else (
    echo 是否创建虚拟环境：否>> "%LOG_FILE%"
)

if not exist "data" mkdir data
if not exist "exports" mkdir exports
if not exist "logs" mkdir logs

echo 正在执行启动前环境检查……
".venv\Scripts\python.exe" scripts\windows\preflight_check.py >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo 启动前检查失败。请查看 logs\startup.log。
    type "%LOG_FILE%"
    pause
    exit /b 1
)

set /p PORT=<logs\current_port.txt
if "%PORT%"=="" set "PORT=8501"

echo 正在安装或检查依赖，请稍候……
if exist "wheelhouse" (
    echo 检测到本地 wheelhouse，优先离线安装依赖。
    echo 依赖安装方式：wheelhouse>> "%LOG_FILE%"
    ".venv\Scripts\python.exe" -m pip install --no-index --find-links=wheelhouse -r requirements.txt >> "%LOG_FILE%" 2>&1
    if errorlevel 1 (
        echo 离线依赖安装失败。详情见 logs\startup.log。
        choice /C YN /M "是否尝试联网安装依赖"
        if errorlevel 2 (
            echo 用户取消联网安装。>> "%LOG_FILE%"
            pause
            exit /b 1
        )
        echo 依赖安装方式：online fallback>> "%LOG_FILE%"
        ".venv\Scripts\python.exe" -m pip install -r requirements.txt >> "%LOG_FILE%" 2>&1
        if errorlevel 1 (
            echo 联网依赖安装仍然失败。请查看 logs\startup.log。
            pause
            exit /b 1
        )
    )
) else (
    echo 未检测到 wheelhouse，将联网安装依赖。
    echo 依赖安装方式：online>> "%LOG_FILE%"
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt >> "%LOG_FILE%" 2>&1
    if errorlevel 1 (
        echo 依赖安装失败。请检查网络连接，或联系技术人员预先构建 wheelhouse。
        echo 错误：联网依赖安装失败。>> "%LOG_FILE%"
        pause
        exit /b 1
    )
)

echo 浏览器地址：http://localhost:%PORT%
echo 关闭本窗口即可停止服务。
echo 使用端口：%PORT%>> "%LOG_FILE%"
echo Streamlit 启动命令：.venv\Scripts\python.exe -m streamlit run app\main.py --server.port %PORT% --server.address localhost>> "%LOG_FILE%"
start "" "http://localhost:%PORT%"
".venv\Scripts\python.exe" -m streamlit run app\main.py --server.port %PORT% --server.address localhost >> "%LOG_FILE%" 2>&1

endlocal
