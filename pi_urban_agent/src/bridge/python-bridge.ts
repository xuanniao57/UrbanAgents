import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export type PythonMethod = "read_file" | "inspect_json" | "inspect_csv" | "inspect_text" | "list_directory" | "hash_artifact" | "run_script";

export interface PythonBridgeResponse {
  success: boolean;
  method: string;
  result?: Record<string, unknown>;
  error?: string;
}

const moduleDir = dirname(fileURLToPath(import.meta.url));
const defaultServer = resolve(moduleDir, "..", "..", "python", "urban_tool_server.py");

export async function callPython(
  method: PythonMethod,
  arguments_: Record<string, unknown>,
  options: { signal?: AbortSignal; repositoryRoot: string; runDir: string; timeoutMs?: number },
): Promise<PythonBridgeResponse> {
  return new Promise((resolveResponse, reject) => {
    const python = process.env.URBAN_PI_PYTHON || (process.platform === "win32" ? "python" : "python3");
    const child = spawn(python, [defaultServer], {
      cwd: options.repositoryRoot,
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
      env: { ...process.env, URBAN_PI_REPOSITORY_ROOT: options.repositoryRoot, URBAN_TOOL_RESULT_ROOT: resolve(options.runDir || options.repositoryRoot, 'execution-results'), PYTHONUTF8: "1" },
    });
    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];
    const timer = setTimeout(() => child.kill(), options.timeoutMs ?? 1_900_000);
    const abort = () => child.kill();
    options.signal?.addEventListener("abort", abort, { once: true });
    child.stdout.on("data", (chunk: Buffer) => stdout.push(chunk));
    child.stderr.on("data", (chunk: Buffer) => stderr.push(chunk));
    child.once("error", reject);
    child.once("close", (code) => {
      clearTimeout(timer);
      options.signal?.removeEventListener("abort", abort);
      const text = Buffer.concat(stdout).toString("utf8").trim();
      try {
        const parsed = JSON.parse(text) as PythonBridgeResponse;
        if (!parsed.success && code !== 0) parsed.error ??= Buffer.concat(stderr).toString("utf8").trim();
        resolveResponse(parsed);
      } catch {
        reject(new Error(Buffer.concat(stderr).toString("utf8").trim() || `Python bridge returned invalid JSON (exit ${code}): ${text.slice(0, 500)}`));
      }
    });
    child.stdin.end(JSON.stringify({ method, arguments: arguments_, allowed_roots: [options.repositoryRoot, options.runDir] }));
  });
}
