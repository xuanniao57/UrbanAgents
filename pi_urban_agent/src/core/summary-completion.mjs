import { countContext, requestLimits } from './request-guard.mjs';

/** Keep Pi's checkpoint writer concise; never persist a length-truncated summary. */
export async function completeCheckpoint(context, options, send) {
  const usage = {};
  for (const fraction of [0.45, 0.22]) {
    // Summary output is a ceiling, unlike the research request's output budget.
    // Fit source + instructions + checkpoint together before calling transport.
    const window = Number(process.env.URBAN_CONTEXT_WINDOW);
    let cap = options.maxTokens;
    if (Number.isFinite(window)) {
      const { margin } = requestLimits(window, cap);
      const available = window - margin - await countContext(context) - 256;
      cap = Math.min(cap, Math.floor(available));
      if (cap < 128) throw new Error('Pi summary source leaves no room for a complete checkpoint request.');
    }
    const target = Math.max(32, Math.floor(cap * fraction));
    const instruction = `Write a compact checkpoint, targeting at most ${target} tokens. Preserve the latest user authorization, current verified state, unresolved blockers and next action. Replace obsolete details instead of accumulating history. Use short bullets and file references; omit code, tables and repeated attempts. Preserve exact constraints without guessing. Finish all sections within the target.`;
    const response = await send({ ...context, systemPrompt: `${context.systemPrompt ?? ''}\n\n${instruction}` }, { ...options, maxTokens: cap });
    for (const [key, value] of Object.entries(response.usage ?? {})) {
      if (typeof value === 'number') usage[key] = (usage[key] ?? 0) + value;
    }
    if (response.stopReason !== 'length') return { ...response, usage: { ...response.usage, ...usage } };
  }
  throw new Error('Pi checkpoint remained output-truncated after a concise retry; original history retained.');
}
