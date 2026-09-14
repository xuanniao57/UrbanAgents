"""Safely unpack an owned pilot snapshot; refuse links and paths outside its label."""
import argparse,re,tarfile
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);p.add_argument('--condition',choices=['A','B'],required=True);a=p.parse_args()
if not re.fullmatch(r'[a-zA-Z0-9_-]+',a.run_id):raise ValueError('Invalid run ID')
base=Path(__file__).resolve().parents[1]/'evaluation'/a.run_id
target=(base/a.condition).resolve()
with tarfile.open(base/f'{a.condition}_collected.tar.gz') as tar:
    members=tar.getmembers()
    for m in members:
        path=(base/m.name).resolve()
        if not path.is_relative_to(target) or not (m.isdir() or m.isfile()):
            raise ValueError('Unsafe archive member')
    tar.extractall(base,members=members,filter='data')
print(f'Extracted {a.condition}: {len(members)} members')
