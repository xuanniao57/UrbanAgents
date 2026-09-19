"""Read-only audit of local context tests; no LLM/SSH calls and no log rewriting."""
from pathlib import Path
from collections import Counter
import json

root = Path(__file__).resolve().parents[1]
base = root / 'evaluation/section43_20260831/runs'
records = []
for run in sorted(base.iterdir()):
    if not run.is_dir() or not ('_context_' in run.name or '_natural_' in run.name):
        continue
    events = []
    for line in (run / 'pi_events.jsonl').read_text(encoding='utf-8-sig').splitlines():
        events.append(json.loads(line))
    compact = run / 'compaction.json'
    manual = json.loads(compact.read_text(encoding='utf-8-sig')) if compact.exists() else None
    starts = [e for e in events if e.get('type') in ('auto_compaction_start', 'compaction_start')]
    ends = [e for e in events if e.get('type') in ('auto_compaction_end', 'compaction_end')]
    errors = [e for e in ends if e.get('errorMessage') or e.get('aborted')]
    records.append({'run': run.name, 'manual_ok': manual.get('success') if manual else None,
                    'compaction_starts': len(starts), 'compaction_ends': len(ends),
                    'reasons': dict(Counter(e.get('reason', 'unknown') for e in starts)),
                    'compaction_errors': [{k: e.get(k) for k in ('reason', 'aborted', 'errorMessage', 'willRetry')} for e in errors]})
print(json.dumps({'runs': len(records), 'manual_ok': sum(r['manual_ok'] is True for r in records),
                  'compaction_starts': sum(r['compaction_starts'] for r in records),
                  'compaction_ends': sum(r['compaction_ends'] for r in records),
                  'reason_counts': dict(sum((Counter(r['reasons']) for r in records), Counter())),
                  'compaction_error_count': sum(len(r['compaction_errors']) for r in records),
                  'records': records}, ensure_ascii=False, indent=2))
