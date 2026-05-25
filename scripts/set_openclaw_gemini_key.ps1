$ErrorActionPreference = "Stop"

$secure = Read-Host "Paste NEW Gemini API key" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

if ([string]::IsNullOrWhiteSpace($key)) {
    throw "Gemini API key is empty."
}

$openclawDir = Join-Path $env:USERPROFILE ".openclaw"
New-Item -ItemType Directory -Path $openclawDir -Force | Out-Null

$envFile = Join-Path $openclawDir ".env"
$existing = @()
if (Test-Path -LiteralPath $envFile) {
    $existing = Get-Content -LiteralPath $envFile -Encoding UTF8 |
        Where-Object { $_ -notmatch "^(GEMINI_API_KEY|GOOGLE_API_KEY)=" }
}

$existing + @(
    "GEMINI_API_KEY=$key",
    "GOOGLE_API_KEY=$key"
) | Set-Content -LiteralPath $envFile -Encoding UTF8

[Environment]::SetEnvironmentVariable("GEMINI_API_KEY", $key, "User")
[Environment]::SetEnvironmentVariable("GOOGLE_API_KEY", $key, "User")

openclaw gateway stop
Start-Sleep -Seconds 3
openclaw gateway start
Start-Sleep -Seconds 5
openclaw models status

