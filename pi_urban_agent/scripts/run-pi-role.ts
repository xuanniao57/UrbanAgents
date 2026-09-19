import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import { basename, join, resolve } from "node:path";

const args = parseArgs(process.argv.slice(2));
const role = args.role;
if (role !== "worker" && role !== "reviewer") throw new Error("--role must be worker or reviewer");
if (!args.runDir) throw new Error("--run-dir is required");
const runDir = resolve(args.runDir);
const provider = args.provider || process.env.URBAN_PI_PROVIDER || "local-vllm";
const model = args.model || process.env.URBAN_PI_MODEL || "Qwen3-30B-A3B-FP8";
const root = resolve(process.cwd());
const executable = process.platform === "win32" ? join(root, "node_modules", ".bin", "pi.cmd") : join(root, "node_modules", ".bin", "pi");
const extension = join(root, ".pi", "extensions", "urban-agent.ts");
const runModelConfig = join(runDir, ".pi-agent-runtime");
const piConfigDir = existsSync(join(runModelConfig, "models.json")) ? runModelConfig : join(root, ".pi-agent");
const prompt = args.prompt || (role === "worker"
  ? "Act only as the Worker for the active branch. Inspect the authoritative Urban Research Git Tree, execute only the assigned branch with the exposed tools, attach every produced artifact with metrics and SHA-256, and stop without reviewing or selecting the route."
  : "Act only as the independent Reviewer for the active branch. Inspect the structured contract and evidence pointers, audit comparability, held-out evaluation, model-process scale, stability, and claim scope, then record exactly one review decision. Do not execute analyses and do not make a human selection.");
const cliArgs = ["-e", extension, "--no-builtin-tools", "--no-session", "--provider", provider, "--model", model, "-p", prompt];
const env = {
  ...process.env,
  URBAN_PI_RUN_DIR: runDir,
  URBAN_PI_REPOSITORY_ROOT: resolve(root, ".."),
  PI_CODING_AGENT_DIR: piConfigDir,
  VLLM_BASE_URL: process.env.VLLM_BASE_URL || "http://127.0.0.1:8000/v1",
  VLLM_API_KEY: process.env.VLLM_API_KEY || "local-vllm",
};
const child = spawn(executable, cliArgs, { cwd: root, env, windowsHide: true, shell: process.platform === "win32" });
const stdout: Buffer[] = [];
const stderr: Buffer[] = [];
child.stdout.on("data", (chunk: Buffer) => { stdout.push(chunk); process.stdout.write(chunk); });
child.stderr.on("data", (chunk: Buffer) => { stderr.push(chunk); process.stderr.write(chunk); });
const exitCode = await new Promise<number>((resolveExit, reject) => {
  child.once("error", reject);
  child.once("close", (code) => resolveExit(code ?? 1));
});
const logDir = join(runDir, "logs");
await mkdir(logDir, { recursive: true });
const stamp = new Date().toISOString().replaceAll(/[-:.TZ]/g, "").slice(0, 14);
const logPath = join(logDir, `${stamp}_${role}_${basename(model)}.json`);
await writeFile(logPath, JSON.stringify({
  role,
  provider,
  model,
  prompt,
  exitCode,
  stdout: Buffer.concat(stdout).toString("utf8"),
  stderr: Buffer.concat(stderr).toString("utf8"),
}, null, 2), "utf8");
console.log(`\nRole log: ${logPath}`);
process.exitCode = exitCode;

function parseArgs(values: string[]): { role?: string; runDir?: string; provider?: string; model?: string; prompt?: string } {
  const parsed: Record<string, string> = {};
  for (let index = 0; index < values.length; index += 1) {
    const key = values[index];
    if (!key.startsWith("--")) continue;
    parsed[key.slice(2)] = values[index + 1] ?? "";
    index += 1;
  }
  return { role: parsed.role, runDir: parsed["run-dir"], provider: parsed.provider, model: parsed.model, prompt: parsed.prompt };
}
