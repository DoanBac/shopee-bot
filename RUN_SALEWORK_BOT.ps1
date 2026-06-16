param(
    [int]$MaxSend = 30,
    [double]$PollSeconds = 3,
    [switch]$Restart,
    [switch]$Supervised,
    [switch]$DryRun,
    [switch]$NoGemini,
    [switch]$NoPause,
    [switch]$SkipPythonInstall,
    [switch]$SkipOpenClawInstall
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$LogDir = Join-Path $ProjectRoot "openclaw-logs"
$PidPath = Join-Path $LogDir "salework_gemini_bot.pid"
$EnvPath = Join-Path $ProjectRoot ".env"
$RequirementsPath = Join-Path $ProjectRoot "requirements.txt"
$VenvPython = Join-Path $ProjectRoot "venv\Scripts\python.exe"
$BotStartScript = Join-Path $ProjectRoot "scripts\start_salework_gemini_bot.ps1"
$BotStopScript = Join-Path $ProjectRoot "scripts\stop_salework_gemini_bot.ps1"
$SaleworkBrowserScript = Join-Path $ProjectRoot "scripts\start_openclaw_salework.ps1"
$LookupBrowserScript = Join-Path $ProjectRoot "scripts\start_edge_shopee_lookup.ps1"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Finish-Or-Pause([int]$ExitCode) {
    if (-not $NoPause) {
        Write-Host ""
        Read-Host "Nhan Enter de dong cua so"
    }
    exit $ExitCode
}

function Find-SystemPython {
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        return @{ File = $pyLauncher.Source; Args = @("-3") }
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{ File = $python.Source; Args = @() }
    }
    return $null
}

function Ensure-PythonVenv {
    if (Test-Path -LiteralPath $VenvPython) {
        return
    }

    if ($SkipPythonInstall) {
        throw "venv is missing and -SkipPythonInstall was provided. Create venv first or run without -SkipPythonInstall."
    }

    Write-Step "Tao Python venv"
    $systemPython = Find-SystemPython
    if (-not $systemPython) {
        throw "Khong tim thay Python. Cai Python 3.11+ roi chay lai file nay."
    }

    & $systemPython.File @($systemPython.Args + @("-m", "venv", "venv"))
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        throw "Tao venv that bai. Khong tim thay $VenvPython"
    }
}

function Ensure-PythonPackages {
    if ($SkipPythonInstall) {
        return
    }
    if (-not (Test-Path -LiteralPath $RequirementsPath)) {
        throw "Khong tim thay requirements.txt"
    }

    Write-Step "Kiem tra/cai Python packages"
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r $RequirementsPath
}

function Ensure-EnvFile {
    if (-not (Test-Path -LiteralPath $EnvPath)) {
        $example = Join-Path $ProjectRoot ".env.example"
        if (Test-Path -LiteralPath $example) {
            Copy-Item -LiteralPath $example -Destination $EnvPath -Force
        } else {
            New-Item -ItemType File -Path $EnvPath -Force | Out-Null
        }
        throw "Da tao .env mau. Dien GEMINI_API_KEY vao $EnvPath roi chay lai."
    }

    $envText = Get-Content -LiteralPath $EnvPath -Raw -Encoding UTF8
    if ($envText -notmatch "(?m)^GEMINI_API_KEY\s*=\s*\S+") {
        throw ".env chua co GEMINI_API_KEY. Dien key vao $EnvPath roi chay lai."
    }
}

function Ensure-OpenClaw {
    $openclaw = Get-Command openclaw -ErrorAction SilentlyContinue
    if ($openclaw) {
        return
    }

    if ($SkipOpenClawInstall) {
        throw "Khong tim thay openclaw trong PATH. Cai OpenClaw roi chay lai."
    }

    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) {
        throw "Khong tim thay openclaw va npm. Cai Node.js LTS, sau do chay: npm install -g openclaw"
    }

    Write-Step "Cai OpenClaw bang npm"
    & npm install -g openclaw

    $openclaw = Get-Command openclaw -ErrorAction SilentlyContinue
    if (-not $openclaw) {
        throw "Da cai OpenClaw nhung PATH chua nhan openclaw. Dong PowerShell, mo lai va chay file nay."
    }
}

function Start-Gateway {
    Write-Step "Bat OpenClaw gateway"
    try {
        openclaw gateway start | Out-Host
    } catch {
        Write-Host "Gateway start tra loi loi, thu kiem tra trang thai..." -ForegroundColor Yellow
    }

    Start-Sleep -Seconds 4
    openclaw gateway status | Out-Host
}

function Start-Browsers {
    Write-Step "Mo Salework Chat"
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $SaleworkBrowserScript
    } catch {
        Write-Host "Khong mo duoc Salework bang profile Edge mac dinh." -ForegroundColor Yellow
        Write-Host "Neu Edge dang mo san, hay dong het Edge roi chay lai file nay." -ForegroundColor Yellow
        throw
    }

    Write-Step "Mo Edge rieng de tra cuu Shopee"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $LookupBrowserScript
}

function Stop-BotIfNeeded {
    if ($Restart) {
        Write-Step "Dung bot cu neu dang chay"
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $BotStopScript
        return
    }

    if (Test-Path -LiteralPath $PidPath) {
        $oldPid = Get-Content -LiteralPath $PidPath -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($oldPid -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {
            Write-Host "Bot dang chay san. PID=$oldPid"
            Write-Host "Muon restart thi chay: powershell -ExecutionPolicy Bypass -File .\RUN_SALEWORK_BOT.ps1 -Restart"
            Finish-Or-Pause 0
        }
    }
}

function Start-Bot {
    Write-Step "Start Salework bot"
    $botArgs = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $BotStartScript,
        "-MaxSend", $MaxSend,
        "-PollSeconds", $PollSeconds
    )
    if ($Supervised) { $botArgs += "-Supervised" }
    if ($DryRun) { $botArgs += "-DryRun" }
    if ($NoGemini) { $botArgs += "-NoGemini" }

    & powershell.exe @botArgs
}

function Show-Result {
    Write-Step "Trang thai bot"
    if (Test-Path -LiteralPath $PidPath) {
        $pidValue = Get-Content -LiteralPath $PidPath -ErrorAction SilentlyContinue | Select-Object -First 1
        $proc = if ($pidValue) { Get-Process -Id $pidValue -ErrorAction SilentlyContinue } else { $null }
        if ($proc) {
            Write-Host "Bot dang chay. PID=$pidValue" -ForegroundColor Green
        } else {
            Write-Host "Co PID file nhung process khong chay. Kiem tra log." -ForegroundColor Yellow
        }
    } else {
        Write-Host "Khong thay PID file. Kiem tra log." -ForegroundColor Yellow
    }

    Write-Host "Log stdout: $(Join-Path $LogDir 'salework_gemini_bot.stdout.log')"
    Write-Host "Log stderr: $(Join-Path $LogDir 'salework_gemini_bot.stderr.log')"
}

try {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

    Stop-BotIfNeeded
    Ensure-EnvFile
    Ensure-PythonVenv
    Ensure-PythonPackages
    Ensure-OpenClaw
    Start-Gateway
    Start-Browsers
    Start-Bot
    Show-Result

    Write-Host ""
    Write-Host "Xong. Neu may nay chua login Salework, hay login trong cua so Edge vua mo roi chay lai file nay." -ForegroundColor Green
    Finish-Or-Pause 0
} catch {
    Write-Host ""
    Write-Host "LOI: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Goi y: chay PowerShell bang lenh:" -ForegroundColor Yellow
    Write-Host "powershell -ExecutionPolicy Bypass -File .\RUN_SALEWORK_BOT.ps1" -ForegroundColor Yellow
    Finish-Or-Pause 1
}
