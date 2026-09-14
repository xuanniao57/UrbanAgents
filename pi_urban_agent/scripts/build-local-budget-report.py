"""Render an engineering report from audited raw local runs; no inferred scores."""
import json,sys,zipfile
from pathlib import Path

root=Path(sys.argv[1]).resolve()
data=json.loads((root/'run_audit.json').read_text(encoding='utf-8'))
runs=data['runs'];complete=(root/'complete.json').exists()
requests=[]
for p in root.glob('*/requests/*/summary.json'):
    try:requests.append(json.loads(p.read_text(encoding='utf-8')))
    except json.JSONDecodeError:pass
used=[r for r in requests if r.get('usage')]
max_actual=max((r['usage'].get('prompt_tokens',0)+r.get('maxTokens',0) for r in used),default=0)
power=[]
telemetry=root/'gpu_telemetry.jsonl'
if telemetry.exists():
    for line in telemetry.read_text(encoding='utf-8').splitlines():
        try:power.append(float(json.loads(line)['power_w_util_pct_vram_mb_temp_c'].split(',')[0]))
        except (ValueError,KeyError):pass
lines=['# 本地统一预算修复：实机复测报告','',
  '**状态：'+('八组运行已结束。' if complete else '运行中，仅为已收集结果，尚未完成八组。')+'**','',
  '## 1. 改了什么','',
  'Pi共享发送入口对系统提示、工具定义、历史、所有工具结果和预留输出统一计数；大结果外置并保留完整入口。旧历史继续由Pi摘要函数处理。多段摘要先共享一份汇总输入预算，再分配各段输出，不再各自独立占满额度。压缩后再次核验，不能容纳必要内容就明确拒绝，不发超窗请求、不退成1-token输出。','',
  '配套修复了只读文件工具、Python日志/产物manifest、可选合同字段哈希，以及测试器额外30秒接收时限。没有修改模型权重、分析脚本的科学结果、研究路线数量或评分答案。','',
  '## 2. 运行条件','',
  '- Qwen3.5 0.8B、2B为现有Q8_0；4B、9B为现有Q4_K_M。各模型内部Urban/Pi使用同一量化、工具和输入。',
  '- 8,192窗口、2,048输出上限、492格式安全余量；部署词表计数并核对服务端usage。',
  '- 两种模式都基于本项目Pi runtime；共享预算层会改变前置压缩时机，不能称为完全未修改的原生Pi。仅上下文模式不同。',
  '- 每组指定新研究目录、五轮相同自然语言输入：研究与数据→只授权OLS→800m粗尺度对照→回读真实系数→恢复进度。无人工compact、无预填结果、无固定节点数。',
  '- 每轮300秒/32工具尝试/连续4次工具错误；前置步骤未完成时后续轮只能用于诊断恢复，不算完成科学分析。',
  '- 固定脚本不是自适应专家对话；每组一次，无独立LLM judge。本轮是工程回归，不能替代论文4.3的重复消融或直接与旧短程召回分数相减。','',
  '- 工作区并非文件系统强隔离：2B/0.8B曾写错运行目录；收尾还发现数据目录含v6旧状态文件，v7工具日志未检出其runId。已原样归档，17个科学输入哈希不变。详见OBSERVATIONS_CN.md；后续正式消融需隔离目录和只读输入。','',
  f'- GPU遥测最高 {max(power,default=0):.2f} W。模型身份、量化、服务版本见 model_metadata.json。','',
  '## 3. 预算与执行分开看','',
  f'- 已保存请求 {len(requests)} 次，其中 {len(used)} 次有服务端usage；实际输入token＋请求输出上限最高 {max_actual}。',
  f'- HTTP错误 {sum(r.get("http_errors",0) for r in runs)}；实际输入＋输出上限超8K {sum(r.get("over_budget_sent",0) for r in runs)}；1-token请求 {sum(r.get("one_token_requests",0) for r in runs)}。',
  f'- 原生压缩错误 {sum(r.get("native_compaction_errors",0) for r in runs)}；本地预算错误事件 {sum(r.get("local_budget_error_events",0) for r in runs)}。',
  f'- 运行源文件哈希不一致：{len(data.get("source_hash_mismatches",[]))}。',
  '- 类型检查与67项单元/集成测试通过，原始输出见 regression.tap。',
  '- 旧27B的23个失败请求通过离线预算重放；摘要为测试桩，不是27B重新推理或摘要准确率证据。','',
  '| 模型 | 上下文模式 | 已结束轮次 | 非空最终回复轮次 | 实际OLS尺度数 | 原生压缩成功/错误 | 前置压缩 | 人类决议写入 |',
  '|---|---|---:|---:|---:|---:|---:|---:|']
for r in sorted(runs,key=lambda x:(float(x['model'].rstrip('b')),x['condition'])):
    mode='Urban' if r['condition']=='urban_full' else 'Pi-only'
    lines.append(f'| {r["model"]} | {mode} | {r["turns"]}/5 | {r["final_text_turns"]} | {r["ols_scales"]}/7 | {r["native_compactions"]}/{r["native_compaction_errors"]} | {r["preflight_compactions"]} | {r["human_decisions"]} |')
lines += ['',
  '非空回复不代表内容正确；OLS数来自实际完成的run_manifest和结果CSV，不来自模型自称。写入决议的数量也不等于语义正确。原生压缩与发送前预检压缩分开统计。错误不会因HTTP200或存在JSON状态文件就被判通过。','',
  '## 4. 如何阅读原始证据','',
  '每组 turns/001...005 内：prompt.txt是人类输入；answer.txt含中间解释；final_answer.txt仅最后回复；summary.json包含工具错误、usage及终止原因。pi_events.jsonl是全部工具调用/结果。request-budget/events.jsonl保留前置摘要和分段预算。研究状态包含模型实际写入的合同与决议，并非标准答案。','',
  '最新人类原文是否出现在实际请求中另见 run_audit.json 的 wire_audit。缺少原文时不能直接认定遗忘，需区分原生摘要、请求中断与结构化状态；保留原文也不自动代表模型正确遵从。','',
  '## 5. 本轮定位与后续','',
  '不以增加上下文窗口、替模型填好参数、预建研究树、重复到成功等方式掩盖问题。若完整流程仍未完成，优先检查数据合同的源文件接入、工具/脚本入口的持久索引、run/branch/artifact标识，以及分页说明是否诱发无意义扫描。预算安全和信息召回质量需要分别验证。','',
  '所有失败保留；v1–v6属于开发排查，尤其v5的测试器短时限、v6的摘要合并预算错误，均不混入本表。','',
  '逐条人工核查（包括9B两组无证据数值输出）见 OBSERVATIONS_CN.md。实现细节见 IMPLEMENTATION_CN.md；源代码与测试数据见 source_and_test_data.zip；原始会话与审计见当前目录。']
if complete:
    successful=sum(r['ols_scales']==7 and r['file_hash_errors']==0 for r in runs)
    lines += ['', '## 6. 验收结论', '',
      f'七尺度实际OLS产物验收：{successful}/{len(runs)}组。这个判据只检验有无真实产物，尚不等于全部科学判断正确。', '',
      '这是一版有完整失败记录的工程修订，不是已验证的稳定研究助手。统一预算解决的是发送和摘要汇总是否容纳得下；摘要遗漏入口、逐字符翻阅历史、标识混淆和无产物却报告数值，仍会导致研究失败。不能凭本轮宣称Urban优于Pi，也不能把模型声称的R²/系数写进论文。', '',
      '下一次最小修订应集中在可操作的信息入口：数据与脚本使用稳定索引；分页单位在参数层明确；历史存档与已计算产物类型分开；完成声明须对应实际产物。保持本轮数据和失败记录，再开独立版本复测，不回填本轮成功。']
    control=root/'host_control/ols/run_manifest.json'
    if control.exists():
        manifest=json.loads(control.read_text(encoding='utf-8'))
        lines += ['', '## 7. 主机直接执行对照', '',
          f'八组Agent运行结束后，使用相同科学Python、数据和analysis.py直接运行七尺度OLS，状态：{manifest.get("status")}。产物见host_control/ols。', '',
          '这是维护者直接执行的环境控制，不经过被测Agent，不计入上表任何一组，也不补写研究树。它用于区分数据/依赖不可用与Agent未找到入口、未发出有效执行调用。']
(root/'REPORT_CN.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'report':str(root/'REPORT_CN.md'),'complete':complete,'runs':len(runs),'requests':len(requests),'max_actual_prompt_plus_output':max_actual},ensure_ascii=False))
if complete and '--zip' in sys.argv:
    target=root/'run_logs_and_results.zip'
    files=[p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in {'.json','.jsonl','.md','.txt','.csv','.sse','.tap'} and '.env' not in p.name and 'node_modules' not in p.parts]
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for p in files:z.write(p,p.relative_to(root))
    print(json.dumps({'logs_zip':str(target),'files':len(files),'bytes':target.stat().st_size}))
