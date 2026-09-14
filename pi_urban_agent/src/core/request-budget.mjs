/** Shared transport budget. No research decisions or condition-specific policy. */
import { readFile, mkdir, writeFile, appendFile } from 'node:fs/promises';
import { resolve, relative } from 'node:path';
import { createHash } from 'node:crypto';
import { Tokenizer } from '@huggingface/tokenizers';

let tokenizerPromise;
const textCounts = new Map();
let lastCompaction;
async function tokenizer() {
  const dir = process.env.URBAN_TOKENIZER_DIR;
  if (!dir) return null;
  return tokenizerPromise ??= Promise.all(['tokenizer.json', 'tokenizer_config.json'].map(f => readFile(resolve(dir, f), 'utf8').then(JSON.parse)))
    .then(([model, config]) => new Tokenizer(model, config));
}
export async function countText(text) {
  const key = createHash('sha256').update(text).digest('hex');
  if (textCounts.has(key)) return textCounts.get(key);
  const tok = await tokenizer();
  // Without a deployment tokenizer, use a conservative UTF-8 bound, not chars/4.
  const n = tok ? tok.encode(text).ids.length : Buffer.byteLength(text, 'utf8');
  if (textCounts.size > 1024) textCounts.clear();
  textCounts.set(key, n);
  return n;
}
export function requestLimits(window, output) {
  if (!Number.isFinite(window) || window < 1024) throw new Error('Budget configuration: missing/invalid deployed context window');
  const margin = Math.max(256, Math.ceil(window * .06));
  const reserve = Math.floor(output);
  if (reserve < 128 || reserve + margin >= window) throw new Error('Budget configuration: insufficient room for useful output');
  return { window, output: reserve, margin, input: window - reserve - margin };
}
export async function countContext(context) {
  // Count actual content and schemas with the deployment vocabulary. Explicit
  // overhead and margin cover provider formatting; this is NOT exact chat-template counting.
  let total = 32 + await countText(context.systemPrompt ?? '');
  if (context.tools?.length) total += 128 + await countText(JSON.stringify(context.tools));
  for (const m of context.messages) total += 32 + await countText(JSON.stringify({ role: m.role, content: m.content, toolCallId: m.toolCallId, toolName: m.toolName }));
  return total;
}
function budgetRoot() {
  return resolve(process.env.URBAN_BUDGET_LOG_DIR ?? process.env.URBAN_PI_RUN_DIR ?? '.urban-budget', 'request-budget');
}
async function archive(value) {
  const content = JSON.stringify(value);
  const root = process.env.URBAN_PI_WORKSPACE_ROOT ? resolve(process.env.URBAN_PI_WORKSPACE_ROOT, '.research-history') : budgetRoot();
  const path = resolve(root, `${createHash('sha256').update(content).digest('hex')}.json`);
  await mkdir(root, { recursive: true });
  await writeFile(path, content, 'utf8');
  return process.env.URBAN_PI_WORKSPACE_ROOT ? relative(process.env.URBAN_PI_WORKSPACE_ROOT, path).replaceAll('\\', '/') : path;
}
async function record(value) {
  await mkdir(budgetRoot(), { recursive: true });
  await appendFile(resolve(budgetRoot(), 'events.jsonl'), JSON.stringify({ time: new Date().toISOString(), ...value }) + '\n');
}
function textOf(message) {
  return typeof message.content === 'string' ? message.content : (message.content ?? []).filter(b => b.type === 'text').map(b => b.text).join('\n');
}
async function reduceToolBodies(context, limit) {
  for (let i = 0; i < context.messages.length && await countContext(context) > limit; i++) {
    const m = context.messages[i];
    if (m.role !== 'toolResult' || await countText(textOf(m)) < 350) continue;
    const path = await archive(m);
    let pointer = { archived_tool_result: path, tool: m.toolName, isError: m.isError ?? false };
    // Keep the stable envelope rather than guessing which tail substring is useful.
    try {
      const body = JSON.parse(textOf(m));
      for (const k of ['result_path', 'manifest_path', 'path', 'next_offset', 'has_more', 'exit_code', 'status']) {
        if (body[k] !== undefined) pointer[k] = body[k];
      }
    } catch { /* Full text is available at archived_tool_result. */ }
    context.messages[i] = { ...m, content: [{ type: 'text', text: JSON.stringify(pointer) }] };
  }
}

/** Calls Pi's unchanged summary prompts via summarize; send is the raw stream. */
export async function streamWithBudget(model, original, options, send, summarize) {
  const window = Number(process.env.URBAN_CONTEXT_WINDOW ?? model.contextWindow);
  const configured = Number(process.env.URBAN_MAX_OUTPUT_TOKENS ?? model.maxTokens);
  const requested = options?.maxTokens ?? configured;
  const isSummary = (original.systemPrompt ?? '').startsWith('You are a context summarization assistant.');
  // A compaction product is an index into archived history, not another long
  // answer. Bound it relative to the deployed window so 4B through API-scale
  // models use the same policy without a fixed 1024-token failure mode.
  const summaryCap = Math.max(192, Math.min(configured, Math.floor(window * .125)));
  const limits = requestLimits(window, Math.min(requested, configured, isSummary ? summaryCap : Number.POSITIVE_INFINITY));
  let context = { ...original, messages: original.messages.map(m => ({ ...m,
    _budgetKey: createHash('sha256').update(JSON.stringify({role:m.role,content:m.content,timestamp:m.timestamp})).digest('hex') })) };
  const before = await countContext(context);
  if (!isSummary && lastCompaction?.root === budgetRoot()) {
    const matches = context.messages.filter(m => lastCompaction.keys.has(m._budgetKey));
    if (matches.length === lastCompaction.keys.size) {
      const first = context.messages.findIndex(m => lastCompaction.keys.has(m._budgetKey));
      context.messages.splice(first, 0, lastCompaction.message);
      context.messages = context.messages.filter(m => !lastCompaction.keys.has(m._budgetKey));
    } else lastCompaction = undefined; // Native compaction or branch change invalidated the prefix.
  }
  if (!isSummary) await reduceToolBodies(context, limits.input);

  if (await countContext(context) > limits.input && isSummary) {
    // Pi serializes summary inputs inside <conversation>. Partition ONLY that
    // source text, preserving its prompt and existing summary. No recursive retries.
    const source = textOf(context.messages[0]);
    const start = source.indexOf('<conversation>\n'), end = source.lastIndexOf('\n</conversation>');
    if (context.messages.length !== 1 || start < 0 || end < 0) throw new Error('Budget configuration: oversized summary source has no supported conversation boundary');
    const prefix = source.slice(0, start + '<conversation>\n'.length);
    const suffix = source.slice(end);
    let remaining = source.slice(prefix.length, end);
    const chunks = [], partials = [];
    while (remaining.length) {
      let lo = 0, hi = remaining.length;
      while (lo < hi) {
        const mid = Math.ceil((lo + hi) / 2);
        const candidate = { ...context, messages: [{ ...context.messages[0], content: [{ type: 'text', text: prefix + remaining.slice(0, mid) + suffix }] }] };
        if (await countContext(candidate) <= limits.input) lo = mid; else hi = mid - 1;
      }
      if (lo < 64) throw new Error('Budget configuration: summary instructions alone leave no usable source budget');
      const chunk = { ...context, messages: [{ ...context.messages[0], content: [{ type: 'text', text: prefix + remaining.slice(0, lo) + suffix }] }] };
      chunks.push(chunk);
      remaining = remaining.slice(lo);
    }
    // Allocate ONE synthesis-input budget across ALL partial summaries. Giving
    // every chunk an independent output allowance recreates the original bug.
    const emptySynthesis = { ...context, messages: [{ ...context.messages[0], content: [{ type: 'text', text: prefix + suffix }] }] };
    const synthesisRoom = limits.input - await countContext(emptySynthesis) - 128;
    // Reserve the aggregate synthesis input conservatively. Partial summaries
    // may tokenize less efficiently than their source, especially when the
    // deployment tokenizer is unavailable during bootstrap.
    const perChunk = Math.min(limits.output, Math.floor(synthesisRoom / (chunks.length * 2)) - 8);
    if (perChunk < 128) throw new Error('Budget configuration: too many source chunks for useful summaries; archive or narrow source input');
    await record({event:'summary_plan',chunks:chunks.length,synthesisRoom,perChunk,allocatedOutput:chunks.length*perChunk});
    for (const chunk of chunks) {
      const chunkOptions = { ...options, maxTokens: perChunk };
      await record({ event: 'summary_chunk', input: await countContext(chunk), output: chunkOptions.maxTokens, window });
      const result = await (await send(model, chunk, chunkOptions)).result();
      if (result.stopReason === 'error' || result.stopReason === 'aborted') throw new Error(result.errorMessage ?? 'Summary chunk did not complete');
      partials.push(textOf(result));
    }
    context.messages = [{ ...context.messages[0], content: [{ type: 'text', text: prefix + partials.join('\n\n') + suffix }] }];
    // Keep a final check for provider/tokenizer differences; never silently crop.
    if (await countContext(context) > limits.input) throw new Error('Budget configuration: chunk summaries exceed summary synthesis capacity');
  }

  if (await countContext(context) > limits.input && !isSummary) {
    // Preserve the latest human message byte-for-byte and the latest assistant
    // tool-call group. Summarize the older prefix using Pi's existing algorithm.
    let lastUser = -1, lastAssistant = -1;
    context.messages.forEach((m, i) => { if (m.role === 'user' && m !== lastCompaction?.message) lastUser = i; if (m.role === 'assistant') lastAssistant = i; });
    const tailStart = Math.max(lastUser, lastAssistant, 0);
    const prefix = context.messages.filter((_, i) => i < tailStart && i !== lastUser);
    const user = lastUser >= 0 && lastUser < tailStart ? [context.messages[lastUser]] : [];
    const tail = context.messages.slice(tailStart);
    const fixed = { ...context, messages: [...user, ...tail] };
    const room = limits.input - await countContext(fixed) - 96;
    if (!prefix.length || room < 256) throw new Error('Budget configuration: system, tools and latest user/tool group cannot fit; reduce static configuration or page this input');
    const archivePath = await archive(prefix);
    const compactOutput = Math.min(summaryCap, room);
    const proposed = await summarize(prefix, compactOutput);
    const proposedTokens = await countText(proposed);
    const capped = proposedTokens >= compactOutput - 8;
    const roleCounts = prefix.reduce((counts, message) => {
      const role = message.role ?? 'unknown';
      counts[role] = (counts[role] ?? 0) + 1;
      return counts;
    }, {});
    const fallback = `history_status: archived_not_in_context\narchived_messages: ${prefix.length}\nroles: ${JSON.stringify(roleCounts)}\nrecovery: Read the archive only if the current task requires an omitted chronological detail; use authoritative runtime state for research facts.`;
    const empty = !proposed.trim();
    const summary = empty ? fallback : proposed.trim();
    const message = { role: 'user', content: [{ type: 'text', text: `[Pi history checkpoint schema=1.0; full_history=${archivePath}; summary_status=${empty ? 'deterministic_fallback' : capped ? 'possibly_incomplete' : 'complete'}; verify research facts against saved records]\n${summary}` }], timestamp: Date.now() };
    const keys = new Set(prefix.flatMap(m => m === lastCompaction?.message ? [...lastCompaction.keys] : [m._budgetKey]));
    lastCompaction = { root: budgetRoot(), keys, message };
    context.messages = [message, ...user, ...tail];
    await record({ event: 'preflight_compaction', archivedPrefix: archivePath, summary, summaryCap: compactOutput, proposedTokens, capped, keptLatestUser: lastUser >= 0 });
  }
  const after = await countContext(context);
  await record({ event: 'request_check', kind: isSummary ? 'summary' : 'agent', before, inputTokens: after, ...limits,
    countMode: process.env.URBAN_TOKENIZER_DIR ? 'deployment-vocabulary-plus-format-overhead' : 'utf8-conservative' });
  if (after > limits.input) throw new Error(`Budget configuration: fitted input ${after} still exceeds ${limits.input}; request NOT sent`);
  // Saved usage belongs to the original prefix, not this reconstructed request.
  // Do not let Pi's secondary estimator reapply stale usage and clamp to 1 token.
  context.messages = context.messages.map(m => {
    const { _budgetKey, ...visible } = m;
    return m.role === 'assistant' ? { ...visible,
      usage: { ...m.usage, input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0 } } : visible;
  });
  return send(model, context, { ...options, maxTokens: limits.output });
}
