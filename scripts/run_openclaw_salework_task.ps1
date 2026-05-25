$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

.\scripts\start_openclaw_salework.ps1

$taskPath = Join-Path $projectRoot "openclaw_salework_task.txt"
if (-not (Test-Path -LiteralPath $taskPath)) {
    throw "Task file not found: $taskPath"
}

$message = "Doc file G:\shopee-bot\openclaw_salework_task.txt va thuc hien dung noi dung trong do. Phien nay duoc auto gui toi da 5 khach voi case DE an toan; tuyet doi khong gui case KHO hoac rui ro chinh sach Shopee. Dung lai va bao cao sau khi gui du 5 tin hoac khong con case an toan."

openclaw agent --agent main --thinking off --timeout 1200 --message "$message"
