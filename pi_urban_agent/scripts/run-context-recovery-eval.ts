import { spawn, spawnSync } from "node:child_process";
import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";

const args = parseArgs(process.argv.slice(2));
if (!args.sourceRun || !args.outputDir) {
  throw new Error("Usage: run-context-recovery-eval.ts --source-run <completed-run> --output-dir <eval-run> [--provider local-ollama] [--model qwen3.5:9b]");
}

const root = resolve(process.cwd());
const sourceRun = resolve(args.sourceRun);
const outputDir = resolve(args.outputDir);
const provider = args.provider ?? "local-ollama";
const model = args.model ?? "qwen3.5:9b-urban16k";
const contextWindow = Number(args.contextWindow ?? 16_384);
const maxOutputTokens = Number(args.maxOutputTokens ?? 4_096);
const configDir = join(outputDir, ".pi-agent-runtime");
const logsDir = join(outputDir, "logs");
await mkdir(logsDir, { recursive: true });

const state = JSON.parse(await readFile(join(sourceRun, "research_state.json"), "utf8")) as Record<string, unknown>;
state.runDir = outputDir;
await writeFile(join(outputDir, "research_state.json"), JSON.stringify(state, null, 2), "utf8");
try {
  await copyFile(join(sourceRun, "research_events.jsonl"), join(outputDir, "research_events_source.jsonl"));
} catch {
  // A completed state is sufficient for recovery evaluation.
}

const prompt = [
  "You are resuming a completed urban research run after aggressive context compaction.",
  "Do not answer from parametric memory and do not modify the research state.",
  "Use urban_recall to recover the exact records needed to report:",
  "1) the human-selected main route;",
  "2) the retained sensitivity route;",
  "3) one blocked route; and",
  "4) the deferred fixed-distance comparison.",
  "For every route, provide the exact node ID, analysis support, model, bandwidth if applicable, analytical role, held-out R2, and the Reviewer or human decision that assigned that role.",
  "If a value is absent from the authoritative state, write absent. Do not infer or invent values.",
].join("\n");
const promptPath = join(outputDir, "recovery_prompt.txt");
await writeFile(promptPath, prompt, "utf8");

await run(resolve(root, "node_modules", ".bin", process.platform === "win32" ? "tsx.cmd" : "tsx"), [
  join(root, "scripts", "materialize-model-config.ts"),
  "--source", join(root, ".pi-agent", "models.json"),
  "--out-dir", configDir,
  "--provider", provider,
  "--model", model,
  "--context-window", String(contextWindow),
  "--max-output-tokens", String(maxOutputTokens),
], root, process.env);

const executable = resolve(root, "node_modules", ".bin", process.platform === "win32" ? "pi.cmd" : "pi");
const extension = join(root, ".pi", "extensions", "urban-agent.ts");
const environment = {
  ...process.env,
  URBAN_PI_RUN_DIR: outputDir,
  URBAN_PI_REPOSITORY_ROOT: resolve(root, ".."),
  PI_CODING_AGENT_DIR: configDir,
  PI_OFFLINE: "1",
};

const gpuBefore = hardwareSnapshot();
const startedAt = new Date().toISOString();
const result = await capture(executable, [
  "-e", extension,
  "--no-builtin-tools",
  "--no-session",
  "--no-context-files",
  "--offline",
  "--mode", "json",
  "--thinking", "minimal",
  "--provider", provider,
  "--model", model,
  "-p", `@${promptPath}`,
], root, environment);
const finishedAt = new Date().toISOString();
const gpuAfter = hardwareSnapshot();

await writeFile(join(logsDir, "pi_stdout.jsonl"), result.stdout, "utf8");
await writeFile(join(logsDir, "pi_stderr.txt"), result.stderr, "utf8");
await writeFile(join(outputDir, "hardware.json"), JSON.stringify({ gpuBefore, gpuAfter }, null, 2), "utf8");

let recallEvents = 0;
try {
  const manifest = await readFile(join(outputDir, "logs", "context_manifest.jsonl"), "utf8");
  recallEvents = manifest.split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line) as { event?: string }).filter((entry) => entry.event === "recall").length;
} catch {
  recallEvents = 0;
}

const report = {
  provider,
  model,
  contextWindow,
  maxOutputTokens,
  startedAt,
  finishedAt,
  exitCode: result.exitCode,
  recallEvents,
  noStateMutationRequested: true,
  promptPath,
  stdoutPath: join(logsDir, "pi_stdout.jsonl"),
  stderrPath: join(logsDir, "pi_stderr.txt"),
};
await writeFile(join(outputDir, "evaluation_summary.json"), JSON.stringify(report, null, 2), "utf8");
console.log(JSON.stringify(report, null, 2));
process.exitCode = result.exitCode;

function parseArgs(values: string[]): Record<string, string | undefined> & {
  sourceRun?: string;
  outputDir?: string;
  provider?: string;
  model?: string;
  contextWindow?: string;
  maxOutputTokens?: string;
} {
  const parsed: Record<string, string> = {};
  for (let index = 0; index < values.length; index += 1) {
    const key = values[index];
    if (!key.startsWith("--")) continue;
    parsed[key.slice(2)] = values[index + 1] ?? "";
    index += 1;
  }
  return {
    ...parsed,
    sourceRun: parsed["source-run"],
    outputDir: parsed["output-dir"],
    contextWindow: parsed["context-window"],
    maxOutputTokens: parsed["max-output-tokens"],
  };
}

async function run(executable: string, childArgs: string[], cwd: string, env: NodeJS.ProcessEnv): Promise<void> {
  const result = await capture(executable, childArgs, cwd, env);
  if (result.exitCode !== 0) throw new Error(result.stderr || result.stdout || `Process failed with ${result.exitCode}`);
}

async function capture(executable: string, childArgs: string[], cwd: string, env: NodeJS.ProcessEnv): Promise<{ exitCode: number; stdout: string; stderr: string }> {
  const child = spawn(executable, childArgs, { cwd, env, windowsHide: true, shell: process.platform === "win32" });
  const stdout: Buffer[] = [];
  const stderr: Buffer[] = [];
  child.stdout.on("data", (chunk: Buffer) => stdout.push(chunk));
  child.stderr.on("data", (chunk: Buffer) => stderr.push(chunk));
  const exitCode = await new Promise<number>((resolveExit, reject) => {
    child.once("error", reject);
    child.once("close", (code) => resolveExit(code ?? 1));
  });
  return { exitCode, stdout: Buffer.concat(stdout).toString("utf8"), stderr: Buffer.concat(stderr).toString("utf8") };
}

function hardwareSnapshot(): Record<string, unknown> {
  const nvidia = spawnSync("nvidia-smi", ["--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu", "--format=csv,noheader,nounits"], { encoding: "utf8", windowsHide: true });
  const ollama = spawnSync(process.platform === "win32" ? "ollama.exe" : "ollama", ["ps"], { encoding: "utf8", windowsHide: true });
  return {
    nvidiaSmi: nvidia.stdout?.trim() || nvidia.stderr?.trim() || "unavailable",
    ollamaPs: ollama.stdout?.trim() || ollama.stderr?.trim() || "unavailable",
  };
}
