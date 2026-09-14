import { readFile, readdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';

const dir = resolve(process.argv[2]);
const pages: any[] = []; const seen = new Set<string>();
for (const file of (await readdir(dir)).filter(f => /^request_\d+\.json$/.test(f)).sort((a,b) => Number(a.match(/\d+/)![0])-Number(b.match(/\d+/)![0]))) {
  const payload = JSON.parse(await readFile(resolve(dir, file), 'utf8'));
  const names = new Map<string, string>();
  for (const m of payload.messages ?? []) {
    for (const call of m.tool_calls ?? []) names.set(call.id, call.function.name);
    if (m.role !== 'tool' || seen.has(m.tool_call_id)) continue;
    const name = names.get(m.tool_call_id);
    if (name !== 'urban_recall' && name !== 'urban_state') continue;
    seen.add(m.tool_call_id);
    try {
      const data = JSON.parse(m.content);
      pages.push({ firstSeen: file, tool: name, validJson: true, chars: m.content.length,
        estimatedTokens: Math.ceil(m.content.length / 4), tokenLimit: data.request?.tokenLimit,
        withinBudget: !data.request?.tokenLimit || Math.ceil(m.content.length / 4) <= data.request.tokenLimit,
        hasMore: data.hasMore, nextCursor: data.nextCursor, oversizedRecord: data.oversizedRecord,
        range: data.effectiveRange, recordIds: data.records?.map((r: any) => r.nodeId ?? r.decisionId ?? r.artifactId ?? r.node?.nodeId),
        focus: data.currentFocusNodeId ?? data.current_focus_node_id, inspectedNode: data.inspected_node,
        pendingQuestions: data.pending_questions });
    } catch {
      pages.push({ firstSeen: file, tool: name, validJson: false, errorText: m.content });
    }
  }
}
const sources = ['src/core/context-memory.ts','src/core/context-bookmark.ts','src/core/model-context.ts','src/core/types.ts','src/pi-extension.ts'];
const sourceHashes = Object.fromEntries(await Promise.all(sources.map(async p => [p,createHash('sha256').update(await readFile(p)).digest('hex')])));
const result = { kind: 'actual_model_visible_tool_text_not_semantic_score', pages, sourceHashes };
await writeFile(resolve(dir,'recall_wire_audit.json'), JSON.stringify(result,null,2));
console.log(JSON.stringify({dir,pages}));
