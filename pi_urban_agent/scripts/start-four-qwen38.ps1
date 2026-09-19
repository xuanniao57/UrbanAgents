param([ValidateSet('urban_full_v2','urban_single_v2','urban_no_memory_v2','pi_native_v2')][string]$Condition)
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
foreach($key in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')){[Environment]::SetEnvironmentVariable($key,'','Process')}
$env:NO_PROXY='*';$env:NODE_USE_ENV_PROXY='0'
$env:URBAN_PI_PYTHON=[IO.Path]::GetFullPath((Join-Path $root '../.venv-section4/Scripts/python.exe'))
$env:URBAN_TOKENIZER_DIR=''
$env:URBAN_SESSION_REQUEST_LIMIT='128'
$out="evaluation/four_framework_qwen38_20260917/runs/$Condition"
if(Test-Path "$out/manifest.json"){throw 'Refuse to overwrite existing experiment'}
New-Item -ItemType Directory -Path $out -Force | Out-Null
$node='C:/Users/18029/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
$p=Start-Process $node -ArgumentList @('--import','tsx','scripts/long-workflow-session.ts','--out',$out,'--condition',$Condition,'--data-root','evaluation/case_reproduction_20260916/data','--model','qwen3.8-max','--provider','aliyun-bailian','--base-url',$url,'--window','32768','--output-tokens','8192','--sampling','qwen-coding-compatible','--thinking','xhigh','--deadline','1200') -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput "$root/$out/launcher.stdout.log" -RedirectStandardError "$root/$out/launcher.stderr.log" -PassThru
Write-Output "Started $Condition PID=$($p.Id)"
$started=Get-Date
while(-not $p.HasExited){
 if(((Get-Date)-$started).TotalMinutes -ge 90){
  New-Item -ItemType File -Path "$out/STOP" -Force | Out-Null
  if(-not $p.WaitForExit(15000)){& taskkill /PID $p.Id /T /F | Out-Null}
  break
 }
 Start-Sleep -Seconds 3
 $p.Refresh()
}
