"""Inspect the collected third human turn without model calls or state mutations."""
from pathlib import Path
import json

root = Path(__file__).resolve().parents[1]
base = root / 'evaluation/long27_20260831'
prompt = (base / 'messages/B_003.txt').read_text(encoding='utf-8-sig').strip()
state = json.loads((base / 'B/research/research_state.json').read_text(encoding='utf-8-sig'))
patch = state['pendingHumanPatches'][-1]
rows = []
for folder in sorted((base / 'B/requests').iterdir()):
    if int(folder.name) < 69:
        continue
    payload = json.loads((folder / 'request.json').read_text(encoding='utf-8-sig'))
    text = json.dumps(payload.get('messages', []), ensure_ascii=False)
    has_tools = bool(payload.get('tools'))
    rows.append({'request': folder.name, 'kind': 'agent' if has_tools else 'summary',
                 'latest_human_verbatim': prompt in text,
                 'ols_authorization_phrase': '现在授权先执行OLS' in text,
                 'old_plan_only': 'Only establish' in text or 'only establish' in text})
print(json.dumps({'stored_patch_status': patch['status'], 'stored_targets': patch['targetBranchIds'],
                  'stored_digest_equals_full_current_message': patch['rawTextDigest'] == prompt,
                  'stored_message_chars': len(prompt),
                  'interpretation': 'Verbatim/phrase checks are lexical only, not semantic scores. Request 80 retains an English OLS authorization in its split-turn summary despite both lexical flags being false; request 85 loses that update. Inspect the full summaries before attribution.',
                  'rows': rows}, ensure_ascii=False, indent=2))
