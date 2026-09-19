param([ValidateSet('qwen38','9b')][string]$Model,[string]$Round='r1',[string]$Condition='urban_full_v2',[switch]$Resume)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $root
foreach($key in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')){[Environment]::SetEnvironmentVariable($key,'','Process')}
$env:NO_PROXY='*';$env:NODE_USE_ENV_PROXY='0'
$env:URBAN_PI_PYTHON=[IO.Path]::GetFullPath((Join-Path $root '../.venv-section4/Scripts/python.exe'))
$env:URBAN_SESSION_REQUEST_LIMIT='128'
if($Model -eq 'qwen38'){
 foreach($line in Get-Content -LiteralPath (Join-Path $root '../../.env')){
  if($line -match '^\s*QWEN_API_KEY\s*=\s*(.+?)\s*$'){$env:URBAN_UPSTREAM_API_KEY=$Matches[1].Trim().Trim('"').Trim("'")}
  if($line -match '^\s*QWEN_API_BASE\s*=\s*(.+?)\s*$'){$env:QWEN_API_BASE=$Matches[1].Trim().Trim('"').Trim("'")}
 }
 if(-not $env:URBAN_UPSTREAM_API_KEY){throw 'QWEN_API_KEY missing'}
 $cfg=Get-Content '.pi-agent/models.json' -Raw|ConvertFrom-Json
 $url=$cfg.providers.'aliyun-bailian'.baseUrl
 if($url -eq '$QWEN_API_BASE'){$url=$env:QWEN_API_BASE}
 $url=$url -replace '/api/v1/?$', '/compatible-mode/v1'
 $env:URBAN_TOKENIZER_DIR=''
 $id='qwen3.8-max';$provider='aliyun-bailian';$window='32768';$output='8192';$thinking='xhigh'
}else{
 $env:URBAN_UPSTREAM_API_KEY='local-dummy'
 $env:URBAN_TOKENIZER_DIR=Join-Path $root 'cache/qwen35-tokenizer'
 $url='http://127.0.0.1:11434/v1';$id='qwen3.5:9b-urban16k';$provider='local-ollama';$window='16384';$output='4096';$thinking='medium'
}
$out="evaluation/compaction_repair_20260917/$Round/$Model/$Condition"
if((Test-Path "$out/manifest.json") -and -not $Resume){throw 'Refuse to overwrite existing experiment'}
New-Item -ItemType Directory -Path $out -Force | Out-Null
$node='C:/Users/18029/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
$argsList=@('--import','tsx','scripts/long-workflow-session.ts','--out',$out,'--condition',$Condition,'--data-root','evaluation/case_reproduction_20260916/data','--model',$id,'--provider',$provider,'--base-url',$url,'--window',$window,'--output-tokens',$output,'--sampling','qwen-coding-compatible','--thinking',$thinking,'--deadline','1200')
$logPrefix='launcher'
if($Resume){$argsList+=@('--resume','true');$logPrefix='resume-'+(Get-Date -Format 'yyyyMMdd-HHmmss')}
$p=Start-Process $node -ArgumentList $argsList -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput "$root/$out/$logPrefix.stdout.log" -RedirectStandardError "$root/$out/$logPrefix.stderr.log" -PassThru
Write-Output "Started $Model $Condition PID=$($p.Id) out=$out"
