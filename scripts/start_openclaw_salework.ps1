$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$edgePath = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
$edgeUserData = Join-Path $env:LOCALAPPDATA "Microsoft\Edge\User Data"

if (-not (Test-Path -LiteralPath $edgePath)) {
    throw "Microsoft Edge not found at $edgePath"
}

Start-Process -FilePath $edgePath -ArgumentList @(
    "--remote-debugging-port=9222",
    "--user-data-dir=$edgeUserData",
    "https://chat.salework.net/conversations"
)

Start-Sleep -Seconds 5

try {
    Invoke-RestMethod -Uri "http://127.0.0.1:9222/json/version" -TimeoutSec 5 | Out-Null
} catch {
    throw "Edge remote debugging is not available on 127.0.0.1:9222. Close Edge fully, run this script again, then keep Edge open."
}

openclaw gateway start
Start-Sleep -Seconds 3
openclaw browser --browser-profile edgeremote open "https://chat.salework.net/conversations"
openclaw gateway status

