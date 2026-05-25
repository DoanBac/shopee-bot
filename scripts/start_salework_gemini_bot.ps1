param(
    [int]$MaxSend = 30,
    [double]$PollSeconds = 6,
    [switch]$Once,
    [switch]$DryRun,
    [switch]$NoGemini,
    [switch]$Supervised
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot "venv\Scripts\python.exe"
$script = Join-Path $projectRoot "scripts\salework_gemini_ui_bot.py"
$logDir = Join-Path $projectRoot "openclaw-logs"
$pidPath = Join-Path $logDir "salework_gemini_bot.pid"
$superPidPath = Join-Path $logDir "salework_gemini_bot.supervisor.pid"
$stdoutPath = Join-Path $logDir "salework_gemini_bot.stdout.log"
$stderrPath = Join-Path $logDir "salework_gemini_bot.stderr.log"
$supervisor = Join-Path $projectRoot "scripts\supervise_salework_bot.ps1"

New-Item -ItemType Directory -Path $logDir -Force | Out-Null

# Supervised mode → hand off to the auto-restart supervisor.
if ($Supervised) {
    if (Test-Path $superPidPath) {
        $existingSuper = Get-Content $superPidPath -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($existingSuper -and (Get-Process -Id $existingSuper -ErrorAction SilentlyContinue)) {
            Write-Host "Supervisor already running. PID=$existingSuper"
            exit 0
        }
    }
    $superArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $supervisor, "-MaxSend", "9999", "-PollSeconds", $PollSeconds)
    if ($DryRun)   { $superArgs += "-DryRun" }
    if ($NoGemini) { $superArgs += "-NoGemini" }
    $superProc = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList $superArgs `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -PassThru
    Write-Host "Started supervised Salework bot. SupervisorPID=$($superProc.Id)"
    exit 0
}

if (Test-Path $pidPath) {
    $oldPid = Get-Content $pidPath -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($oldPid -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {
        Write-Host "Bot is already running. PID=$oldPid"
        exit 0
    }
}

$argsList = @(
    $script,
    "--max-send", $MaxSend,
    "--poll-seconds", $PollSeconds
)
if ($Once)     { $argsList += "--once" }
if ($DryRun)   { $argsList += "--dry-run" }
if ($NoGemini) { $argsList += "--no-gemini" }

$process = Start-Process `
    -FilePath $python `
    -ArgumentList $argsList `
    -WorkingDirectory $projectRoot `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath `
    -WindowStyle Hidden `
    -PassThru

$process.Id | Set-Content -Path $pidPath -Encoding ascii
Write-Host "Started Salework Gemini bot. PID=$($process.Id)"
Write-Host "Log: $stdoutPath"
