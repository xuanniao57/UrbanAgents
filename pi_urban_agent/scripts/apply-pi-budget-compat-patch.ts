import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

// Narrow, reproducible compatibility patch shared by BOTH evaluated frameworks.
// It does not replace Pi's summarizer or Research Tree injection.
const target = resolve("node_modules/@earendil-works/pi-coding-agent/node_modules/@earendil-works/pi-ai/dist/api/simple-options.js");
const before = "const available = model.contextWindow - estimateContextTokens(context).tokens - CONTEXT_SAFETY_TOKENS;";
const after = "const safetyTokens = Math.min(CONTEXT_SAFETY_TOKENS, Math.max(256, Math.floor(model.contextWindow * 0.05)));\n    const available = model.contextWindow - estimateContextTokens(context).tokens - safetyTokens;";
const source = await readFile(target, "utf8");
if (source.includes(after)) console.log("Pi output-budget compatibility patch already applied");
else {
  if (source.split(before).length !== 2) throw new Error("Upstream changed: refuse unverified budget patch");
  await writeFile(target, source.replace(before, after));
  console.log("Applied window-scaled safety margin; model output cap remains unchanged");
}

// Overflow-only recovery shared by all conditions. Normal/manual compaction is unchanged.
const sessionPath = resolve('node_modules/@earendil-works/pi-coding-agent/dist/core/agent-session.js');
let session = await readFile(sessionPath, 'utf8');
const recoveryImport = `import { prepareOverflowCompaction } from ${JSON.stringify(pathToFileURL(resolve('src/core/pi-compaction-recovery.mjs')).href)};`;
const recoveryMarker = '// urban-shared-overflow-recovery-v1';
if (session.includes(recoveryMarker)) {
  session = session.replace(/import \{ prepareOverflowCompaction \} from ["']file:\/\/\/[^"']*\/src\/core\/pi-compaction-recovery\.mjs["'];/, recoveryImport);
} else {
  const start = session.indexOf('    async _runAutoCompaction(reason, willRetry) {');
  if (start < 0) throw new Error('Upstream auto-compaction changed');
  const head = session.slice(0, start);
  let tail = session.slice(start);
  const old = 'const preparation = prepareCompaction(pathEntries, settings);\n            if (!preparation) {\n                return false;\n            }';
  if (!tail.includes(old)) throw new Error('Upstream compaction preparation changed');
  tail = tail.replace(old, `const preparation = reason === "overflow"
                ? prepareOverflowCompaction(pathEntries, settings, prepareCompaction, estimateTokens)
                : prepareCompaction(pathEntries, settings);
            if (!preparation) {
                if (reason === "overflow") this._emit({ type: "compaction_end", reason, result: undefined, aborted: false, willRetry: false, errorMessage: "Context overflow: no compressible history or summary remains; reduce static context/output reservation or use a larger window." });
                return false;
            }`);
  const append = '            this.sessionManager.appendCompaction(summary, firstKeptEntryId, tokensBefore, details, fromExtension, usage);';
  if (!tail.includes(append)) throw new Error('Upstream compaction persistence changed');
  tail = tail.replace(append, `            if (preparation.overflowSummaryOnly && estimateTokens({ role: "user", content: summary, timestamp: 0 }) >= estimateTokens({ role: "user", content: preparation.previousSummary, timestamp: 0 })) {
                throw new Error("Summary-only overflow recovery did not reduce the summary; refusing a futile retry.");
            }
` + append);
  session = `${recoveryMarker}\n${recoveryImport}\n` + head + tail;
}
await writeFile(sessionPath, session);

// A split summary is two responses concatenated by Pi, not two independent
// allowances. Size their combined result against the reconstructed suffix.
session = await readFile(sessionPath, 'utf8');
const jointImport = `import { fitCompactionBudget } from ${JSON.stringify(pathToFileURL(resolve('src/core/pi-compaction-recovery.mjs')).href)};`;
if (!session.includes('// urban-joint-summary-budget-v1')) {
  session = session.replace('import { CURRENT_SESSION_VERSION, getLatestCompactionEntry }', 'import { CURRENT_SESSION_VERSION, getLatestCompactionEntry, buildSessionContext }');
  const beforePrepare='const preparation = reason === "overflow"';
  if(session.split(beforePrepare).length!==2)throw new Error('Upstream automatic preparation changed');
  session=session.replace(beforePrepare,'let preparation = reason === "overflow"');
  const afterPrepare=': prepareCompaction(pathEntries, settings);\n            if (!preparation) {';
  if(session.split(afterPrepare).length!==2)throw new Error('Upstream preparation validation changed');
  session=session.replace(afterPrepare,`: prepareCompaction(pathEntries, settings);
            preparation = await fitCompactionBudget(preparation, pathEntries, settings, requestModel, this.agent.state, prepareCompaction, estimateTokens, buildSessionContext, convertToLlm);
            if (!preparation) {`);
  session=`// urban-joint-summary-budget-v1\n${jointImport}\nimport { convertToLlm } from './messages.js';\n`+session;
} else {
  session=session.replace(/import \{ fitCompactionBudget \} from ["']file:\/\/\/[^"']*\/src\/core\/pi-compaction-recovery\.mjs["'];/,jointImport);
}
await writeFile(sessionPath,session);

// Pi's split-turn path must retain its previous summary when no new history exists.
const compactionPath = resolve('node_modules/@earendil-works/pi-coding-agent/dist/core/compaction/compaction.js');
let compaction = await readFile(compactionPath, 'utf8');
const oldHistory = 'if (messagesToSummarize.length > 0) {';
const keepHistory = 'if (messagesToSummarize.length > 0 || previousSummary) {';
if (!compaction.includes(keepHistory)) {
  if (compaction.split(oldHistory).length !== 2) throw new Error('Upstream split-turn summary changed');
  compaction = compaction.replace(oldHistory, keepHistory);
  await writeFile(compactionPath, compaction);
}

// Checkpoint writing gets the whole summary allowance for its text. Keep the
// research agent's reasoning level unchanged; supported providers map off to
// an explicit 'none' so the transport cannot silently re-enable thinking.
const summaryThinking='if (model.reasoning && thinkingLevel && thinkingLevel !== "off") {\n        options.reasoning = thinkingLevel;\n    }';
const summaryNoThinking='// urban-summary-text-budget-v1: no reasoning budget for checkpoint writing';
if(!compaction.includes(summaryNoThinking)) {
  if(compaction.split(summaryThinking).length!==2)throw new Error('Upstream summarization options changed');
  compaction=compaction.replace(summaryThinking,summaryNoThinking);
  await writeFile(compactionPath,compaction);
}

// One bounded retry of Pi's SAME checkpoint request if output was truncated.
// Never feed the partial summary back as source or persist it as a checkpoint.
const checkpointImport = `import { completeCheckpoint } from ${JSON.stringify(pathToFileURL(resolve('src/core/summary-completion.mjs')).href)};`;
if (!compaction.includes('// urban-complete-checkpoint-v1')) {
  const oldCall = 'return retryAssistantCall(produce, retry, requestOptions.signal, callbacks);';
  if (compaction.split(oldCall).length !== 2) throw new Error('Upstream summary completion changed');
  compaction = compaction.replace(oldCall, `return completeCheckpoint(context, requestOptions, async (checkpointContext, checkpointOptions) => {
        const call = async () => streamFn
            ? (await streamFn(model, checkpointContext, checkpointOptions)).result()
            : completeSimple(model, checkpointContext, checkpointOptions);
        return retryAssistantCall(call, retry, checkpointOptions.signal, callbacks);
    });`);
  compaction = `// urban-complete-checkpoint-v1\n${checkpointImport}\n` + compaction;
} else {
  compaction = compaction.replace(/import \{ completeCheckpoint \} from ["']file:\/\/\/[^"']*\/src\/core\/summary-completion\.mjs["'];/, checkpointImport);
}
await writeFile(compactionPath, compaction);

// Small checkpoints cannot carry Pi's cumulative, seven-section template.
// Change the instructions, not the original conversation being summarized.
const compactPromptImport = `import { COMPACT_CHECKPOINT_PROMPT } from ${JSON.stringify(pathToFileURL(resolve('src/core/checkpoint-prompt.mjs')).href)};`;
if (!compaction.includes('// urban-small-checkpoint-prompt-v1')) {
  const oldPrompt = 'let basePrompt = previousSummary ? UPDATE_SUMMARIZATION_PROMPT : SUMMARIZATION_PROMPT;';
  if(compaction.split(oldPrompt).length!==2)throw new Error('Upstream checkpoint prompt changed');
  compaction=compaction.replace(oldPrompt,'let basePrompt = maxTokens < 2048 ? COMPACT_CHECKPOINT_PROMPT : (previousSummary ? UPDATE_SUMMARIZATION_PROMPT : SUMMARIZATION_PROMPT);');
  compaction=`// urban-small-checkpoint-prompt-v1\n${compactPromptImport}\n`+compaction;
} else {
  compaction=compaction.replace(/import \{ COMPACT_CHECKPOINT_PROMPT \} from ["']file:\/\/\/[^"']*\/src\/core\/checkpoint-prompt\.mjs["'];/,compactPromptImport);
}
await writeFile(compactionPath,compaction);

// The Urban preflight already reserves the whole requested output. Do not
// clamp it a second time using Pi's different context estimate. Native calls
// without this per-request marker retain Pi's original clamp.
const optionsSource = await readFile(target, 'utf8');
const nativeClamp = 'maxTokens: clampMaxTokensToContext(model, context, options?.maxTokens ?? model.maxTokens),';
const checkedClamp = 'maxTokens: options?.urbanPreflightChecked ? options.maxTokens : clampMaxTokensToContext(model, context, options?.maxTokens ?? model.maxTokens),';
if (!optionsSource.includes(checkedClamp)) {
  if (optionsSource.split(nativeClamp).length !== 2) throw new Error('Upstream output clamp changed');
  await writeFile(target, optionsSource.replace(nativeClamp, checkedClamp));
}

// One shared stream boundary covers main calls AND Pi's summary subrequests.
const sdkPath = resolve('node_modules/@earendil-works/pi-coding-agent/dist/core/sdk.js');
let sdk = await readFile(sdkPath, 'utf8');
const marker = '// urban-shared-request-budget-v1';
const budgetImport = `import { streamWithBudget } from ${JSON.stringify(pathToFileURL(resolve('src/core/request-guard.mjs')).href)};`;
if (sdk.includes(marker)) {
  const importPattern = /import \{ streamWithBudget \} from ["']file:\/\/\/[^"']*\/src\/core\/request-(?:budget|guard)\.mjs["'];/;
  if (!importPattern.test(sdk)) throw new Error('Existing request-budget marker has no recognized absolute import; refuse unchecked rewrite');
  const corrected = sdk.replace(importPattern, budgetImport);
  if (corrected !== sdk) {
    await writeFile(sdkPath, corrected);
    console.log('Updated shared request-budget import for the current deployment path');
  } else console.log('Shared request-budget import already points to the current deployment path');
} else {
  const start = 'return modelRuntime.streamSimple(model, context, {';
  const end = '            });\n        },\n        onPayload:';
  if (sdk.split(start).length !== 2 || sdk.split(end).length !== 2) throw new Error('Upstream SDK changed: refuse unchecked request-budget patch');
  sdk = sdk.replace(start, 'const send = (model, context, options) => modelRuntime.streamSimple(model, context, {');
  sdk = sdk.replace(end, `            });
            const budgetStream = (m, c, o) => streamWithBudget(m, c, o, send, async (prefix, cap) => {
                const result = await generateSummaryWithUsage(prefix, { ...m, maxTokens: cap }, Math.ceil(cap / 0.8), o?.apiKey, o?.headers, o?.signal, undefined, undefined, undefined, budgetStream);
                return result.text;
            });
            return budgetStream(model, context, options);
        },
        onPayload:`);
  sdk = `${marker}\n${budgetImport}\nimport { generateSummaryWithUsage } from './compaction/compaction.js';\n` + sdk;
  await writeFile(sdkPath, sdk);
  console.log('Applied shared request preflight; Pi summary prompt and cut policy unchanged');
}
