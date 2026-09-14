"""Verify collected scientific outputs and compare computed results, without fitting."""
import argparse,csv,hashlib,json,re,tarfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);a=p.parse_args()
if not re.fullmatch(r'[a-zA-Z0-9_-]+',a.run_id):raise ValueError('Invalid run id')
root=Path(__file__).resolve().parents[1];base=root/'evaluation'/a.run_id
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
source_manifest=json.loads((base/'source_manifest.json').read_text(encoding='utf-8'))
frozen={}
with tarfile.open(base/'urban_long_pilot.tar.gz','r:gz') as archive:
    for name in source_manifest:
        member=archive.getmember('pi_urban_agent/'+name)
        if not member.isfile():raise ValueError('Expected regular source file')
        frozen[name]=hashlib.sha256(archive.extractfile(member).read()).hexdigest()
if frozen!=source_manifest:raise ValueError('Frozen archive differs from source manifest')
result={};comparisons={}
for label in ['A','B']:
    records=[]
    for path in sorted((base/label/'research').rglob('run_manifest.json')):
        m=json.loads(path.read_text(encoding='utf-8'));errors=[]
        for name,digest in m.get('output_sha256',{}).items():
            target=(path.parent/name).resolve()
            if not target.is_relative_to(path.parent.resolve()):raise ValueError('Invalid output path')
            if not target.exists() or sha(target)!=digest:errors.append('output: '+name)
        for name,digest in m.get('input_sha256',{}).items():
            if '/long_case/' not in name:raise ValueError('Unrecognized input root')
            relative='long_case/'+name.split('/long_case/',1)[1]
            if frozen.get(relative)!=digest:errors.append('input: '+relative)
        if m.get('code_sha256')!=frozen['long_case/analysis.py']:errors.append('analysis code')
        rows=list(csv.DictReader((path.parent/'model_summary.csv').open(encoding='utf-8-sig',newline='')))
        records.append({'manifest':str(path.relative_to(base)),'status':m.get('status'),'validation':m.get('validation'),
                        'runtime_seconds':m.get('runtime_seconds'),'features':m.get('features'),
                        'input_files_checked':len(m.get('input_sha256',{})),
                        'output_files_checked':len(m.get('output_sha256',{})),'mismatches':errors,
                        'models':[{'scale_m':r['scale_m'],'model':r['model'],'scope':r['scope'],'n':r['n'],'r2':r['r2']} for r in rows]})
        comparisons[label]=m.get('output_sha256',{})
    result[label]=records
if all(k in comparisons for k in ['A','B']):
    result['paired_output_hash_equality']={k:comparisons['A'][k]==comparisons['B'].get(k) for k in comparisons['A']}
(base/'scientific_artifact_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
