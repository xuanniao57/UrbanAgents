"""Derive mechanical pilot outcomes without replacing raw harness labels or judging science."""
from pathlib import Path
import argparse,csv,json,re

parser=argparse.ArgumentParser();parser.add_argument('--run-id',default='long27_20260831');args=parser.parse_args()
if not re.fullmatch(r'[a-zA-Z0-9_-]+',args.run_id):raise ValueError('Invalid run ID')

root=Path(__file__).resolve().parents[1]
base=root/'evaluation'/args.run_id
audit=json.loads((root/'evaluation'/f'{args.run_id}_review/audit.json').read_text(encoding='utf-8'))
rows=[]
for session in audit['sessions']:
    label=session['source_session']
    for turn in session['turns_and_artifacts']:
        if 'turn' not in turn:continue  # fit-artifact audit entries are not human turns
        number=turn['turn'];folder=base/label/'turns'/f'{number:03d}'
        summary=json.loads((folder/'summary.json').read_text(encoding='utf-8'))
        final=(folder/'final_answer.txt').read_text(encoding='utf-8').strip()
        stops=[m.get('stopReason') for m in summary.get('assistantUsage',[])]
        failure=summary.get('failure') or ''
        if '600s' in failure or 'exceeded' in failure:
            effective='deadline_interruption'
        elif failure:
            effective='runtime_interruption'
        elif final and stops and stops[-1]=='stop':
            effective='answer_returned_with_recovery' if summary.get('assistantErrors') else 'answer_returned'
        elif final and stops and stops[-1]=='length':
            effective='truncated_answer'
        else:
            effective='no_final_answer'
        totals=turn['request_accounting']['totals']
        events=[json.loads(line) for line in (folder/'events.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
        unflagged=[]
        for event in events:
            if event.get('type')!='tool_execution_end':continue
            details=event.get('result',{}).get('details',{})
            exitcode=details.get('result',{}).get('exit_code') if isinstance(details,dict) else None
            if isinstance(exitcode,int) and exitcode!=0 and not event.get('isError'):
                unflagged.append(event.get('toolCallId'))
        rows.append(dict(condition=label,anonymous=session['anonymous_session'],turn=number,
            raw_outcome=summary.get('outcome'),effective_outcome=effective,
            duration_seconds=round(summary['durationMs']/1000,3),
            tool_calls=turn['tool_calls_started_or_observed'],tool_errors=turn['recorded_tool_errors'],
            unflagged_nonzero_script_exit=len(unflagged),
            internal_agent_starts=sum(e.get('type')=='agent_start' for e in events),
            compactions_started=turn['compaction']['start_events'],
            compactions_completed=turn['compaction']['completed_end_events'],
            compactions_failed=turn['compaction']['aborted_or_error_end_events'],
            prompt_tokens_observed=totals['prompt_tokens'],completion_tokens_observed=totals['completion_tokens'],
            tokens_observed=totals['total_tokens'],requests=totals['requests'],
            requests_with_usage=totals['requests_with_usage'],final_answer_characters=len(final),
            failure=failure))
output=base/'mechanical_metrics.csv'
with output.open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
states={}
for label in ['A','B']:
    state=json.loads((base/label/'research/research_state.json').read_text(encoding='utf-8'))
    fits=[]
    for path in (base/label/'research').rglob('run_manifest.json'):
        if json.loads(path.read_text(encoding='utf-8')).get('action')=='fit':fits.append(str(path.relative_to(base)))
    states[label]={'nodes':len(state['nodes']),'artifacts':len(state['artifacts']),
        'reviews':len(state['reviews']),'humanDecisions':len(state['humanDecisions']),
        'pendingHumanPatches':len(state.get('pendingHumanPatches',[])),
        'pending_patch_statuses':[p['status'] for p in state.get('pendingHumanPatches',[])],
        'fit_manifests':fits}
result={'note':'Observed provider usage excludes unreported/aborted usage; raw errors are not equivalent to task failure. No scientific scores generated.',
        'turns':rows,'final_state':states}
(base/'mechanical_metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
