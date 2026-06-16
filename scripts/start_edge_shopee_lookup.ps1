param(
    [int]$Port = 9333,
    [string]$ProfileName = "edgelookup",
    [string]$StartUrl = "https://shopee.vn"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$edgePath = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
$userDataDir = Join-Path $projectRoot "openclaw-edge-shopee-profile"
$openclawConfig = Join-Path $env:USERPROFILE ".openclaw\openclaw.json"

if (-not (Test-Path -LiteralPath $edgePath)) {
    throw "Microsoft Edge not found at $edgePath"
}
if (-not (Test-Path -LiteralPath $openclawConfig)) {
    throw "OpenClaw config not found at $openclawConfig"
}

New-Item -ItemType Directory -Path $userDataDir -Force | Out-Null

$config = Get-Content -LiteralPath $openclawConfig -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $config.browser) {
    $config | Add-Member -NotePropertyName browser -NotePropertyValue ([pscustomobject]@{})
}
if (-not $config.browser.profiles) {
    $config.browser | Add-Member -NotePropertyName profiles -NotePropertyValue ([pscustomobject]@{})
}

$profileValue = [pscustomobject]@{
    cdpUrl = "http://127.0.0.1:$Port"
    color  = "#0066CC"
}
$existing = $config.browser.profiles.PSObject.Properties[$ProfileName]
if ($existing) {
    $existing.Value = $profileValue
} else {
    $config.browser.profiles | Add-Member -NotePropertyName $ProfileName -NotePropertyValue $profileValue
}

$backupPath = "$openclawConfig.bak.salework-bot"
Copy-Item -LiteralPath $openclawConfig -Destination $backupPath -Force
$config | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $openclawConfig -Encoding UTF8

Start-Process -FilePath $edgePath -ArgumentList @(
    "--remote-debugging-port=$Port",
    "--user-data-dir=$userDataDir",
    "--no-first-run",
    "--new-window",
    $StartUrl
)

Start-Sleep -Seconds 5

try {
    Invoke-RestMethod -Uri "http://127.0.0.1:$Port/json/version" -TimeoutSec 5 | Out-Null
} catch {
    throw "Edge lookup browser is not available on 127.0.0.1:$Port"
}

openclaw gateway restart
Start-Sleep -Seconds 3
openclaw browser --browser-profile $ProfileName open $StartUrl | Out-Null
Write-Host "Started separate Microsoft Edge lookup browser. Profile=$ProfileName Port=$Port UserDataDir=$userDataDir"
