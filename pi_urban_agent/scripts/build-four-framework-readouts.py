"""Export visible human/assistant/tool trajectories, excluding model reasoning."""
from pathlib import Path
import json, html
ROOT=Path(__file__).resolve().parents[1]
CONDITIONS={'urban_full_v2':'完整 Urban','urban_single_v2':'去多 Agent','urban_no_memory_v2':'去外部记忆','pi_native_v2':'Pi 基线'}
EXPERIMENTS=['four_framework_kimi_20260917','four_framework_qwen38_20260917']
def load(p):
    try:return json.loads(p.read_text(encoding='utf-8-sig'))
    except (OSError,ValueError):return {}
def text(p):
    return p.read_text(encoding='utf-8-sig') if p.exists() else ''
links=[]
for exp in EXPERIMENTS:
    base=ROOT/'evaluation'/exp
    base.mkdir(exist_ok=True)
    for condition,label in CONDITIONS.items():
        run=base/'runs'/condition
        parts=[f'# {label} — {exp}', '\n只呈现人类输入、最终答复和可见工具操作；不包含隐藏推理。\n']
        state=load(run/'status.json')
        parts+=['## 当前状态', '```json\n'+json.dumps(state,ensure_ascii=False,indent=2)+'\n```']
        turns=sorted((run/'turns').glob('[0-9]*')) if (run/'turns').exists() else []
        for turn in turns:
            parts += [f'## 第 {int(turn.name)} 轮', '### 人类输入',text(turn/'prompt.txt') or load(run/'inbox'/f'{turn.name}.json').get('message',''), '### Agent 最终答复',text(turn/'final_answer.txt') or '本轮尚未完成。']
            parts += ['### 可见工具轨迹']
            for line in text(turn/'events.jsonl').splitlines():
                try:e=json.loads(line)
                except ValueError:continue
                if e.get('type')=='tool_execution_start':
                    parts += [f"\n工具：{e.get('toolName','')} · {e.get('toolCallId','')}\n",'```json\n'+json.dumps(e.get('args',{}),ensure_ascii=False,indent=2)[:8000]+'\n```']
                elif e.get('type')=='tool_execution_end':
                    result=e.get('result',{})
                    content='\n'.join(c.get('text','') for c in result.get('content',[]) if c.get('type')=='text') if isinstance(result,dict) else str(result)
                    parts += [f"返回（错误={e.get('isError',False)}）：\n",'```text\n'+content[:10000]+('\n[阅读副本截短；原始工具事件完整保留]' if len(content)>10000 else '')+'\n```']
            parts+=['### 本轮统计','```json\n'+json.dumps(load(turn/'summary.json'),ensure_ascii=False,indent=2)+'\n```']
        if not turns:parts+=['实验尚未产生可读回合；运行期间可重新执行生成脚本刷新此副本。']
        parts+=['## 测试员记录',text(run/'tester_notes.md') or '测试员尚未提交记录。']
        p=base/f'READOUT_{condition}.md';p.write_text('\n\n'.join(parts),encoding='utf-8')
        links.append((exp,label,p,run))
index=['# 四框架实验：答复与轨迹入口','\n先读 READOUT：每轮按“人类输入 → Agent 答复 → 工具操作 → 统计”排列，不必翻会话 JSONL。阅读副本按生成时状态截取，不是实时页面。\n']
for exp in EXPERIMENTS:
    index += [f'## {exp}']
    for e,label,p,run in links:
        if e==exp:index += [f'- [{label}：对话与工具轨迹]({p.as_posix()}) · [测试员记录]({(run/"tester_notes.md").as_posix()})']
index += ['## 原始文件怎么读','- `runs/<条件>/inbox/NNN.json`：逐字人类消息。','- `turns/NNN/final_answer.txt`：对应 Agent 最终答复。','- `turns/NNN/events.jsonl`：原始事件；优先使用上面的已筛选阅读副本，避免混入隐藏推理。','- `turns/NNN/summary.json`：本轮耗时、用量和错误等统计。','- `research/research_state.json`：研究树状态（具有研究记忆的条件）。','- `workspace/outputs/`：真实表格与其他产物。','- `tester_notes.md`：测试员的追问理由、停止依据与遗留问题。','\n刷新阅读副本：在 pi_urban_agent 目录运行 `python scripts/build-four-framework-readouts.py`。']
(ROOT/'evaluation'/'FOUR_FRAMEWORK_TRACE_INDEX.md').write_text('\n\n'.join(index),encoding='utf-8')
print(ROOT/'evaluation'/'FOUR_FRAMEWORK_TRACE_INDEX.md')
