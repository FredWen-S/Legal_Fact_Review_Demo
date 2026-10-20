@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

if exist "%~dp0app\main.py" (
    cd /d "%~dp0"
) else (
    cd /d "%~dp0..\.."
)

if not exist "logs" mkdir "logs"
if not exist "data" mkdir "data"
if not exist "exports" mkdir "exports"

set "LOG_FILE=logs\startup.log"
echo ===============================================>> "%LOG_FILE%"
echo Start time: %date% %time%>> "%LOG_FILE%"
echo Working dir: %cd%>> "%LOG_FILE%"

echo LegalFactReview is starting...
echo Startup log: logs\startup.log
set "PYTHONPATH=%CD%"
echo PYTHONPATH: %PYTHONPATH%>> "%LOG_FILE%"

set "PY_CMD="

py -3.12 --version >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "PY_CMD=py -3.12"
    goto :found_python
)

py -3.11 --version >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "PY_CMD=py -3.11"
    goto :found_python
)

py -3.10 --version >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "PY_CMD=py -3.10"
    goto :found_python
)

python --version >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "PY_CMD=python"
    goto :found_python
)

echo Python 3.10-3.12 is required.
echo Please install Python 3.11 or 3.12 and try again.
echo ERROR: Python 3.10-3.12 was not found.>> "%LOG_FILE%"
pause
exit /b 1

:found_python
echo Using Python command: %PY_CMD%
echo Python command: %PY_CMD%>> "%LOG_FILE%"
%PY_CMD% --version >> "%LOG_FILE%" 2>&1
%PY_CMD% "scripts\windows\preflight_check.py"
if errorlevel 1 (
    echo Preflight check failed. See logs\startup.log
    echo ERROR: preflight check failed.>> "%LOG_FILE%"
    pause
    exit /b 1
)

set "PORT=8501"
if exist "logs\current_port.txt" (
    set /p PORT=<"logs\current_port.txt"
)

if not "%PORT%"=="8501" (
    echo Port 8501 is busy. Using http://localhost:%PORT%
) else (
    echo Using http://localhost:%PORT%
)
echo Port: %PORT%>> "%LOG_FILE%"

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    echo Create venv: yes>> "%LOG_FILE%"
    %PY_CMD% -m venv ".venv"
    if errorlevel 1 (
        echo Failed to create virtual environment.
        echo ERROR: failed to create venv.>> "%LOG_FILE%"
        pause
        exit /b 1
    )
) else (
    echo Create venv: no>> "%LOG_FILE%"
)

set "VENV_PY=.venv\Scripts\python.exe"

if exist "wheelhouse" (
    echo Installing dependencies from local wheelhouse...
    echo Dependency mode: wheelhouse>> "%LOG_FILE%"
    "%VENV_PY%" -m pip install --no-index --find-links="wheelhouse" -r "requirements.txt" >> "%LOG_FILE%" 2>&1
    if errorlevel 1 (
        echo Offline install failed.
        echo Trying online install...
        echo Dependency mode: online fallback>> "%LOG_FILE%"
        "%VENV_PY%" -m pip install -r "requirements.txt" >> "%LOG_FILE%" 2>&1
        if errorlevel 1 (
            echo Dependency installation failed. See logs\startup.log
            echo ERROR: dependency installation failed.>> "%LOG_FILE%"
            pause
            exit /b 1
        )
    )
) else (
    echo Installing dependencies online...
    echo Dependency mode: online>> "%LOG_FILE%"
    "%VENV_PY%" -m pip install -r "requirements.txt" >> "%LOG_FILE%" 2>&1
    if errorlevel 1 (
        echo Dependency installation failed. See logs\startup.log
        echo ERROR: dependency installation failed.>> "%LOG_FILE%"
        pause
        exit /b 1
    )
)

echo Starting Streamlit...
echo Open: http://localhost:%PORT%
echo Streamlit command: %VENV_PY% -m streamlit run app\main.py --server.port %PORT% --server.address localhost>> "%LOG_FILE%"
start "" "http://localhost:%PORT%"
"%VENV_PY%" -m streamlit run "app\main.py" --server.port %PORT% --server.address localhost

pause
endlocal
