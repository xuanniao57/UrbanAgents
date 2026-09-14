import { readFile, readdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';

const dir = resolve(process.argv[2]);
const requests = [];
for (const name of (await readdir(dir)).filter((f) => /^request_\d+\.json$/.test(f)).sort((a, b) => Number(a.match(/\d+/)![0]) - Number(b.match(/\d+/)![0]))) {
  const p = JSON.parse(await readFile(resolve(dir, name), 'utf8'));
  const system = p.messages?.find((m: any) => m.role === 'system')?.content;
  if (typeof system !== 'string' || !system.includes('<urban_state_bookmark')) continue;
  const b = system.slice(system.indexOf('<urban_state_bookmark'));
  const next = b.split('\n').find((l) => l.startsWith('next_action:')) ?? '';
  const pending = b.split('\n').find((l) => l.startsWith('pending_human_patch:')) ?? '';
  requests.push({ file: name, bookmarkChars: b.length, estimatedTokens: Math.ceil(b.length / 4),
    priorityIntact: b.includes('instruction_priority: The latest user message is the active instruction.'),
    recallEntryIntact: b.includes('recall_next: urban_recall'), completeEnvelope: b.endsWith('</urban_state_bookmark>'),
    withinSameBudget: b.length <= 1440, pending, next,
    noUnclassifiedWriteSuggestion: !/unparsed|the named target/.test(b) && !(pending === 'pending_human_patch: none' && next.includes('urban_human_decision')),
    unresolved: b.split('\n').find((l) => l.startsWith('unresolved_review_action:')),
    active: b.split('\n').find((l) => l.startsWith('current_focus_node_id:') || l.startsWith('active_node:')),
  });
}
const sources = ['src/core/context-bookmark.ts', 'src/core/state-obligations.ts', 'src/core/context-compiler.ts', 'src/core/context-memory.ts', 'src/core/human-patch.ts', 'src/pi-extension.ts'];
const hashes = Object.fromEntries(await Promise.all(sources.map(async (f) => [f, createHash('sha256').update(await readFile(f)).digest('hex')])));
const result = { kind: 'wire_projection_audit_not_task_success_score', sourceHashes: hashes, requests,
  allWireChecksPass: requests.length > 0 && requests.every((r) => r.priorityIntact && r.recallEntryIntact && r.completeEnvelope && r.withinSameBudget && r.noUnclassifiedWriteSuggestion),
};
await writeFile(resolve(dir, 'bookmark_wire_audit.json'), JSON.stringify(result, null, 2));
console.log(JSON.stringify({ dir, requests: requests.length, allWireChecksPass: result.allWireChecksPass, lastRequest: requests.at(-1) }));
