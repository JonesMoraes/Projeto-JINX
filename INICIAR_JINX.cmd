@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 goto fallback
py -3 "%~dp0runtime_manager.py" --launch
goto finish
:fallback
set "JINX_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%JINX_PYTHON%" (
    echo Instale Python estavel do python.org para preparar o JINX.
    pause
    exit /b 1
)
"%JINX_PYTHON%" "%~dp0runtime_manager.py" --launch
:finish
set "JINX_RESULT=%ERRORLEVEL%"
if not "%JINX_RESULT%"=="0" (
    echo Falha %JINX_RESULT%. Consulte logs\python-runtime.log e logs\desktop-start.log.
    pause
)
exit /b %JINX_RESULT%
