"""Local credential-safe queue/collection client for the paired AutoDL pilot."""
import argparse,json,re,shlex,sys,time
from collections import Counter
from pathlib import Path
from autodl_remote import connect

if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
p=argparse.ArgumentParser();p.add_argument('action',choices=['queue','status','errors','collect','stop','verify']);p.add_argument('--condition',choices=['A','B']);p.add_argument('--turn',type=int);p.add_argument('--message-file',type=Path)
p.add_argument('--run-id',default='long27_20260831');p.add_argument('--remote-root',default='/root/urban-long-20260831');p.add_argument('--wait',type=int,default=0);a=p.parse_args()
if not re.fullmatch(r'[a-zA-Z0-9_-]+',a.run_id) or not re.fullmatch(r'/root/[a-zA-Z0-9_-]+',a.remote_root):raise ValueError('Invalid run ID or remote root')
root=Path(__file__).resolve().parents[1];remote=f'{a.remote_root}/paper4_urban_svgagent/pi_urban_agent/evaluation/{a.run_id}'
c=connect(root.parent.parent/'.env')
try:
    with c.open_sftp() as s:
        if a.action=='verify':
            project=remote.rsplit('/evaluation/',1)[0]
            code="import json,hashlib;from pathlib import Path;p=Path("+repr(project)+");m=json.loads((p/'source_manifest.json').read_text());print(json.dumps({'files_checked':len(m),'mismatches':[k for k,v in m.items() if hashlib.sha256((p/k).read_bytes()).hexdigest()!=v]}))"
            _,stdout,stderr=c.exec_command('/root/autodl-tmp/urban_agent_eval/envs/urban-agent/bin/python -c '+shlex.quote(code),timeout=30)
            print(stdout.read().decode());print(stderr.read().decode())
        elif a.action=='queue':
            if not(a.condition and a.turn and a.message_file):raise ValueError('queue needs condition,turn,message-file')
            dest=f'{remote}/{a.condition}/inbox/{a.turn:03d}.json'
            try:s.stat(dest);raise RuntimeError('Refuse existing inbox entry')
            except FileNotFoundError:pass
            text=a.message_file.read_text(encoding='utf-8-sig')
            payload=json.dumps({'message':text},ensure_ascii=False)
            with s.open(dest+'.tmp','w') as f:f.write(payload)
            s.rename(dest+'.tmp',dest);print('queued',a.condition,a.turn)
        elif a.action=='stop':
            for label in ([a.condition] if a.condition else ['A','B']):
                with s.open(f'{remote}/{label}/STOP','w') as f:f.write('requested by orchestrator after evaluation')
            print('stop requested for session only; instance power unchanged')
        elif a.action=='errors':
            if not a.condition:raise ValueError('errors needs condition')
            code="import json\nerrors=[]\nfor line in open("+repr(f'{remote}/{a.condition}/pi_events.jsonl')+"):\n try:e=json.loads(line)\n except json.JSONDecodeError:continue\n if e.get('type')=='tool_execution_end' and e.get('isError'):errors.append({'tool':e.get('toolName'),'call':e.get('toolCallId'),'content':str(e.get('result',{}).get('content'))[:1400]})\nprint(json.dumps(errors[-8:],ensure_ascii=False,indent=2))"
            _,stdout,stderr=c.exec_command('/root/autodl-tmp/urban_agent_eval/envs/urban-agent/bin/python -c '+shlex.quote(code),timeout=30)
            print(stdout.read().decode());print(stderr.read().decode())
        elif a.action=='status':
            for label in ([a.condition] if a.condition else ['A','B']):
                # Parse remotely: downloading a growing JSONL via small SFTP reads is slow.
                code='''import json,time
from pathlib import Path
from collections import Counter
root=Path(ROOT)
deadline=time.monotonic()+WAIT
while True:
 status=json.loads((root/'status.json').read_text())
 if status.get('idle') or status.get('stopped') or time.monotonic()>=deadline:break
 time.sleep(2)
print(LABEL,json.dumps(status,ensure_ascii=False))
if status.get('turn',0):
 lines=(root/'timeline.jsonl').read_text().splitlines()
 for line in lines[-3:]:print(line[:1800])
 active=[]
 for line in lines:
  try:e=json.loads(line)
  except json.JSONDecodeError:continue
  if e.get('turn')==status['turn']:active.append(e)
 print('turn_counts',json.dumps({'tools':dict(Counter(e.get('toolName') for e in active if e.get('event')=='tool_execution_start')),'tool_errors':sum(e.get('event')=='tool_execution_end' and bool(e.get('isError')) for e in active),'compactions':dict(Counter(e.get('reason') for e in active if e.get('event')=='compaction_start'))}))
 if status.get('idle'):
  final=root/'turns'/f"{status['turn']:03d}"/'final_answer.txt'
  if final.exists():print(final.read_text())
'''.replace('ROOT',repr(f'{remote}/{label}')).replace('WAIT',str(max(0,min(45,a.wait)))).replace('LABEL',repr(label))
                _,stdout,stderr=c.exec_command('/root/autodl-tmp/urban_agent_eval/envs/urban-agent/bin/python -c '+shlex.quote(code),timeout=60)
                print(stdout.read().decode());print(stderr.read().decode())
        else:
            for label in ([a.condition] if a.condition else ['A','B']):
                archive=f'{a.remote_root}/{label}_collected.tar.gz'
                command=f'tar -czf {shlex.quote(archive)} -C {shlex.quote(remote)} {label}'
                _,stdout,stderr=c.exec_command(command,timeout=120)
                error=stderr.read().decode();code=stdout.channel.recv_exit_status()
                if code:raise RuntimeError(error)
                dest=root/'evaluation'/a.run_id/f'{label}_collected.tar.gz'
                s.get(archive,str(dest));print('collected',label,dest.stat().st_size)
finally:c.close()
