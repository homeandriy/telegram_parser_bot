param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version,
    [string]$InnoSetup = "iscc.exe"
)

$projectRoot = Split-Path -Parent $PSScriptRoot
& $InnoSetup "/DAppVersion=$Version" (Join-Path $projectRoot 'installer\telegram-alert-monitor.iss')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
