param(
    [string]$EnvFile = (Join-Path $PSScriptRoot "..\env\kimi_code.env")
)

if (-not (Test-Path $EnvFile)) {
    throw "Missing env file: $EnvFile. Copy env/kimi_code.env.example to env/kimi_code.env and fill in your Kimi Code key first."
}

Get-Content -Path $EnvFile -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#")) {
        $separatorIndex = $line.IndexOf("=")
        if ($separatorIndex -ge 1) {
            $name = $line.Substring(0, $separatorIndex).Trim()
            $value = $line.Substring($separatorIndex + 1).Trim().Trim('"').Trim("'")
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

if (-not $env:KIMI_CODE_API_KEY -or $env:KIMI_CODE_API_KEY -eq "replace_with_your_kimi_code_api_key") {
    throw "KIMI_CODE_API_KEY is not configured. Edit env/kimi_code.env before launching Urban-Hermes."
}

if (-not $env:KIMI_API_KEY -or $env:KIMI_API_KEY -eq "replace_with_your_kimi_code_api_key") {
    $env:KIMI_API_KEY = $env:KIMI_CODE_API_KEY
}

if (-not $env:KIMI_CODING_API_KEY -or $env:KIMI_CODING_API_KEY -eq "replace_with_your_kimi_code_api_key") {
    $env:KIMI_CODING_API_KEY = $env:KIMI_CODE_API_KEY
}

Remove-Item Env:KIMI_BASE_URL -ErrorAction SilentlyContinue

if (-not $env:HERMES_PROVIDER) {
    $env:HERMES_PROVIDER = "kimi-coding"
}

if (-not $env:HERMES_MODEL) {
    $env:HERMES_MODEL = "kimi-for-coding"
}

Write-Host "Loaded Kimi Code API environment for provider=$env:HERMES_PROVIDER model=$env:HERMES_MODEL"
