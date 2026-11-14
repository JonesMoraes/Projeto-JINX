@echo off
setlocal
cd /d "%~dp0"
set "JINX_PYTHON=%~dp0.venv-local\Scripts\python.exe"
if not exist "%JINX_PYTHON%" set "JINX_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%JINX_PYTHON%" (
    echo Ambiente Python do JINX nao encontrado.
    echo Configure o ambiente e as dependencias de requirements.txt antes de iniciar.
    pause
    exit /b 1
)
if not exist "%~dp0logs" mkdir "%~dp0logs"
if not exist "%~dp0logs" (
    echo Nao foi possivel criar a pasta de logs.
    pause
    exit /b 1
)
echo Iniciando JINX. O diagnostico fica em logs\desktop-start.log.
"%JINX_PYTHON%" -u "%~dp0main.py" >> "%~dp0logs\desktop-start.log" 2>&1
set "JINX_RESULT=%ERRORLEVEL%"
if not "%JINX_RESULT%"=="0" (
    echo O JINX encerrou com erro %JINX_RESULT%. Consulte logs\desktop-start.log.
    pause
)
exit /b %JINX_RESULT%
