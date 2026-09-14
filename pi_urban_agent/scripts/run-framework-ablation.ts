/** Run the same natural six-turn workflow under five framework conditions. */
import { spawn } from "node:child_process";
import { access, mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

type Status = { idle?: boolean; stopped?: boolean; turn?: number; error?: string };
const args = parseArgs(process.argv.slice(2));
if (!args.model || !args.dataRoot || !args.outputRoot) {
  throw new Error("Require --model, --data-root and --output-root");
}
const root = resolve(process.cwd());
const outputRoot = resolve(args.outputRoot);
const dataRoot = resolve(args.dataRoot);
const protocol = JSON.parse(await readFile(resolve(root, args.protocol ?? "evaluation/framework_ablation_v1/protocol.json"), "utf8"));
const allowed = new Set<string>(protocol.conditions);
const conditions = (args.conditions?.split(",") ?? protocol.conditions).map((value: string) => value.trim()).filter(Boolean);
if (conditions.some((condition: string) => !allowed.has(condition))) throw new Error("Unknown condition");
const repeats = positive(args.repeats ?? "1", "--repeats");
await mkdir(outputRoot, { recursive: true });

const summaries: Record<string, unknown>[] = [];
for (const condition of conditions) for (let repeat = 1; repeat <= repeats; repeat += 1) {
  const run = resolve(outputRoot, `${safe(args.model)}__${condition}__r${String(repeat).padStart(2, "0")}`);
  try { await access(run); throw new Error(`Refuse to reuse existing run: ${run}`); }
  catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
  await mkdir(run, { recursive: true });
  const childArgs = ["--import", "tsx", resolve(root, "scripts/long-workflow-session.ts"),
    "--out", run, "--condition", condition, "--data-root", dataRoot,
    "--model", args.model, "--provider", args.provider ?? "local-ollama",
    "--window", args.contextWindow ?? "8192", "--output-tokens", args.maxOutputTokens ?? "2048",
    "--deadline", args.deadline ?? "600", "--seed", String(positive(args.seed ?? "42", "--seed") + repeat - 1)];
  if (args.baseUrl) childArgs.push("--base-url", args.baseUrl);
  const started = Date.now();
  const child = spawn(process.execPath, childArgs, { cwd: root, env: process.env, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] });
  const closed = new Promise<number>((done) => {
    child.once("error", () => done(1));
    child.once("close", (code) => done(code ?? 1));
  });
  const stdout: Buffer[] = [];
  const stderr: Buffer[] = [];
  child.stdout.on("data", (chunk: Buffer) => stdout.push(chunk));
  child.stderr.on("data", (chunk: Buffer) => stderr.push(chunk));
  try {
    await waitFor(run, (status) => status.idle === true && (status.turn ?? 0) === 0, 120_000);
    for (let index = 0; index < protocol.turns.length; index += 1) {
      const number = index + 1;
      const inbox = resolve(run, "inbox", `${String(number).padStart(3, "0")}.json`);
      const temporary = `${inbox}.tmp`;
      await writeFile(temporary, JSON.stringify({ message: protocol.turns[index].message }, null, 2), "utf8");
      await rename(temporary, inbox);
      await waitFor(run, (status) => status.idle === true && (status.turn ?? 0) >= number, (positive(args.deadline ?? "600", "--deadline") + 120) * 1000);
    }
    await writeFile(resolve(run, "STOP"), "stop\n", "utf8");
  } catch (error) {
    await writeFile(resolve(run, "ORCHESTRATOR_ERROR.txt"), String(error), "utf8");
    child.kill();
  }
  const exitCode = await closed;
  await writeFile(resolve(run, "orchestrator_stdout.txt"), Buffer.concat(stdout), "utf8");
  await writeFile(resolve(run, "orchestrator_stderr.txt"), Buffer.concat(stderr), "utf8");
  const summary = { protocol: protocol.protocol, model: args.model, condition, repeat, exitCode, runtimeSeconds: (Date.now() - started) / 1000 };
  summaries.push(summary);
  await writeFile(resolve(outputRoot, "framework_ablation_summary.json"), JSON.stringify(summaries, null, 2), "utf8");
  console.log(JSON.stringify(summary));
}
await writeFile(resolve(outputRoot, "framework_ablation_summary.json"), JSON.stringify(summaries, null, 2), "utf8");

async function waitFor(run: string, accept: (status: Status) => boolean, timeoutMs: number): Promise<Status> {
  const deadline = Date.now() + timeoutMs;
  let last: Status = {};
  while (Date.now() < deadline) {
    try {
      last = JSON.parse(await readFile(resolve(run, "status.json"), "utf8"));
      if (last.error) throw new Error(last.error);
      if (accept(last)) return last;
      if (last.stopped) throw new Error(`Session stopped before target state: ${JSON.stringify(last)}`);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
    await new Promise((done) => setTimeout(done, 500));
  }
  throw new Error(`Timed out waiting for run status; last=${JSON.stringify(last)}`);
}

function positive(value: string, name: string): number {
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed <= 0) throw new Error(`${name} must be a positive integer`);
  return parsed;
}
function safe(value: string): string { return value.replace(/[^A-Za-z0-9_.-]+/g, "_"); }
function parseArgs(values: string[]): Record<string, string> {
  const result: Record<string, string> = {};
  for (let index = 0; index < values.length; index += 2) {
    const key = values[index]?.replace(/^--/, "");
    const value = values[index + 1];
    if (!key || !value) throw new Error("Arguments must be --name value pairs");
    const camel = key.replace(/-([a-z])/g, (_match, letter) => letter.toUpperCase());
    result[camel] = value;
  }
  return result;
}
