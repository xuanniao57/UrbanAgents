param([ValidateSet('local','qwen3.5-plus','qwen3.8-max')][string]$Lane='local')
$ErrorActionPreference='Stop'
$runtime=Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $runtime
$node='C:/Users/18029/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
$env:URBAN_PI_PYTHON=[IO.Path]::GetFullPath((Join-Path $runtime '../.venv-section4/Scripts/python.exe'))
$env:URBAN_TOKENIZER_DIR=Join-Path $runtime 'cache/qwen35-tokenizer'
$env:HTTP_PROXY=''; $env:HTTPS_PROXY=''; $env:ALL_PROXY=''; $env:NO_PROXY='*'
$out=Join-Path $runtime "evaluation/framework_full_20260914/$Lane"
New-Item -ItemType Directory -Path $out -Force | Out-Null
& nvidia-smi | Out-File (Join-Path $out 'hardware.txt')
if ($Lane -eq 'local') {
  $models=@('qwen3.5:4b-urban8k','qwen3.5:9b-urban8k','qwen3.5:0.8b-urban8k','qwen3.5:2b-urban8k')
  $provider='local-ollama'; $url='http://127.0.0.1:11434/v1'
} else {
  foreach($line in Get-Content -LiteralPath (Join-Path $runtime '../../.env')) {
    if($line -match '^\s*QWEN_API_KEY\s*=\s*(.+?)\s*$') {$env:URBAN_UPSTREAM_API_KEY=$Matches[1].Trim().Trim('"').Trim("'")}
    if($line -match '^\s*QWEN_API_BASE\s*=\s*(.+?)\s*$') {$env:QWEN_API_BASE=$Matches[1].Trim().Trim('"').Trim("'")}
  }
  if(-not $env:URBAN_UPSTREAM_API_KEY){throw 'QWEN_API_KEY missing'}
  $cfg=Get-Content '.pi-agent/models.json' -Raw | ConvertFrom-Json
  $url=$cfg.providers.'aliyun-bailian'.baseUrl
  if($url -eq '$QWEN_API_BASE'){$url=$env:QWEN_API_BASE}
  $url=$url -replace '/api/v1/?$', '/compatible-mode/v1'
  $provider='aliyun-bailian'; $models=@($Lane)
}
foreach($model in $models){
  if($Lane -eq 'local'){
    $loaded=Invoke-RestMethod 'http://127.0.0.1:11434/api/ps'
    foreach($m in $loaded.models){Invoke-RestMethod 'http://127.0.0.1:11434/api/generate' -Method Post -ContentType 'application/json' -Body (@{model=$m.name;keep_alive=0}|ConvertTo-Json) | Out-Null}
  }
  $modelOut=Join-Path $out ($model -replace '[^A-Za-z0-9_.-]','_')
  & $node --import tsx scripts/run-framework-ablation.ts --model $model --provider $provider --base-url $url --data-root long_case/data --output-root $modelOut --context-window 8192 --max-output-tokens 2048 --deadline 600 --repeats 3 --seed 42
  if($LASTEXITCODE -ne 0){throw "Matrix runner failed for $model"}
}
