param([string]$Run='subagent_tester_20260916_r1', [string]$DataRoot='raw_case/data', [string]$Condition='urban_full_v2', [string]$OutRoot='evaluation/raw_api_20260916/kimi-code')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $root
foreach($line in Get-Content -LiteralPath (Join-Path $root '../../.env')){
 if($line -match '^\s*kimi_code_apikey\s*=\s*(.+?)\s*$'){$env:URBAN_UPSTREAM_API_KEY=$Matches[1].Trim().Trim('"').Trim("'")}
}
if(-not $env:URBAN_UPSTREAM_API_KEY){throw 'kimi_code_apikey missing'}
$env:HTTP_PROXY='';$env:HTTPS_PROXY='';$env:ALL_PROXY='';$env:NO_PROXY='*';$env:NODE_USE_ENV_PROXY='0'
$env:URBAN_PI_PYTHON=[IO.Path]::GetFullPath((Join-Path $root '../.venv-section4/Scripts/python.exe'))
$env:URBAN_TOKENIZER_DIR=''
$env:URBAN_SESSION_REQUEST_LIMIT='128'
& 'C:/Users/18029/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe' --import tsx scripts/long-workflow-session.ts --out "$OutRoot/$Run" --condition $Condition --data-root $DataRoot --model kimi-for-coding --provider kimi-code-openai --base-url https://api.kimi.com/coding/v1 --window 262144 --output-tokens 16384 --sampling kimi-compatible --thinking low --deadline 1200
exit $LASTEXITCODE
