import { readdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const args = parseArgs(process.argv.slice(2));
if (!args.resultsRoot || !args.output) throw new Error("Usage: summarize-context-eval.ts --results-root <dir> --output <md> [--judge-dir <dir>] [--expected-models a,b] [--expected-conditions a,b] [--expected-repeats 3]");
const root = resolve(args.resultsRoot);
const score = JSON.parse(await readFile(resolve(root, "score_summary.json"), "utf8")) as { generatedAt: string; runs: RunScore[] };
const contextRuns = score.runs.filter((run) => run.task === "context");
const judge = args.judgeDir ? await loadJudge(resolve(args.judgeDir)) : new Map<string, JudgeOutput>();
const judgeKey = args.judgeDir ? await loadJudgeKey(resolve(args.judgeDir, "sample_key.csv")) : new Map<string, KeyRow>();

const models = split(args.expectedModels) ?? unique(contextRuns.map((run) => run.model));
const conditions = split(args.expectedConditions) ?? unique(contextRuns.map((run) => run.condition));
const expectedRepeats = Number(args.expectedRepeats ?? 3);
const groups = models.flatMap((model) => conditions.map((condition) => ({ model, condition })));
const lines: string[] = [
  "# Urban Agent 上下文机制修复后重复实验审计",
  "",
  `- 规则评分生成时间：${score.generatedAt}`,
  `- 结果根目录：\`${root}\``,
  `- 原始运行材料：每个 run 目录中的 \`run_manifest.json\`、\`pi_events.jsonl\`、\`research_state.json\`、\`assistant_output.txt\` 和 \`prepared_session/\`。`,
  args.judgeDir ? `- 隔离 Judge 材料：\`${resolve(args.judgeDir)}\`；原始输出保存在 \`raw_outputs/\`，身份映射单独保存在 \`sample_key.csv\`。` : "- 隔离 Judge：未运行。",
  "- 规则评分中的身份、消息哈希和状态清理检查是权威硬检查；隔离 LLM judge 仅评价语义与 claim calibration。",
  "- 规则评分的路线恢复项允许以真实 recall trace 作为证据；Judge 的 J1 则要求 Agent 在 A1/D1 中把证据转化为可读结论。两者分别衡量‘取回了’与‘正确使用并报告了’，不应互相替代。",
  "- token 与时间是描述性成本，不是等工作量效率：提前超时的运行可能没有返回 usage（记为 0），不同条件完成的有效工作也不同，因此不得脱离完成状态和质量分数解释。",
  "",
  "## 运行矩阵",
  "",
  "| 模型 | 条件 | 已运行/计划 | exit0/已运行 | authenticated patch | 规则分数 mean±SD (%) | Judge mean±SD (%) | token mean±SD | 运行时间 mean±SD (s) | 超时：压缩/推理工具 | 严重错误项* |",
  "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
];

for (const group of groups) {
  const runs = contextRuns.filter((run) => run.model === group.model && run.condition === group.condition);
  const judgeScores = [...judge.entries()]
    .filter(([sampleId]) => {
      const key = judgeKey.get(sampleId);
      return key?.model === group.model && key?.condition === group.condition;
    })
    .map(([, output]) => 10 * output.total);
  const severe = runs.filter((run) => run.invalid_human_patch_flag || run.prohibited_claim_flag || Number(run.exit_code) !== 0 || Boolean(run.unknown_route_ids)).length
    + [...judge.entries()].filter(([sampleId, output]) => {
      const key = judgeKey.get(sampleId);
      return key?.model === group.model && key?.condition === group.condition && output.severe_semantic_errors?.length;
    }).length;
  lines.push(`| ${group.model} | ${group.condition} | ${runs.length}/${expectedRepeats} | ${runs.filter((run) => Number(run.exit_code) === 0).length}/${runs.length} | ${runs.filter((run) => run.authenticated_patch_success).length}/${runs.length} | ${formatStat(runs.map((run) => Number(run.percent)))} | ${formatStat(judgeScores)} | ${formatStat(runs.map((run) => Number(run.total_tokens)))} | ${formatStat(runs.map((run) => Number(run.runtime_seconds)))} | ${runs.filter((run) => run.failure_stage === "compaction").length}/${runs.filter((run) => run.failure_stage === "inference_or_tools").length} | ${severe} |`);
}
lines.push("", "\\* 严重错误项为规则运行错误与 Judge 严重语义错误之和；同一次 run 可能在两侧各计一次。", "");

if (conditions.includes("urban_full") && conditions.includes("pi_default_compaction")) {
  lines.push("", "## Urban 相对 Pi 的配对差值", "", "只比较相同模型、相同 repeat 且两边均有 manifest 的运行；正的分数差表示 Urban 更高，正的 token/时间差表示 Urban 消耗更多。", "", "| 模型 | 配对数 | 规则分数差（百分点） | Judge 差（/10） | token 差 | 运行时间差（s） |", "|---|---:|---:|---:|---:|---:|");
  for (const model of models) {
    const urban = contextRuns.filter((run) => run.model === model && run.condition === "urban_full");
    const pi = contextRuns.filter((run) => run.model === model && run.condition === "pi_default_compaction");
    const pairs = urban.flatMap((urbanRun) => {
      const piRun = pi.find((candidate) => Number(candidate.repeat) === Number(urbanRun.repeat));
      return piRun ? [{ urban: urbanRun, pi: piRun }] : [];
    });
    const judgeDelta = pairs.flatMap((pair) => {
      const urbanJudge = judgeForRun(pair.urban.run_id, judge, judgeKey);
      const piJudge = judgeForRun(pair.pi.run_id, judge, judgeKey);
      return urbanJudge && piJudge ? [Number(urbanJudge.total) - Number(piJudge.total)] : [];
    });
    lines.push(`| ${model} | ${pairs.length} | ${formatStat(pairs.map((pair) => Number(pair.urban.percent) - Number(pair.pi.percent)))} | ${formatStat(judgeDelta)} | ${formatStat(pairs.map((pair) => Number(pair.urban.total_tokens) - Number(pair.pi.total_tokens)))} | ${formatStat(pairs.map((pair) => Number(pair.urban.runtime_seconds) - Number(pair.pi.runtime_seconds)))} |`);
  }
}

lines.push("", "## 分项规则评分", "", "| 模型 | 条件 | semantic | provenance | state cleanup | claim calibration |", "|---|---|---:|---:|---:|---:|");
for (const group of groups) {
  const runs = contextRuns.filter((run) => run.model === group.model && run.condition === group.condition);
  lines.push(`| ${group.model} | ${group.condition} | ${formatStat(runs.map((r) => Number(r.semantic_score)))} | ${formatStat(runs.map((r) => Number(r.provenance_score)))} | ${formatStat(runs.map((r) => Number(r.state_cleanup_score)))} | ${formatStat(runs.map((r) => Number(r.claim_calibration_score)))} |`);
}

lines.push("", "## 单次运行审计", "", "| run | 规则 % | Judge /10 | provenance | cleanup | claim | tokens | runtime s | exit | failure stage | invalid patch | prohibited claim | unknown IDs |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|");
for (const run of contextRuns.sort((a, b) => a.run_id.localeCompare(b.run_id))) {
  const key = [...judgeKey.entries()].find(([, row]) => normalizePath(row.run_dir).endsWith(normalizePath(run.run_id)))?.[0];
  const judged = key ? judge.get(key) : undefined;
  lines.push(`| ${run.run_id} | ${fmt(Number(run.percent))} | ${judged ? fmt(Number(judged.total)) : "未跑"} | ${run.provenance_score} | ${run.state_cleanup_score} | ${run.claim_calibration_score} | ${run.total_tokens} | ${fmt(Number(run.runtime_seconds))} | ${run.exit_code} | ${run.failure_stage} | ${run.invalid_human_patch_flag} | ${run.prohibited_claim_flag} | ${run.unknown_route_ids || "-"} |`);
}

const judgeUncertainties = [...judge.entries()].filter(([, output]) => output.uncertainty || output.severe_semantic_errors?.length);
lines.push("", "## 隔离 Judge 不确定性与严重语义错误", "");
if (!args.judgeDir) lines.push("- 未运行。");
else if (!judgeUncertainties.length) lines.push("- Judge 未报告严重语义错误或额外不确定性。");
else for (const [sampleId, output] of judgeUncertainties) {
  const key = judgeKey.get(sampleId);
  lines.push(`- ${sampleId}${key ? `（${key.model} × ${key.condition} × repeat ${key.repeat}）` : ""}：severe=${(output.severe_semantic_errors ?? []).join("；") || "无"}；uncertainty=${output.uncertainty || "未说明"}`);
}

const missing = groups.filter((group) => contextRuns.filter((run) => run.model === group.model && run.condition === group.condition).length < expectedRepeats);
lines.push("", "## 未运行项目", "", missing.length ? missing.map((group) => `- ${group.model} × ${group.condition}：已运行 ${contextRuns.filter((run) => run.model === group.model && run.condition === group.condition).length}/${expectedRepeats}。`).join("\n") : "- 无。", "");
await writeFile(resolve(args.output), `${lines.join("\n")}\n`, "utf8");

const paperRows = groups.map((group) => {
  const runs = contextRuns.filter((run) => run.model === group.model && run.condition === group.condition);
  const judged = [...judge.entries()].flatMap(([sampleId, output]) => {
    const key = judgeKey.get(sampleId);
    return key?.model === group.model && key?.condition === group.condition ? [output] : [];
  });
  const dimension = (id: string) => stat(judged.flatMap((output) => {
    const item = output.dimensions?.find((candidate) => candidate.id === id);
    return item ? [Number(item.score)] : [];
  }));
  const rule = stat(runs.map((run) => Number(run.percent)));
  const judgeTotal = stat(judged.map((output) => Number(output.total)));
  const semantic = stat(runs.map((run) => Number(run.semantic_score)));
  const provenance = stat(runs.map((run) => Number(run.provenance_score)));
  const cleanup = stat(runs.map((run) => Number(run.state_cleanup_score)));
  const claim = stat(runs.map((run) => Number(run.claim_calibration_score)));
  const runtime = stat(runs.map((run) => Number(run.runtime_seconds)));
  const tokens = stat(runs.map((run) => Number(run.total_tokens)));
  return {
    model: group.model,
    condition: group.condition,
    n: runs.length,
    planned_n: expectedRepeats,
    exit0_n: runs.filter((run) => Number(run.exit_code) === 0).length,
    authenticated_patch_success_n: runs.filter((run) => run.authenticated_patch_success).length,
    rule_percent_mean: rule.mean,
    rule_percent_sd: rule.sd,
    judge_n: judged.length,
    judge_total_10_mean: judgeTotal.mean,
    judge_total_10_sd: judgeTotal.sd,
    judge_J1_mean: dimension("J1").mean,
    judge_J1_sd: dimension("J1").sd,
    judge_J2_mean: dimension("J2").mean,
    judge_J2_sd: dimension("J2").sd,
    judge_J3_mean: dimension("J3").mean,
    judge_J3_sd: dimension("J3").sd,
    judge_J4_mean: dimension("J4").mean,
    judge_J4_sd: dimension("J4").sd,
    judge_J5_mean: dimension("J5").mean,
    judge_J5_sd: dimension("J5").sd,
    rule_semantic_mean: semantic.mean,
    rule_semantic_sd: semantic.sd,
    rule_provenance_mean: provenance.mean,
    rule_provenance_sd: provenance.sd,
    rule_state_cleanup_mean: cleanup.mean,
    rule_state_cleanup_sd: cleanup.sd,
    rule_claim_calibration_mean: claim.mean,
    rule_claim_calibration_sd: claim.sd,
    total_tokens_mean: tokens.mean,
    total_tokens_sd: tokens.sd,
    runtime_seconds_mean: runtime.mean,
    runtime_seconds_sd: runtime.sd,
    compaction_timeout_n: runs.filter((run) => run.failure_stage === "compaction").length,
    inference_or_tools_timeout_n: runs.filter((run) => run.failure_stage === "inference_or_tools").length,
    completed_n: runs.filter((run) => run.failure_stage === "completed").length,
    judge_severe_error_run_n: judged.filter((output) => output.severe_semantic_errors?.length).length,
  };
});
const paperJson = resolve(root, "paper_table_rule_and_judge.json");
const paperCsv = resolve(root, "paper_table_rule_and_judge.csv");
await writeFile(paperJson, `${JSON.stringify(paperRows, null, 2)}\n`, "utf8");
await writeFile(paperCsv, toCsv(paperRows), "utf8");
console.log(JSON.stringify({ output: resolve(args.output), paperCsv, paperJson, runs: contextRuns.length, judgeOutputs: judge.size, missingGroups: missing.length }, null, 2));

interface RunScore { run_id: string; model: string; task: string; condition: string; repeat: number; percent: number; semantic_score: number; provenance_score: number; state_cleanup_score: number; claim_calibration_score: number; input_tokens: number; output_tokens: number; total_tokens: number; runtime_seconds: number; exit_code: number; failure_stage: string; unknown_route_ids: string; prohibited_claim_flag: boolean; invalid_human_patch_flag: boolean; authenticated_patch_success: boolean }
interface JudgeOutput { sample_id: string; total: number; dimensions?: Array<{ id: string; score: number }>; severe_semantic_errors?: string[]; uncertainty?: string }
interface KeyRow { sample_id: string; model: string; condition: string; repeat: string; run_dir: string }
async function loadJudge(dir: string): Promise<Map<string, JudgeOutput>> { const out = new Map<string, JudgeOutput>(); const raw = resolve(dir, "raw_outputs"); try { for (const file of await readdir(raw)) if (file.endsWith(".json")) { const parsed = JSON.parse(await readFile(resolve(raw, file), "utf8")) as JudgeOutput; out.set(parsed.sample_id, parsed); } } catch {} return out; }
async function loadJudgeKey(path: string): Promise<Map<string, KeyRow>> { const map = new Map<string, KeyRow>(); for (const line of (await readFile(path, "utf8")).split(/\r?\n/).slice(1).filter(Boolean)) { const [sample_id, model, condition, repeat, run_dir] = parseCsvLine(line); map.set(sample_id, { sample_id, model, condition, repeat, run_dir }); } return map; }
function judgeForRun(runId: string, outputs: Map<string, JudgeOutput>, key: Map<string, KeyRow>): JudgeOutput | undefined { const sampleId = [...key.entries()].find(([, row]) => normalizePath(row.run_dir).endsWith(normalizePath(runId)))?.[0]; return sampleId ? outputs.get(sampleId) : undefined; }
function parseCsvLine(line: string): string[] { const out: string[] = []; let current = ""; let quoted = false; for (let i = 0; i < line.length; i++) { const ch = line[i]; if (ch === '"' && quoted && line[i + 1] === '"') { current += '"'; i++; } else if (ch === '"') quoted = !quoted; else if (ch === "," && !quoted) { out.push(current); current = ""; } else current += ch; } out.push(current); return out; }
function formatStat(values: number[]): string { const finite = values.filter(Number.isFinite); if (!finite.length) return "未跑"; const mean = finite.reduce((a, b) => a + b, 0) / finite.length; const sd = finite.length > 1 ? Math.sqrt(finite.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (finite.length - 1)) : 0; return `${fmt(mean)}±${fmt(sd)}`; }
function stat(values: number[]): { mean: number | null; sd: number | null } { const finite = values.filter(Number.isFinite); if (!finite.length) return { mean: null, sd: null }; const mean = finite.reduce((a, b) => a + b, 0) / finite.length; const sd = finite.length > 1 ? Math.sqrt(finite.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (finite.length - 1)) : 0; return { mean, sd }; }
function toCsv(rows: Array<Record<string, unknown>>): string { if (!rows.length) return ""; const headers = Object.keys(rows[0]); const quote = (value: unknown) => `"${String(value ?? "").replaceAll('"', '""')}"`; return `${headers.map(quote).join(",")}\n${rows.map((row) => headers.map((header) => quote(row[header])).join(",")).join("\n")}\n`; }
function fmt(value: number): string { return Number.isFinite(value) ? value.toFixed(2) : "NA"; }
function unique(values: string[]): string[] { return [...new Set(values)]; }
function normalizePath(value: string): string { return value.replaceAll("\\", "/").replace(/^.*?results_authenticated_patch_v\d+_repeats\//, ""); }
function split(value?: string): string[] | undefined { return value ? value.split(",").map((item) => item.trim()).filter(Boolean) : undefined; }
function parseArgs(values: string[]) { const out: Record<string, string> = {}; for (let i = 0; i < values.length; i += 2) out[values[i].replace(/^--/, "")] = values[i + 1] ?? ""; return { resultsRoot: out["results-root"], output: out.output, judgeDir: out["judge-dir"], expectedModels: out["expected-models"], expectedConditions: out["expected-conditions"], expectedRepeats: out["expected-repeats"] }; }
