"""Bundle user-owned pilot evidence, excluding runtime authentication/config folders."""
from pathlib import Path
import argparse,hashlib,json,re,zipfile

parser=argparse.ArgumentParser();parser.add_argument('--run-id',default='long27_20260831');args=parser.parse_args()
if not re.fullmatch(r'[a-zA-Z0-9_-]+',args.run_id):raise ValueError('Invalid run ID')

root=Path(__file__).resolve().parents[1]
base=root/'evaluation'/args.run_id
review=root/'evaluation'/f'{args.run_id}_review'
dest=root/'evaluation'/('Urban_Pi_27B_longpilot_20260831.zip' if args.run_id=='long27_20260831' else f'Urban_Pi_27B_{args.run_id}.zip')
files={}
for folder,prefix in [(base,args.run_id),(review,f'{args.run_id}_review')]:
    for path in folder.rglob('*'):
        if not path.is_file():continue
        rel=path.relative_to(folder)
        if {'runtime','__pycache__'}.intersection(rel.parts):continue
        if path.name in {'auth.json','.env'} or path.name.endswith('_collected.tar.gz'):continue
        files[prefix+'/'+rel.as_posix()]=path
for name in ['long-workflow-session.ts','summarize-long-pilot.py','finalize-long-metrics.py',
             'control-long-pilot.py','autodl_remote.py','package-long-pilot.py','package-long-results.py','start-long-pair.sh','start-long-vllm.sh',
             'unpack-long-pilot.py','audit-long-budget.py','verify-long-artifacts.py']:
    files['supporting_scripts/'+name]=root/'scripts'/name
hashes={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in sorted(files.items())}
with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED) as z:
    for name,path in files.items():z.write(path,name)
    z.writestr('bundle_sha256.json',json.dumps(hashes,indent=2))
with zipfile.ZipFile(dest) as z:
    assert z.testzip() is None
print(json.dumps({'path':str(dest),'files':len(files),'bytes':dest.stat().st_size,
                  'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()}))
