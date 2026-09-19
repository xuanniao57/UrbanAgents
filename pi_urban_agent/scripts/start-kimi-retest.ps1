$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $root
foreach($line in Get-Content -LiteralPath (Join-Path $root '../../.env')){
 if($line -match '^\s*(?:OPENCODE_API_KEY|opencode_APIkey)\s*=\s*(.+?)\s*$'){$env:URBAN_UPSTREAM_API_KEY=$Matches[1].Trim().Trim('"').Trim("'")}
}
if(-not $env:URBAN_UPSTREAM_API_KEY){throw 'OpenCode credential missing'}
$env:HTTP_PROXY='';$env:HTTPS_PROXY='';$env:ALL_PROXY='';$env:NO_PROXY='*';$env:NODE_USE_ENV_PROXY='0'
$env:URBAN_PI_PYTHON=[IO.Path]::GetFullPath((Join-Path $root '../.venv-section4/Scripts/python.exe'))
# Do not use the Qwen tokenizer to claim exact Kimi token counts.
$env:URBAN_TOKENIZER_DIR=''
$out='evaluation/raw_api_20260916/kimi-k3/fixes_r01'
if(Test-Path "$out/manifest.json"){throw 'Refuse to overwrite an existing run'}
New-Item -ItemType Directory -Path "$out/inbox" -Force | Out-Null
Copy-Item -LiteralPath 'evaluation/raw_api_20260915/qwen3.5-plus/raw_full_r01/inbox/001.json' -Destination "$out/inbox/001.json"
Copy-Item -LiteralPath 'evaluation/raw_local_20260915/4b/thinking_on_20260916_r01/inbox/002.json' -Destination "$out/inbox/002.json"
$cfg=Get-Content '.pi-agent/models.json' -Raw|ConvertFrom-Json
$url=$cfg.providers.'opencode-zen'.baseUrl
$node='C:/Users/18029/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
$p=Start-Process $node -ArgumentList @('--import','tsx','scripts/long-workflow-session.ts','--out',$out,'--condition','urban_full_v2','--data-root','raw_case/data','--model','kimi-k3','--provider','opencode-zen','--base-url',$url,'--window','32768','--output-tokens','8192','--sampling','qwen-coding-compatible','--thinking','low','--deadline','600') -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput "$root/$out/launcher.stdout.log" -RedirectStandardError "$root/$out/launcher.stderr.log" -PassThru
$started=Get-Date
while(-not $p.HasExited){
 if(Test-Path "$out/status.json"){
  try{$s=Get-Content "$out/status.json" -Raw|ConvertFrom-Json}catch{$s=$null}
  if($s -and $s.turn -ge 2){[IO.File]::WriteAllText((Join-Path $root "$out/STOP"),'Stop after bounded second turn.')}
 }
 if(((Get-Date)-$started).TotalMinutes -gt 25){& taskkill /PID $p.Id /T /F; throw 'Kimi supervisor timeout'}
 Start-Sleep -Seconds 2
 $p.Refresh()
}
Write-Output "Kimi bounded rerun finished. Exit=$($p.ExitCode); results=$out"
