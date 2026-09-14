/** Explicit wire compatibility: local Ollama is not the OpenAI server. */
export function applyProviderCompatibility(provider: string, model: Record<string, unknown>): Record<string, unknown> {
  if (provider !== "local-ollama") return { ...model };
  return {
    ...model,
    compat: { ...(model.compat as object ?? {}), maxTokensField: "max_tokens", supportsStore: false, supportsDeveloperRole: false },
    thinkingLevelMap: { off: "none", ...(model.thinkingLevelMap as object ?? {}) },
  };
}

export function normalizeProviderPayload(provider: string | undefined, value: unknown): unknown {
  if (provider !== "local-ollama" || !value || typeof value !== "object") return value;
  const payload = { ...(value as Record<string, unknown>) };
  if (typeof payload.max_completion_tokens === "number") {
    payload.max_tokens ??= payload.max_completion_tokens;
    delete payload.max_completion_tokens;
  }
  return payload;
}
