import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

// Narrow, reproducible compatibility patch shared by BOTH evaluated frameworks.
// It does not alter Pi's summarizer, cut points, or Research Tree injection.
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

// One shared stream boundary covers main calls AND Pi's summary subrequests.
const sdkPath = resolve('node_modules/@earendil-works/pi-coding-agent/dist/core/sdk.js');
let sdk = await readFile(sdkPath, 'utf8');
const marker = '// urban-shared-request-budget-v1';
const budgetImport = `import { streamWithBudget } from ${JSON.stringify(pathToFileURL(resolve('src/core/request-budget.mjs')).href)};`;
if (sdk.includes(marker)) {
  const importPattern = /import \{ streamWithBudget \} from ["']file:\/\/\/[^"']*\/src\/core\/request-budget\.mjs["'];/;
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
