import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { resolveCompactionSettings } from "../src/core/model-context.js";
import { applyProviderCompatibility } from "../src/core/provider-compat.js";

const args = parseArgs(process.argv.slice(2));
const source = resolve(args.source || ".pi-agent/models.json");
const outDir = resolve(required(args, "out-dir"));
const provider = required(args, "provider");
const modelId = required(args, "model");
const contextWindow = positiveInteger(args["context-window"]);
const maxTokens = positiveInteger(args["max-output-tokens"]);
const baseUrl = args["base-url"];
const config = JSON.parse(await readFile(source, "utf8")) as {
  providers?: Record<string, { baseUrl?: string; models?: Array<Record<string, unknown>> }>;
};
const providerConfig = config.providers?.[provider];
if (!providerConfig) throw new Error(`Provider ${provider} is not present in ${source}.`);
const model = providerConfig.models?.find((candidate) => candidate.id === modelId);
if (!model) throw new Error(`Model ${provider}/${modelId} is not present in ${source}.`);
if (contextWindow) model.contextWindow = contextWindow;
if (maxTokens) model.maxTokens = maxTokens;
if (baseUrl) providerConfig.baseUrl = baseUrl;
Object.assign(model, applyProviderCompatibility(provider, model));
await mkdir(outDir, { recursive: true });
const output = join(outDir, "models.json");
await writeFile(output, JSON.stringify(config, null, 2), "utf8");
const effectiveWindow = positiveIntegerValue(model.contextWindow) ?? 32_768;
const effectiveMaxTokens = positiveIntegerValue(model.maxTokens);
const settings = { compaction: resolveCompactionSettings(effectiveWindow, effectiveMaxTokens) };
const settingsOutput = join(outDir, "settings.json");
await writeFile(settingsOutput, JSON.stringify(settings, null, 2), "utf8");
console.log(JSON.stringify({
  success: true,
  output,
  settingsOutput,
  provider,
  model: modelId,
  baseUrlHost: safeHost(providerConfig.baseUrl),
  contextWindow: model.contextWindow,
  maxTokens: model.maxTokens,
  compaction: settings.compaction,
}));

function parseArgs(values: string[]): Record<string, string> {
  const result: Record<string, string> = {};
  for (let index = 0; index < values.length; index += 1) {
    const key = values[index];
    if (!key.startsWith("--")) continue;
    result[key.slice(2)] = values[index + 1] ?? "";
    index += 1;
  }
  return result;
}

function required(values: Record<string, string>, key: string): string {
  const value = values[key];
  if (!value) throw new Error(`Missing --${key}.`);
  return value;
}

function positiveInteger(value?: string): number | undefined {
  if (!value) return undefined;
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) throw new Error(`Expected a positive integer, received ${value}.`);
  return parsed;
}

function positiveIntegerValue(value: unknown): number | undefined {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) return undefined;
  return Math.floor(value);
}

function safeHost(value?: string): string | undefined {
  if (!value) return undefined;
  try {
    return new URL(value).host;
  } catch {
    return "invalid";
  }
}
