import { FALLBACK_CONTEXT_WINDOW } from "./context-compiler.js";
import type { ContextCompileOptions } from "./context-compiler.js";
import type { ContextProfile } from "./types.js";

export interface ModelContextMetadata {
  contextWindow?: number;
  maxTokens?: number;
  provider?: string;
  id?: string;
}

export interface ContextOverrides {
  contextWindow?: number;
  maxOutputTokens?: number;
  profile?: ContextProfile | "auto";
}

export interface ResolvedModelContext extends ContextCompileOptions {
  source: "override" | "model_metadata" | "fallback";
  modelLabel: string;
}

export interface AdaptiveCompactionSettings {
  enabled: true;
  reserveTokens: number;
  keepRecentTokens: number;
}

/** Share Pi's existing output reserve; do not add a second turn-wide quota. */
export function recallPageBudget(window: number, used: number | null | undefined, output: number, index: boolean): number {
  const free = used == null ? Math.floor(window * 0.15) : window - used - resolveCompactionSettings(window, output).reserveTokens;
  return Math.max(0, Math.min(index ? 480 : 3_200, Math.floor(free)));
}

export function resolveCompactionSettings(contextWindow: number, maxOutputTokens?: number): AdaptiveCompactionSettings {
  const window = Math.floor(contextWindow);
  const output = maxOutputTokens && maxOutputTokens > 0 ? Math.floor(maxOutputTokens) : Math.floor(window * 0.15);
  const outputReserve = output + Math.max(256, Math.ceil(window * .06));
  if (output < 128 || outputReserve >= window) throw new Error('Context window cannot accommodate the configured output reserve');
  const keepRecentTokens = Math.max(512, Math.min(12_000, Math.floor(window * 0.20)));
  return { enabled: true, reserveTokens: outputReserve, keepRecentTokens };
}

export function resolveModelContext(
  model?: ModelContextMetadata,
  overrides: ContextOverrides = environmentOverrides(),
): ResolvedModelContext {
  const overrideWindow = positiveInteger(overrides.contextWindow);
  const metadataWindow = positiveInteger(model?.contextWindow);
  const contextWindow = overrideWindow ?? metadataWindow ?? FALLBACK_CONTEXT_WINDOW;
  const maxOutputTokens = positiveInteger(overrides.maxOutputTokens) ?? positiveInteger(model?.maxTokens);
  return {
    contextWindow,
    maxOutputTokens,
    profile: overrides.profile ?? "auto",
    source: overrideWindow ? "override" : metadataWindow ? "model_metadata" : "fallback",
    modelLabel: [model?.provider, model?.id].filter(Boolean).join("/") || "unknown-model",
  };
}

export function environmentOverrides(env: NodeJS.ProcessEnv = process.env): ContextOverrides {
  const profile = env.URBAN_CONTEXT_PROFILE;
  return {
    contextWindow: positiveInteger(env.URBAN_CONTEXT_WINDOW),
    maxOutputTokens: positiveInteger(env.URBAN_MAX_OUTPUT_TOKENS),
    profile: profile === "micro" || profile === "compact" || profile === "balanced" || profile === "spacious"
      ? profile
      : "auto",
  };
}

function positiveInteger(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value) && value > 0) return Math.floor(value);
  if (typeof value === "string" && value.trim()) {
    const parsed = Number.parseInt(value, 10);
    if (Number.isFinite(parsed) && parsed > 0) return parsed;
  }
  return undefined;
}
