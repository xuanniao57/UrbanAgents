"""Package allowlisted source and corrected aggregates; never credentials or old scores."""
from pathlib import Path
import argparse,hashlib,json,re,tarfile

parser=argparse.ArgumentParser()
parser.add_argument('--run-id',default='long27_20260831')
parser.add_argument('--remote-root',default='/root/urban-long-20260831')
args=parser.parse_args()
if not re.fullmatch(r'[a-zA-Z0-9_-]+',args.run_id) or not re.fullmatch(r'/root/[a-zA-Z0-9_-]+',args.remote_root):raise ValueError('Invalid run ID or remote root')

root=Path(__file__).resolve().parents[1]
source=root.parent/'experiments/case2_multiscale_aoi_corrected_20260830/outputs'
dest=root/'evaluation'/args.run_id
dest.mkdir(parents=True,exist_ok=True)
files={}
for folder in ['src','.pi/extensions','python','long_case']:
    for p in (root/folder).rglob('*'):
        if p.is_file() and p.suffix in {'.ts','.py','.json','.md'} and not {'__pycache__','_validation'}.intersection(p.parts) and p.name != 'test_analysis.py':
            files[p.relative_to(root).as_posix()]=p
for name in ['package.json','package-lock.json','tsconfig.json','scripts/apply-pi-budget-compat-patch.ts','scripts/long-workflow-session.ts']:
    files[name]=root/name
files[f'evaluation/{args.run_id}/PROTOCOL_CN.md']=dest/'PROTOCOL_CN.md'
template_path=dest/'initial_message_template.txt'
if not template_path.exists():
    template_path.write_bytes((root/'evaluation/long27_20260831/initial_message_template.txt').read_bytes())
files[f'evaluation/{args.run_id}/initial_message_template.txt']=template_path
for name in ['JUDGE_RUBRIC.md','CHANGESET.md']:
    if (dest/name).exists():files[f'evaluation/{args.run_id}/{name}']=dest/name
for pattern in ['model_ready_*m.csv','grid_supports_*m.geojson','shared_macro_fold_assignments.csv','event_aoi_membership_audit.csv','scale_coverage_ledger.csv']:
    for p in source.glob(pattern):files['long_case/data/'+p.name]=p
manifest={name:hashlib.sha256(p.read_bytes()).hexdigest() for name,p in sorted(files.items())}
(dest/'source_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
files['source_manifest.json']=dest/'source_manifest.json'
with tarfile.open(dest/'urban_long_pilot.tar.gz','w:gz') as tar:
    for name,p in files.items():tar.add(p,arcname='pi_urban_agent/'+name)
print(json.dumps({'files':len(files),'bytes':(dest/'urban_long_pilot.tar.gz').stat().st_size,'archive':str(dest/'urban_long_pilot.tar.gz')}))
remote=f'{args.remote_root}/paper4_urban_svgagent/pi_urban_agent'
template=(dest/'initial_message_template.txt').read_text(encoding='utf-8')
messages=dest/'messages';messages.mkdir(exist_ok=True)
for label in ['A','B']:
    (messages/f'{label}_001.txt').write_text(template.replace('{{RUN_DIR}}',f'{remote}/evaluation/{args.run_id}/{label}/research').replace('{{CASE_DIR}}',f'{remote}/long_case'),encoding='utf-8')
