$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pidPath = Join-Path $projectRoot "openclaw-logs\salework_gemini_bot.pid"
$superPidPath = Join-Path $projectRoot "openclaw-logs\salework_gemini_bot.supervisor.pid"

function Stop-OneByPidFile([string]$path, [string]$label) {
    if (!(Test-Path $path)) {
        Write-Host "$label PID file not found."
        return
    }
    $pidValue = Get-Content $path -ErrorAction SilentlyContinue | Select-Object -First 1
    if (!$pidValue) {
        Remove-Item -LiteralPath $path -Force
        Write-Host "Empty $label PID file removed."
        return
    }
    $process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
    if (!$process) {
        Remove-Item -LiteralPath $path -Force
        Write-Host "$label is not running. PID file removed."
        return
    }
    Stop-Process -Id $pidValue -Force
    Remove-Item -LiteralPath $path -Force
    Write-Host "Stopped $label. PID=$pidValue"
}

# Stop supervisor first so it does not relaunch the bot we are about to kill.
Stop-OneByPidFile $superPidPath "supervisor"
Stop-OneByPidFile $pidPath "bot"
