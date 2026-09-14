"""Read-only request-size and tool-output audit; never logs headers or credentials."""
import argparse, json, re
from collections import Counter
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);a=p.parse_args()
if not re.fullmatch(r'[a-zA-Z0-9_-]+',a.run_id):raise ValueError('Invalid run id')
base=Path(__file__).resolve().parents[1]/'evaluation'/a.run_id
result={}
for label in ['A','B']:
    rows=[];tools=[]
    for folder in sorted((base/label/'requests').glob('*')):
        if not (folder/'request.json').exists():continue
        request=json.loads((folder/'request.json').read_text(encoding='utf-8'))
        summary=json.loads((folder/'summary.json').read_text(encoding='utf-8')) if (folder/'summary.json').exists() else {}
        messages=request.get('messages',[])
        tc=[len(json.dumps(m.get('content'),ensure_ascii=False)) for m in messages if m.get('role')=='tool']
        row=dict(request=folder.name,turn=summary.get('turn'),kind='agent' if request.get('tools') else 'compaction',
                 max_tokens=request.get('max_tokens',request.get('max_completion_tokens')),
                 message_chars=len(json.dumps(messages,ensure_ascii=False)),tool_result_chars=sum(tc),
                 max_single_tool_chars=max(tc,default=0),tool_messages=len(tc),
                 schema_chars=len(json.dumps(request.get('tools',[]),ensure_ascii=False)),
                 http_status=summary.get('httpStatus'),finish_reason=summary.get('finishReason'),
                 usage=summary.get('usage'),error=summary.get('error') or summary.get('providerError'))
        rows.append(row)
    for turn in sorted((base/label/'turns').glob('*')):
        path=turn/'events.jsonl'
        if not path.exists():continue
        for line in path.read_text(encoding='utf-8').splitlines():
            e=json.loads(line)
            if e.get('type')!='tool_execution_end' or e.get('toolName')!='urban_python':continue
            output=e.get('result',{})
            details=output.get('details',{})
            inner=details.get('result',{}) if isinstance(details,dict) else {}
            text='\n'.join(b.get('text','') for b in output.get('content',[]) if b.get('type')=='text')
            tools.append(dict(turn=turn.name,call=e.get('toolCallId'),is_error=e.get('isError'),
                              method=details.get('method') if isinstance(details,dict) else None,
                              visible_chars=len(text),stdout_chars=len(inner.get('stdout_preview','')),
                              visible_has_report='feasibility.csv' in text,
                              saved_details_has_report='feasibility.csv' in str(inner),
                              visible_has_fit_reports='model_summary.csv' in text,
                              saved_details_has_fit_reports='model_summary.csv' in str(inner),
                              visible_truncated='truncated' in text.lower()))
    result[label]={'requests':rows,'python_outputs':tools,
                   'summary':{'request_count':len(rows),'http_statuses':dict(Counter(str(x['http_status']) for x in rows)),
                              'compaction_requests':sum(x['kind']=='compaction' for x in rows),
                              'max_tool_result_chars':max((x['tool_result_chars'] for x in rows),default=0),
                              'python_outputs_with_hidden_report':sum(x['saved_details_has_report'] and not x['visible_has_report'] for x in tools)}}
(base/'budget_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v['summary'] for k,v in result.items()},ensure_ascii=False,indent=2))
