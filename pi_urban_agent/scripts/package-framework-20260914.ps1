$ErrorActionPreference='Stop'
$runtime=Split-Path $PSScriptRoot -Parent
$dest=[IO.Path]::GetFullPath((Join-Path $runtime '../deliverables/framework27b_20260914'))
if(Test-Path $dest){throw 'Package destination exists; preserve it and choose a new version.'}
$target=Join-Path $dest 'pi_urban_agent'
New-Item -ItemType Directory -Path $target -Force | Out-Null
foreach($folder in @('src','python','tests','scripts')){
  Copy-Item -LiteralPath (Join-Path $runtime $folder) -Destination $target -Recurse
}
foreach($file in @('package.json','package-lock.json','tsconfig.json')){Copy-Item -LiteralPath (Join-Path $runtime $file) -Destination $target}
foreach($folder in @('.pi/extensions','long_case/data','evaluation/framework_ablation_v1','cache/qwen35-tokenizer')){
  $to=Join-Path $target $folder
  New-Item -ItemType Directory -Path (Split-Path $to -Parent) -Force | Out-Null
  Copy-Item -LiteralPath (Join-Path $runtime $folder) -Destination $to -Recurse
}
Copy-Item -LiteralPath (Join-Path $runtime 'long_case/data_contract.json') -Destination (Join-Path $target 'long_case/data_contract.json')
Copy-Item -LiteralPath (Join-Path $runtime 'evaluation/framework_ablation_v1/LAB27B_README_CN.md') -Destination (Join-Path $dest 'README_CN.md')
$files=Get-ChildItem -LiteralPath $dest -Recurse -File
$forbidden=$files | Where-Object { $_.Name -eq '.env' -or $_.Name -eq 'auth.json' -or $_.FullName -match 'node_modules' }
if($forbidden){throw 'Forbidden package file detected'}
$manifest=$files | ForEach-Object { [pscustomobject]@{path=$_.FullName.Substring($dest.Length+1);sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash;bytes=$_.Length} }
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $dest 'SHA256_MANIFEST.json') -Encoding UTF8
Compress-Archive -LiteralPath $dest -DestinationPath "$dest.zip"
Get-Item "$dest.zip" | Select-Object FullName,Length
