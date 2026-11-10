param(
    [switch]$NoShortcut
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Write-Ok([string]$Text) {
    Write-Host "  [OK] $Text" -ForegroundColor Green
}

function Write-Warn([string]$Text) {
    Write-Host "  [!] $Text" -ForegroundColor Yellow
}

function Fail([string]$Text) {
    Write-Host ""
    Write-Host "[ERRO] $Text" -ForegroundColor Red
    exit 1
}

function Get-PythonVersion([string]$Exe) {
    try {
        $version = & $Exe -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -ne 0) { return $null }
        return ("$version").Trim()
    } catch {
        return $null
    }
}

function Test-Python([string]$Exe) {
    $version = Get-PythonVersion $Exe
    if (-not $version) { return $false }
    $parts = $version.Split(".")
    # O projeto usa numpy 2 e os pacotes winrt; 3.11+ e o minimo suportado
    # (o mesmo exigido pelo run.bat e pelo README).
    return ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 11)
}

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Find-SystemPython {
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        try {
            $exe = & py -3 -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $exe -and (Test-Python "$exe".Trim())) {
                return "$exe".Trim()
            }
        } catch { }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python -and (Test-Python $python.Source)) {
        return $python.Source
    }

    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python314\python.exe"),
        "C:\Python312\python.exe",
        "C:\Python313\python.exe"
    )
    foreach ($candidate in $candidates) {
        if ((Test-Path $candidate) -and (Test-Python $candidate)) {
            return $candidate
        }
    }
    return $null
}

function Install-Python {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Step "Python nao encontrado. Tentando instalar pelo winget..."
        try {
            & winget install --id Python.Python.3.12 -e --silent `
                --accept-package-agreements --accept-source-agreements
        } catch {
            Write-Warn "O winget nao conseguiu instalar o Python."
        }
        Refresh-Path
        $found = Find-SystemPython
        if ($found) { return $found }
    }

    $url = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
    $installer = Join-Path $env:TEMP "piratefarm-python-3.12.10.exe"
    Write-Step "Baixando o Python oficial (cerca de 27 MB)..."
    try {
        Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
    } catch {
        Fail "Nao consegui baixar o Python. Verifique a internet e tente de novo."
    }

    Write-Step "Instalando o Python para o seu usuario..."
    $arguments = @(
        "/quiet",
        "InstallAllUsers=0",
        "PrependPath=1",
        "Include_launcher=1",
        "InstallLauncherAllUsers=0",
        "Include_pip=1",
        "Include_test=0"
    )
    $process = Start-Process -FilePath $installer -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        Fail "A instalacao do Python falhou (codigo $($process.ExitCode))."
    }

    Refresh-Path
    return (Find-SystemPython)
}

Write-Host ""
Write-Host "  Pirate Farm 1.2.1 - instalador" -ForegroundColor Yellow
Write-Host "  Pasta: $Root"
Write-Host ""

$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
$systemPython = $null

if (-not (Test-Path $venvPython)) {
    Write-Step "Procurando o Python..."
    $systemPython = Find-SystemPython
    if (-not $systemPython) {
        $systemPython = Install-Python
    }
    if (-not $systemPython) {
        Fail "O Python nao foi encontrado depois da instalacao. Reinicie o computador e rode o Instalar.bat novamente."
    }
    Write-Ok "Python encontrado: $systemPython"

    Write-Step "Criando o ambiente isolado (.venv)..."
    if (Test-Path (Join-Path $Root ".venv")) {
        & $systemPython -m venv --clear ".venv"
    } else {
        & $systemPython -m venv ".venv"
    }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
        Fail "Nao consegui criar o ambiente .venv."
    }
} else {
    Write-Ok "Ambiente .venv ja existe."
}

Write-Step "Atualizando o instalador de pacotes..."
& $venvPython -m pip install --upgrade pip --disable-pip-version-check
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Nao consegui atualizar o pip; vou tentar instalar mesmo assim."
}

Write-Step "Instalando as dependencias (pode levar alguns minutos)..."
& $venvPython -m pip install -r "requirements.txt" --disable-pip-version-check
if ($LASTEXITCODE -ne 0) {
    Fail "Nao consegui instalar as dependencias. Verifique a internet e tente novamente."
}

Write-Step "Conferindo a instalacao..."
& $venvPython -c "import cv2, numpy, mss, pydirectinput, win32api; print('dependencias principais ok')"
if ($LASTEXITCODE -ne 0) {
    Fail "As dependencias principais nao foram carregadas corretamente."
}
& $venvPython -c "import winrt.windows.media.ocr, winrt.windows.graphics.imaging, winrt.windows.storage, winrt.windows.storage.streams, winrt.windows.globalization; print('OCR do Windows ok')"
if ($LASTEXITCODE -ne 0) {
    Write-Warn "O OCR do Windows nao esta disponivel. As capturas ainda serao enviadas com o nome generico."
}

if ($NoShortcut) {
    Write-Ok "Atalho da area de trabalho ignorado (-NoShortcut)."
} else {
    Write-Step "Criando o atalho na area de trabalho..."
    $desktop = [Environment]::GetFolderPath("Desktop")
    $shortcutPath = Join-Path $desktop "Pirate Farm.lnk"
    $launcher = Join-Path $Root "Iniciar.vbs"
    $icon = Join-Path $Root "assets\logo.ico"
    try {
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $launcher
        $shortcut.WorkingDirectory = $Root
        $shortcut.Description = "Pirate Farm"
        if (Test-Path $icon) {
            $shortcut.IconLocation = "$icon,0"
        }
        $shortcut.Save()
        Write-Ok "Atalho criado: $shortcutPath"
    } catch {
        Write-Warn "Nao consegui criar o atalho. Use o Iniciar.bat na pasta do jogo."
    }
}

Write-Host ""
Write-Host "  Instalacao concluida!" -ForegroundColor Green
Write-Host "  Abra o atalho 'Pirate Farm' na area de trabalho ou o Iniciar.bat."
Write-Host ""
