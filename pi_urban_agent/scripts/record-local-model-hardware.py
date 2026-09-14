"""Read-only model metadata and GPU telemetry for an existing local matrix."""
import json, subprocess, sys, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

root=Path(sys.argv[1]).resolve()
if not (root/'plan.json').exists():raise SystemExit('Expected existing matrix plan')
def api(path,data=None):
    req=urllib.request.Request('http://127.0.0.1:11434/api/'+path,
      data=json.dumps(data).encode() if data is not None else None,
      headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as response:return json.load(response)
tags={m['name']:m for m in api('tags')['models']}
models=[]
for size in ['0.8b','2b','4b','9b']:
    name=f'qwen3.5:{size}-urban8k';show=api('show',{'model':name})
    models.append({'name':name,'digest':tags[name]['digest'],'bytes':tags[name]['size'],
      'details':show.get('details'),'parameters':show.get('parameters'),
      'model_info':show.get('model_info'),'capabilities':show.get('capabilities')})
(root/'model_metadata.json').write_text(json.dumps({'ollama':api('version'),'models':models},ensure_ascii=False,indent=2),encoding='utf-8')
print('Recorded four installed model identities and parameters',flush=True)
start=time.monotonic()
with (root/'gpu_telemetry.jsonl').open('a',encoding='utf-8') as log:
    while time.monotonic()-start<3600:
        proc=subprocess.run(['nvidia-smi','--query-gpu=power.draw,utilization.gpu,memory.used,temperature.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        row={'time':datetime.now(timezone.utc).isoformat(),'returncode':proc.returncode,'power_w_util_pct_vram_mb_temp_c':proc.stdout.strip()}
        log.write(json.dumps(row)+'\n');log.flush()
        if (root/'complete.json').exists():break
        time.sleep(10)
print('GPU telemetry ended',flush=True)
