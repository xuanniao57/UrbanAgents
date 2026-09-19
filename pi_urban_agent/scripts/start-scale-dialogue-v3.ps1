param(
 [Parameter(Mandatory=$true)][ValidateSet('kimi','qwen38')][string]$Model,
 [Parameter(Mandatory=$true)][ValidateSet('urban_full_v2','urban_no_memory_v2','pi_native_v2')][string]$Condition,
 [Parameter(Mandatory=$true)][int]$ContextWindow,
 [int]$OutputTokens=16384,
 [string]$Repeat='r1',
 [string]$DataRoot='evaluation/case_reproduction_20260916/data'
)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $root
if($Repeat -notmatch '^[a-zA-Z0-9_-]+$'){throw 'Invalid repeat identifier'}
if($ContextWindow -lt 8192 -or $OutputTokens -ge $ContextWindow){throw 'Supply verified provider-supported context/output limits'}
$dotenv=if($env:URBAN_ENV_FILE){$env:URBAN_ENV_FILE}else{Join-Path $root '../../.env'}
Remove-Item Env:URBAN_UPSTREAM_API_KEY -ErrorAction SilentlyContinue
foreach($line in Get-Content -LiteralPath $dotenv){
 if($line -match '^\s*kimi_code_apikey\s*=\s*(.+?)\s*$' -and $Model -eq 'kimi'){$env:URBAN_UPSTREAM_API_KEY=$Matches[1].Trim().Trim('"').Trim("'")}
 if($line -match '^\s*QWEN_API_KEY\s*=\s*(.+?)\s*$' -and $Model -eq 'qwen38'){$env:URBAN_UPSTREAM_API_KEY=$Matches[1].Trim().Trim('"').Trim("'")}
 if($line -match '^\s*QWEN_API_BASE\s*=\s*(.+?)\s*$'){$env:QWEN_API_BASE=$Matches[1].Trim().Trim('"').Trim("'")}
}
if(-not $env:URBAN_UPSTREAM_API_KEY){throw 'Model API credential missing'}
foreach($key in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')){[Environment]::SetEnvironmentVariable($key,'','Process')}
$env:NO_PROXY='*';$env:NODE_USE_ENV_PROXY='0'
$env:URBAN_SESSION_REQUEST_LIMIT='4096'
$env:URBAN_TURN_REQUEST_LIMIT='512'
$env:URBAN_TOOL_CALL_BUDGET='512'
$env:URBAN_TOOL_ERROR_BUDGET='16'
if(-not $env:URBAN_PI_PYTHON){$env:URBAN_PI_PYTHON=[IO.Path]::GetFullPath((Join-Path $root '../.venv-section4/Scripts/python.exe'))}
$env:URBAN_TOKENIZER_DIR=''
if($Model -eq 'kimi'){$provider='kimi-code-openai';$id='kimi-for-coding';$url='https://api.kimi.com/coding/v1';$sampling='kimi-compatible';$thinking='high'}
else{$provider='aliyun-bailian';$id='qwen3.8-max';$url=$env:QWEN_API_BASE -replace '/api/v1/?$', '/compatible-mode/v1';$sampling='qwen-coding-compatible';$thinking='xhigh';if(-not $url){throw 'QWEN_API_BASE missing'}}
$out="evaluation/scale_dialogue_v3/$Model/$Condition/$Repeat"
if(Test-Path "$out/manifest.json"){throw 'Never overwrite an existing run'}
# Runs in the caller terminal; no hidden 90-minute launcher cutoff. Tester writes inbox messages.
& node --import tsx scripts/long-workflow-session.ts --out $out --condition $Condition --data-root $DataRoot --model $id --provider $provider --base-url $url --window $ContextWindow --output-tokens $OutputTokens --sampling $sampling --thinking $thinking --deadline 3600
exit $LASTEXITCODE
