"""Read-only run audit; writes derived tables, never edits raw trajectories."""
import csv,json,sys,hashlib
from pathlib import Path
from collections import Counter

root=Path(sys.argv[1]).resolve()
def read(p,default=None):
    try:return json.loads(p.read_text(encoding='utf-8-sig'))
    except (FileNotFoundError,json.JSONDecodeError):return default
def lines(p):
    if not p.exists():return []
    result=[]
    for line in p.read_text(encoding='utf-8-sig').splitlines():
        try:result.append(json.loads(line))
        except json.JSONDecodeError:pass
    return result
plan=read(root/'plan.json',{})
runtime=Path(__file__).resolve().parents[1]
hash_errors=[p for p,h in plan.get('sourceHashes',{}).items() if hashlib.sha256((runtime/p).read_bytes()).hexdigest()!=h]
rows=[];details=[]
for size in plan.get('sizes',[]):
  for condition in plan['conditions']:
    run=root/f'{size}_{condition}'
    if not (run/'manifest.json').exists():continue
    events=lines(run/'pi_events.jsonl');budgets=lines(run/'request-budget/events.jsonl')
    turns=[read(p) for p in sorted((run/'turns').glob('*/summary.json'))]
    requests=[read(p) for p in sorted((run/'requests').glob('*/summary.json'))]
    requests=[r for r in requests if r]
    wire=[]
    for folder in sorted((run/'requests').glob('*')):
      r=read(folder/'request.json',{}); s=read(folder/'summary.json',{})
      if not r:continue
      messages=r.get('messages',[])
      summary_call=any(str(m.get('content','')).startswith('You are a context summarization assistant.') for m in messages if m.get('role')=='system')
      prompt_file=run/'turns'/str(s.get('turn',0)).zfill(3)/'prompt.txt'
      human=prompt_file.read_text(encoding='utf-8') if prompt_file.exists() else ''
      def wire_text(m):
        c=m.get('content','')
        return c if isinstance(c,str) else '\n'.join(b.get('text','') for b in (c or []) if b.get('type')=='text')
      wire.append({'id':folder.name,'kind':'summary' if summary_call else 'agent',
        'latest_human_verbatim':any(human in wire_text(m) for m in messages if m.get('role')=='user') if human else None})
    answers=[(p.parent.name,p.read_text(encoding='utf-8')) for p in sorted((run/'turns').glob('*/final_answer.txt'))]
    tools=[e for e in events if e.get('type')=='tool_execution_start']
    ends=[e for e in events if e.get('type')=='tool_execution_end']
    success_ids={e['toolCallId'] for e in ends if not e.get('isError')}
    reads=[t for t in tools if t['toolCallId'] in success_ids and (t.get('toolName')=='urban_read' or t.get('toolName')=='urban_python' and t.get('args',{}).get('method') in {'inspect_csv','inspect_json','inspect_text','list_directory'})]
    model_reads=[r for r in reads if str(r.get('args',{}).get('path') or r.get('args',{}).get('arguments',{}).get('path','')).endswith('model_summary.csv')]
    archive_reads=[r for r in reads if 'request-budget' in str(r.get('args',{}).get('path',''))]
    manifests=[];ols_scales=set();gwr=0;file_hash_errors=[]
    for p in run.rglob('run_manifest.json'):
      m=read(p,{})
      if m.get('action')!='fit' or m.get('status')!='completed':continue
      manifests.append(str(p))
      table=p.parent/'model_summary.csv'
      if table.exists():
        for r in csv.DictReader(table.open(encoding='utf-8-sig')):
          if r.get('model')=='ols':ols_scales.add(r['scale_m'])
          elif r.get('model','').startswith('gwr'):gwr+=1
      for name,h in m.get('output_sha256',{}).items():
        f=p.parent/name
        if not f.exists() or hashlib.sha256(f.read_bytes()).hexdigest()!=h:file_hash_errors.append(str(f))
    state_paths=list(run.rglob('research_state.json'))
    for e in ends:
      if e.get('toolName')=='urban_initialize' and not e.get('isError'):
        actual=e.get('result',{}).get('details',{}).get('runDir')
        if actual:
          candidate=Path(actual)/'research_state.json'
          if candidate.exists() and candidate not in state_paths:state_paths.append(candidate)
    states=[read(p,{}) for p in state_paths]
    state=states[-1] if states else {}
    turn_failures=[t.get('failure') for t in turns if t.get('failure')]
    local_budget_errors=[e for e in events if e.get('type')=='message_end' and 'Budget configuration:' in str(e.get('message',{}).get('errorMessage',''))]
    row=dict(model=size,condition=condition,turns=len(turns),final_text_turns=sum(bool(a.strip()) for _,a in answers),
      ols_scales=len(ols_scales),gwr_fits=gwr,successful_file_reads=len(reads),model_table_reads=len(model_reads),successful_archive_reads=len(archive_reads),
      native_compactions=sum(e.get('type')=='compaction_end' and bool(e.get('result')) and not e.get('aborted') and not e.get('errorMessage') for e in events),
      native_compaction_errors=sum(e.get('type')=='compaction_end' and bool(e.get('errorMessage')) for e in events),
      preflight_compactions=sum(b.get('event')=='preflight_compaction' for b in budgets),
      summary_chunks=sum(b.get('event')=='summary_chunk' for b in budgets),
      http_errors=sum((r.get('httpStatus') or 0)>=400 for r in requests),
      requests=len(requests),requests_with_usage=sum(bool(r.get('usage')) for r in requests),
      agent_requests=sum(w['kind']=='agent' for w in wire),
      latest_human_verbatim_missing=sum(w['kind']=='agent' and w['latest_human_verbatim'] is False for w in wire),
      wire_requests_without_turn_metadata=sum(w['latest_human_verbatim'] is None for w in wire),
      local_budget_error_events=len(local_budget_errors),
      one_token_requests=sum(r.get('maxTokens')==1 for r in requests),
      over_budget_sent=sum(r.get('usage',{}).get('prompt_tokens',0)+r.get('maxTokens',0)>8192 for r in requests if r.get('usage')),
      preflight_refusals=sum(b.get('event')=='request_check' and b.get('inputTokens',0)>b.get('input',0) for b in budgets),
      tool_attempts=len(tools),tool_errors=sum(bool(e.get('isError')) for e in ends),
      outer_stops=sum(bool(t.get('budgetStop')) for t in turns),
      tree_nodes=sum(len(s.get('nodes',{})) for s in states),artifacts=sum(len(s.get('artifacts',{})) for s in states),human_decisions=sum(len(s.get('humanDecisions',[])) for s in states),
      initialized_stores=len(states),expected_store_exists=(run/'research/research_state.json').exists(),
      acceptance_timeouts=sum('Prompt acceptance exceeded' in f for f in turn_failures),
      prompt_tokens=sum(r.get('usage',{}).get('prompt_tokens',0) for r in requests),completion_tokens=sum(r.get('usage',{}).get('completion_tokens',0) for r in requests),
      duration_seconds=round(sum(t.get('durationMs',0) for t in turns)/1000,1),file_hash_errors=len(file_hash_errors),finished=(run/'runner_result.json').exists())
    rows.append(row)
    details.append(dict(**row,answers=dict(answers),decisions=state.get('humanDecisions',[]),state_paths=[str(p) for p in state_paths],turn_failures=turn_failures,wire_audit=wire,local_budget_errors=local_budget_errors,manifests=manifests,file_hash_error_paths=file_hash_errors,
      errors=Counter(str(e.get('result',{}).get('content'))[:500] for e in ends if e.get('isError'))))
if rows:
  with (root/'run_audit.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(root/'run_audit.json').write_text(json.dumps({'source_hash_mismatches':hash_errors,'runs':details},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'source_hash_mismatches':hash_errors,'runs':rows},ensure_ascii=False,indent=2))
