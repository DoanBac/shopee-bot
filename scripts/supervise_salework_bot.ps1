param(
    [int]$MaxSend = 9999,
    [double]$PollSeconds = 6,
    [int]$RestartDelaySeconds = 10,
    [int]$DailyRestartHour = 4,
    [switch]$DryRun,
    [switch]$NoGemini,
    [string]$Profile = "edgeremote",
    [string]$LookupProfile = "edgelookup"
)

# Supervisor: keep the Salework UI bot alive 24/7. It re-launches the bot
# whenever the Python process exits (crash, OOM, network loss, etc.), with
# capped exponential backoff. Once a day it forces a fresh restart so the
# browser session, Edge profile and bot state get a clean slate.

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$python = Join-Path $projectRoot "venv\Scripts\python.exe"
$script = Join-Path $projectRoot "scripts\salework_gemini_ui_bot.py"
$logDir = Join-Path $projectRoot "openclaw-logs"
$superLog = Join-Path $logDir "supervisor.log"
$stdoutPath = Join-Path $logDir "salework_gemini_bot.stdout.log"
$stderrPath = Join-Path $logDir "salework_gemini_bot.stderr.log"
$pidPath = Join-Path $logDir "salework_gemini_bot.pid"
$superPidPath = Join-Path $logDir "salework_gemini_bot.supervisor.pid"

New-Item -ItemType Directory -Path $logDir -Force | Out-Null

function Write-SuperLog([string]$msg) {
    $stamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $line = "[$stamp] $msg"
    Write-Host $line
    Add-Content -Path $superLog -Value $line -Encoding utf8
}

if (Test-Path $superPidPath) {
    $existing = Get-Content $superPidPath -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($existing -and (Get-Process -Id $existing -ErrorAction SilentlyContinue)) {
        Write-SuperLog "Supervisor already running. PID=$existing"
        exit 0
    }
}

$PID | Set-Content -Path $superPidPath -Encoding ascii
Write-SuperLog "Supervisor started. PID=$PID"

$consecutiveFailures = 0
$lastDailyRestart = (Get-Date).Date

try {
    while ($true) {
        $argsList = @(
            $script,
            "--profile", $Profile,
            "--lookup-profile", $LookupProfile,
            "--max-send", $MaxSend,
            "--poll-seconds", $PollSeconds
        )
        if ($DryRun)   { $argsList += "--dry-run" }
        if ($NoGemini) { $argsList += "--no-gemini" }

        Write-SuperLog "Launching bot: $python $argsList"
        $startTime = Get-Date
        $proc = Start-Process `
            -FilePath $python `
            -ArgumentList $argsList `
            -WorkingDirectory $projectRoot `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath `
            -WindowStyle Hidden `
            -PassThru

        $proc.Id | Set-Content -Path $pidPath -Encoding ascii
        Write-SuperLog "Bot launched. PID=$($proc.Id)"

        # Watch the process. While it's alive, check once per minute for the
        # daily restart window. If we cross into a new day past the restart
        # hour, kill the bot so the loop relaunches it fresh.
        while (-not $proc.HasExited) {
            Start-Sleep -Seconds 30
            $now = Get-Date
            if ($now.Date -gt $lastDailyRestart -and $now.Hour -ge $DailyRestartHour) {
                Write-SuperLog "Daily restart window reached. Stopping bot for clean restart."
                try { Stop-Process -Id $proc.Id -Force -ErrorAction Stop } catch {}
                $lastDailyRestart = $now.Date
                break
            }
        }

        $exitCode = $null
        try { $exitCode = $proc.ExitCode } catch {}
        $ranSeconds = [int]((Get-Date) - $startTime).TotalSeconds
        Write-SuperLog "Bot exited. ExitCode=$exitCode RanSeconds=$ranSeconds"

        if (Test-Path $pidPath) { Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue }

        if ($ranSeconds -lt 30) {
            $consecutiveFailures++
        } else {
            $consecutiveFailures = 0
        }

        $delay = $RestartDelaySeconds
        if ($consecutiveFailures -gt 0) {
            $delay = [Math]::Min(300, $RestartDelaySeconds * [Math]::Pow(2, [Math]::Min($consecutiveFailures, 5)))
        }
        Write-SuperLog "Sleeping $delay s before relaunch (consecutiveFailures=$consecutiveFailures)"
        Start-Sleep -Seconds $delay
    }
} finally {
    if (Test-Path $superPidPath) { Remove-Item -LiteralPath $superPidPath -Force -ErrorAction SilentlyContinue }
    Write-SuperLog "Supervisor exiting."
}
