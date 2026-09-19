param([ValidateSet('4b','9b')][string]$Size='4b', [string]$Run='pi_only_r02', [ValidateSet('urban_full_v2','urban_single_v2','urban_no_memory_v2','pi_native_v2')][string]$Condition='urban_full_v2', [ValidateSet(8192,16384,32768)][int]$Window=8192, [int]$OutputTokens=0, [ValidateSet('greedy','qwen-instruct-compatible','qwen-coding-compatible')][string]$Sampling='greedy', [ValidateSet('off','low')][string]$Thinking='off', [switch]$Resume)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $root
$env:URBAN_PI_PYTHON=[IO.Path]::GetFullPath((Join-Path $root '../.venv-section4/Scripts/python.exe'))
$env:URBAN_TOKENIZER_DIR=Join-Path $root 'cache/qwen35-tokenizer'
$env:HTTP_PROXY='';$env:HTTPS_PROXY='';$env:ALL_PROXY='';$env:NO_PROXY='*';$env:NODE_USE_ENV_PROXY='0'
$windowLabel=([string][int]($Window/1024))+'k'
if($OutputTokens -eq 0){$OutputTokens=[Math]::Min(8192,[int]($Window/4))}
$resumeArgs=@()
if($Resume){$resumeArgs=@('--resume','true')}
& 'C:/Users/18029/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe' --import tsx scripts/long-workflow-session.ts --out "evaluation/raw_local_20260915/$Size/$Run" --condition $Condition --data-root raw_case/data --model "qwen3.5:$Size-urban$windowLabel" --provider local-ollama --base-url http://127.0.0.1:11434/v1 --window $Window --output-tokens $OutputTokens --sampling $Sampling --thinking $Thinking --deadline 600 @resumeArgs
exit $LASTEXITCODE
