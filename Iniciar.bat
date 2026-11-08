@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo Primeira execucao: instalando os componentes necessarios...
    call "%~dp0Instalar.bat"
)

if not exist ".venv\Scripts\pythonw.exe" (
    echo.
    echo [ERRO] O Pirate Farm ainda nao esta instalado.
    echo Execute o Instalar.bat nesta pasta e tente de novo.
    echo.
    pause
    exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" "%~dp0main.py"
exit /b 0
