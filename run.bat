@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Criando o ambiente virtual...
    python -m venv .venv
    if errorlevel 1 goto :error
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto :error
)

start "" ".venv\Scripts\pythonw.exe" main.py
exit /b 0

:error
echo.
echo Falha ao preparar o ambiente. Verifique se o Python esta instalado.
pause
exit /b 1
