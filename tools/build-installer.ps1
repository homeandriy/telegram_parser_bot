param(
    [string]$InnoSetup = "iscc.exe"
)

$projectRoot = Split-Path -Parent $PSScriptRoot
& $InnoSetup (Join-Path $projectRoot 'installer\telegram-alert-monitor.iss')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
