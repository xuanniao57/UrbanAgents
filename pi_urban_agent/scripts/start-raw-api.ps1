param([ValidateSet('qwen3.5-plus','qwen3.8-max')][string]$Model='qwen3.5-plus', [string]$Run='raw_full_r01', [ValidateSet('off','low','medium','xhigh')][string]$Thinking='low')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $root
foreach($line in Get-Content -LiteralPath (Join-Path $root '../../.env')){
 if($line -match '^\s*QWEN_API_KEY\s*=\s*(.+?)\s*$'){$env:URBAN_UPSTREAM_API_KEY=$Matches[1].Trim().Trim('"').Trim("'")}
 if($line -match '^\s*QWEN_API_BASE\s*=\s*(.+?)\s*$'){$env:QWEN_API_BASE=$Matches[1].Trim().Trim('"').Trim("'")}
}
if(-not $env:URBAN_UPSTREAM_API_KEY){throw 'QWEN_API_KEY missing'}
$cfg=Get-Content '.pi-agent/models.json' -Raw|ConvertFrom-Json
$url=$cfg.providers.'aliyun-bailian'.baseUrl
if($url -eq '$QWEN_API_BASE'){$url=$env:QWEN_API_BASE}
$url=$url -replace '/api/v1/?$', '/compatible-mode/v1'
$env:HTTP_PROXY='';$env:HTTPS_PROXY='';$env:ALL_PROXY='';$env:NO_PROXY='*';$env:NODE_USE_ENV_PROXY='0'
$env:URBAN_PI_PYTHON=[IO.Path]::GetFullPath((Join-Path $root '../.venv-section4/Scripts/python.exe'))
$env:URBAN_TOKENIZER_DIR=Join-Path $root 'cache/qwen35-tokenizer'
& 'C:/Users/18029/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe' --import tsx scripts/long-workflow-session.ts --out "evaluation/raw_api_20260915/$Model/$Run" --condition urban_full_v2 --data-root raw_case/data --model $Model --provider aliyun-bailian --base-url $url --window 32768 --output-tokens 8192 --sampling qwen-coding-compatible --thinking $Thinking --deadline 600
exit $LASTEXITCODE
