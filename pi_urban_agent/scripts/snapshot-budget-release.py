"""Freeze source, tokenizer and input fingerprints without credentials or model weights."""
import hashlib,json,sys,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
dest=Path(sys.argv[1]).resolve();dest.mkdir(parents=True,exist_ok=True)
files=[]
for folder in ['src','python','.pi/extensions','tests']:
    files.extend(p for p in (root/folder).rglob('*') if p.is_file() and p.suffix in {'.ts','.mjs','.py'} and '__pycache__' not in p.parts)
for name in ['package.json','package-lock.json','tsconfig.json','scripts/apply-pi-budget-compat-patch.ts','scripts/long-workflow-session.ts','scripts/run-local-long-budget.ts','scripts/summarize-local-long-budget.py','scripts/snapshot-budget-release.py','scripts/build-local-budget-report.py','scripts/record-local-model-hardware.py','scripts/replay-request-budget.ts','long_case/analysis.py','long_case/tool_manifest.json','long_case/data_contract.json']:
    files.append(root/name)
# Inputs only: never package model-created research state accidentally placed here.
files.extend(p for p in (root/'long_case/data').iterdir() if p.is_file() and p.suffix.lower() in {'.csv','.geojson'})
files.extend(p for p in (root/'cache/qwen35-tokenizer').iterdir() if p.is_file())
manifest={str(p.relative_to(root)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files))}
(dest/'release_hashes.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
with zipfile.ZipFile(dest/'source_and_test_data.zip','w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(set(files)):z.write(p,p.relative_to(root))
    z.write(dest/'release_hashes.json','release_hashes.json')
print(json.dumps({'files':len(manifest),'zip_bytes':(dest/'source_and_test_data.zip').stat().st_size}))
