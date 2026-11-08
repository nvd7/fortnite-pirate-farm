@echo off
setlocal
cd /d "%~dp0"

where powershell >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERRO] O PowerShell do Windows nao foi encontrado.
    echo Este instalador precisa do Windows 10 ou 11.
    echo.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\instalar.ps1" %*
set "CODE=%ERRORLEVEL%"

if not "%CODE%"=="0" (
    echo.
    echo A instalacao falhou. Veja as mensagens acima.
    echo.
    pause
)
exit /b %CODE%
