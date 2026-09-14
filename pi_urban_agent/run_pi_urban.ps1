[CmdletBinding()]
param(
    [string]$RunDir,
    [string]$Provider = $(if ($env:URBAN_PI_PROVIDER) { $env:URBAN_PI_PROVIDER } else { "kimi-code" }),
    [string]$Model = $(if ($env:URBAN_PI_MODEL) { $env:URBAN_PI_MODEL } else { "kimi-for-coding" }),
    [int]$ContextWindow = 0,
    [int]$MaxOutputTokens = 0,
    [ValidateSet("auto", "micro", "compact", "balanced", "spacious")]
    [string]$ContextProfile = "auto",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PiArguments
)

$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$env:URBAN_PI_REPOSITORY_ROOT = $repositoryRoot
if ($RunDir) {
    $env:URBAN_PI_RUN_DIR = [System.IO.Path]::GetFullPath($RunDir)
}
$env:PI_CODING_AGENT_DIR = Join-Path $PSScriptRoot ".pi-agent"
if ($ContextWindow -gt 0) { $env:URBAN_CONTEXT_WINDOW = "$ContextWindow" }
if ($MaxOutputTokens -gt 0) { $env:URBAN_MAX_OUTPUT_TOKENS = "$MaxOutputTokens" }
$env:URBAN_CONTEXT_PROFILE = $ContextProfile

$runtimeConfig = if ($RunDir) {
    Join-Path ([System.IO.Path]::GetFullPath($RunDir)) ".pi-agent-runtime"
} else {
    Join-Path ([System.IO.Path]::GetTempPath()) "urban-agent-pi-model-$PID"
}
$tsx = Join-Path $PSScriptRoot "node_modules\.bin\tsx.cmd"
$configScript = Join-Path $PSScriptRoot "scripts\materialize-model-config.ts"
$configArgs = @(
    $configScript,
    "--source", (Join-Path $PSScriptRoot ".pi-agent\models.json"),
    "--out-dir", $runtimeConfig,
    "--provider", $Provider,
    "--model", $Model
)
if ($ContextWindow -gt 0) { $configArgs += @("--context-window", "$ContextWindow") }
if ($MaxOutputTokens -gt 0) { $configArgs += @("--max-output-tokens", "$MaxOutputTokens") }
& $tsx @configArgs
if ($LASTEXITCODE -ne 0) { throw "Failed to materialize the Pi model and adaptive compaction configuration." }
$env:PI_CODING_AGENT_DIR = $runtimeConfig

if ($Provider -eq "kimi-code") {
    $dotenvPath = Join-Path $repositoryRoot ".env"
    $keyLine = Get-Content -LiteralPath $dotenvPath |
        Where-Object { $_ -match "^\s*KIMI_CODE_API_KEY\s*=" } |
        Select-Object -First 1
    if (-not $keyLine) { throw "KIMI_CODE_API_KEY is not configured in $dotenvPath" }
    $key = ($keyLine -split "=", 2)[1].Trim().Trim('"').Trim("'")
    if ([string]::IsNullOrWhiteSpace($key)) { throw "KIMI_CODE_API_KEY is empty in $dotenvPath" }
    $env:KIMI_CODE_API_KEY = $key
}
elseif ($Provider -eq "local-vllm") {
    if (-not $env:VLLM_BASE_URL) { $env:VLLM_BASE_URL = "http://127.0.0.1:8000/v1" }
    if (-not $env:VLLM_API_KEY) { $env:VLLM_API_KEY = "local-vllm" }
}

$pi = Join-Path $PSScriptRoot "node_modules\.bin\pi.cmd"
$extension = Join-Path $PSScriptRoot ".pi\extensions\urban-agent.ts"
if (-not (Test-Path -LiteralPath $pi)) {
    throw "Pi is not installed. From $PSScriptRoot run: npm install --omit=dev"
}

& $pi -e $extension --no-builtin-tools --provider $Provider --model $Model @PiArguments
exit $LASTEXITCODE
