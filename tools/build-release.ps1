param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $projectRoot
try {
    .\.venv\Scripts\python.exe -m pip install -e '.[ui,build]'
    .\.venv\Scripts\python.exe -m unittest discover -s tests
    .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean TelegramAlertMonitor.spec
    & "$PSScriptRoot\build-installer.ps1" -Version $Version
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed: $LASTEXITCODE" }

    Compress-Archive -Path dist\TelegramAlertMonitor\* -DestinationPath "dist\TelegramAlertMonitor-v$Version-windows-x64.zip" -Force
} finally {
    Pop-Location
}
