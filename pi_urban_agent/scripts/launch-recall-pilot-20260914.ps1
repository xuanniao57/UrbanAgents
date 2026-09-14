param([ValidateSet('local','api')][string]$Lane='local')
$ErrorActionPreference='Stop'
$runtime=Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $runtime
$node='C:/Users/18029/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
$env:URBAN_PI_PYTHON=[IO.Path]::GetFullPath((Join-Path $runtime '../.venv-section4/Scripts/python.exe'))
$env:URBAN_TOKENIZER_DIR=Join-Path $runtime 'cache/qwen35-tokenizer'
$env:HTTP_PROXY='';$env:HTTPS_PROXY='';$env:ALL_PROXY='';$env:NO_PROXY='*';$env:NODE_USE_ENV_PROXY='0'
$out=Join-Path $runtime "evaluation/recall_repair_pilot_20260914/runs/$Lane"
New-Item -ItemType Directory -Path $out -Force|Out-Null
$hashes=foreach($f in @('src/core/request-budget.mjs','src/pi-extension.ts','scripts/long-workflow-session.ts','evaluation/recall_repair_pilot_20260914/protocol.json')){[pscustomobject]@{file=$f;sha256=(Get-FileHash $f).Hash}}
$hashes|ConvertTo-Json|Set-Content (Join-Path $out 'source_hashes.json') -Encoding UTF8
if($Lane -eq 'local'){
  $models=@('qwen3.5:4b-urban8k');$provider='local-ollama';$url='http://127.0.0.1:11434/v1'
  & nvidia-smi|Out-File (Join-Path $out 'hardware.txt')
}else{
  foreach($line in Get-Content -LiteralPath (Join-Path $runtime '../../.env')){
    if($line -match '^\s*QWEN_API_KEY\s*=\s*(.+?)\s*$'){$env:URBAN_UPSTREAM_API_KEY=$Matches[1].Trim().Trim('"').Trim("'")}
    if($line -match '^\s*QWEN_API_BASE\s*=\s*(.+?)\s*$'){$env:QWEN_API_BASE=$Matches[1].Trim().Trim('"').Trim("'")}
  }
  if(-not $env:URBAN_UPSTREAM_API_KEY){throw 'QWEN_API_KEY missing'}
  $cfg=Get-Content '.pi-agent/models.json' -Raw|ConvertFrom-Json
  $url=$cfg.providers.'aliyun-bailian'.baseUrl
  if($url -eq '$QWEN_API_BASE'){$url=$env:QWEN_API_BASE}
  $url=$url -replace '/api/v1/?$', '/compatible-mode/v1'
  Resolve-DnsName ([uri]$url).Host -Type A | Where-Object IPAddress | ForEach-Object {
    Find-NetRoute -RemoteIPAddress $_.IPAddress | Select-Object InterfaceAlias,NextHop,DestinationPrefix
  } | ConvertTo-Json | Set-Content (Join-Path $out 'direct_route.json') -Encoding UTF8
  $provider='aliyun-bailian';$models=@('qwen3.8-max','qwen3.5-plus')
  Add-Type -AssemblyName System.Net.Http
  $handler=New-Object System.Net.Http.HttpClientHandler
  $handler.UseProxy=$false
  $client=New-Object System.Net.Http.HttpClient($handler)
  $client.Timeout=[TimeSpan]::FromSeconds(45)
  $client.DefaultRequestHeaders.Authorization=New-Object System.Net.Http.Headers.AuthenticationHeaderValue('Bearer',$env:URBAN_UPSTREAM_API_KEY)
}
foreach($model in $models){
  if($Lane -eq 'api'){
    $body=@{model=$model;messages=@(@{role='user';content='Reply OK.'});max_tokens=16;stream=$false;enable_thinking=$false}|ConvertTo-Json -Depth 5
    $content=New-Object System.Net.Http.StringContent($body,[Text.Encoding]::UTF8,'application/json')
    $res=$client.PostAsync("$($url.TrimEnd('/'))/chat/completions",$content).GetAwaiter().GetResult()
    $code=[int]$res.StatusCode
    Write-Output "Direct HTTP preflight model=$model status=$code UseProxy=false"
    if(-not $res.IsSuccessStatusCode){continue}
  }
  $modelOut=Join-Path $out ($model -replace '[^A-Za-z0-9_.-]','_')
  & $node --import tsx scripts/run-framework-ablation.ts --protocol evaluation/recall_repair_pilot_20260914/protocol.json --model $model --provider $provider --base-url $url --data-root long_case/data --output-root $modelOut --context-window 8192 --max-output-tokens 2048 --deadline 300 --repeats 1 --seed 42
  if($LASTEXITCODE -ne 0){throw "Pilot runner failed: $model"}
}
if($Lane -eq 'local'){
  Invoke-RestMethod 'http://127.0.0.1:11434/api/generate' -Method Post -ContentType 'application/json' -Body '{"model":"qwen3.5:4b-urban8k","keep_alive":0}'|Out-Null
}else{$client.Dispose()}
