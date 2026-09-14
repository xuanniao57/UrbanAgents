import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { ResearchStore } from '../src/core/research-store.js';
import { recallResearchState } from '../src/core/context-memory.js';
import { recallPageBudget } from '../src/core/model-context.js';
import { renderStateBookmark } from '../src/core/context-bookmark.js';
import extension from '../src/pi-extension.js';
import { CONTRACT } from './fixtures.js';

async function fixture() {
  const store = await ResearchStore.initialize(await mkdtemp(join(tmpdir(), 'urban-recall-wire-')), CONTRACT);
  for (let i = 0; i < 9; i++) await store.openBranch({ nodeId: `route_${i}`, nodeType: 'model_route', title: `Route ${i}`, parentIds: ['research_object'], decisionQuestion: 'Compare?', parameters: { support_m: 200 + 100 * i, bandwidth_distance_m: 12000 }, claimBoundary: 'Association only.' });
  await store.recordHumanDecision({ branchIds: ['route_0'], decision: 'select_main', rationale: 'Reviewed', actor: 'expert' });
  await store.recordHumanDecision({ branchIds: ['route_1'], decision: 'retain_sensitivity', rationale: 'Reviewed', actor: 'expert' });
  return { store, state: await store.load() };
}

test('wire pages are complete JSON, preserve cursor and visit every record once', async () => {
  const { state } = await fixture();
  const ids: string[] = []; let cursor: string | undefined;
  do {
    const page = recallResearchState(state, { scope: 'tree', tokenLimit: 400, cursor, sourceMessageHash: 'runtime-only' });
    const wire = JSON.stringify(page);
    assert.ok(Math.ceil(wire.length / 4) <= 400);
    assert.doesNotMatch(wire, /runtime-only|excludeIds/);
    assert.equal(JSON.parse(wire).effectiveRange, 'all');
    assert.ok(page.records.length > 0);
    ids.push(...page.records.map((r: any) => r.nodeId));
    cursor = page.nextCursor;
    assert.equal(page.hasMore, !!cursor);
  } while (cursor);
  assert.equal(ids.length, Object.keys(state.nodes).length);
  assert.equal(new Set(ids).size, ids.length);
});

test('oversize evidence is explicitly not loaded, can be retried, and cursors reject changed queries/state', async () => {
  const { state } = await fixture();
  state.nodes.route_0.parameters.large = 'x'.repeat(4000);
  const request = { scope: 'branch' as const, ids: ['route_0'], detail: 'full' as const, dependencyDepth: 0, tokenLimit: 450 };
  const page = recallResearchState(state, request);
  assert.equal(page.records.length, 0); assert.equal(page.hasMore, true);
  assert.equal(page.oversizedRecord?.id, 'route_0');
  assert.ok(JSON.stringify(page).length <= 450 * 4);
  const retried = recallResearchState(state, { ...request, cursor: page.nextCursor, tokenLimit: 2500 });
  assert.equal(retried.records.length, 1); assert.equal(retried.hasMore, false);
  assert.throws(() => recallResearchState(state, { ...request, ids: ['route_1'], cursor: page.nextCursor }), /cursor/);
  state.stateVersion = (state.stateVersion ?? 0) + 1;
  assert.throws(() => recallResearchState(state, { ...request, cursor: page.nextCursor }), /cursor/);
});

test('human-decision current/all ranges are explicit and indexing does not replace evidence reading', async () => {
  const { state } = await fixture(); state.activeBranchId = 'route_1';
  const current = recallResearchState(state, { scope: 'human_decision' });
  assert.equal(current.effectiveRange, 'route_1'); assert.equal(current.records.length, 1);
  const all = recallResearchState(state, { scope: 'human_decision', range: 'all' });
  assert.equal(all.effectiveRange, 'all'); assert.equal(all.records.length, 2);
  const index = recallResearchState(state, { scope: 'tree' });
  const first = (index.records[0] as any).nodeId;
  const read = recallResearchState(state, { scope: 'branch', ids: [first], detail: 'card', dependencyDepth: 0 });
  assert.ok((read.records[0] as any).parameters);
  const batch = recallResearchState(state, { scope: 'branch', ids: ['route_0', 'route_1'], dependencyDepth: 1, tokenLimit: 2000 });
  assert.equal(batch.records.filter((r: any) => r.nodeId === 'research_object').length, 1);
});

test('page headroom depends on remaining context, not a 655-token turn quota', () => {
  assert.equal(recallPageBudget(8192, 4000, 2048, false), 1652);
  assert.equal(recallPageBudget(8192, 4500, 2048, false), 1152);
  assert.equal(recallPageBudget(8192, 4000, 2048, true), 480);
  assert.equal(recallPageBudget(8192, 8100, 2048, false), 0);
  assert.equal(recallPageBudget(8192, null, 2048, false), 1228);
});

test('extension keeps recovery tool schemas stable, returns idempotent receipts and never re-truncates recall JSON', async () => {
  const { state } = await fixture();
  const old = process.env.URBAN_PI_RUN_DIR; process.env.URBAN_PI_RUN_DIR = state.runDir;
  const tools = new Map<string, any>(); const handlers = new Map<string, any[]>(); let activeTools: string[] = [];
  try { extension({ on: (name: string, cb: any) => handlers.set(name, [...(handlers.get(name) ?? []), cb]), registerTool: (tool: any) => tools.set(tool.name, tool), setActiveTools: (names: string[]) => { activeTools = names; } } as any); }
  finally { if (old === undefined) delete process.env.URBAN_PI_RUN_DIR; else process.env.URBAN_PI_RUN_DIR = old; }
  const ctx = { model: { contextWindow: 8192, maxTokens: 2048 }, getContextUsage: () => ({ tokens: 3000 }) };
  const call = (name: string, params: any) => tools.get(name).execute('test', params, undefined, undefined, ctx);
  const focused = JSON.parse((await call('urban_state', {})).content[0].text);
  assert.ok(activeTools.includes('urban_state')); assert.ok(activeTools.includes('urban_recall'));
  const repeatedState = JSON.parse((await call('urban_state', {})).content[0].text);
  assert.equal(repeatedState.status, 'already_loaded');
  assert.match(repeatedState.remaining_action, /already present/i);
  const inspected = JSON.parse((await call('urban_state', { branch_id: 'research_object' })).content[0].text);
  assert.equal(inspected.current_focus_node_id, focused.current_focus_node_id);
  assert.equal(inspected.inspected_node.node_id, 'research_object');
  assert.match(renderStateBookmark(state), /current_focus_node_id:/);
  await assert.rejects(call('urban_state', { branch_id: 'active_branch_id' }), /urban_state \{\}/);
  await call('urban_recall', { scope: 'tree' });
  let output = await call('urban_recall', { scope: 'branch', range: 'all', detail: 'card', token_limit: 2000 });
  assert.ok(activeTools.includes('urban_state')); assert.ok(activeTools.includes('urban_recall'));
  const originalText = output.content[0].text;
  assert.ok(originalText.length > 3200, 'exercise former global 800-token truncation');
  for (const cb of handlers.get('tool_result') ?? []) {
    const update = await cb({ toolName: 'urban_recall', ...output, isError: false }, ctx);
    if (update) output = { ...output, ...update };
  }
  assert.equal(output.content[0].text, originalText);
  const result = JSON.parse(originalText);
  assert.ok(result.records.length > 0); assert.equal(result.currentFocusNodeId, state.activeBranchId);
  assert.equal(result.status, 'loaded');
  const repeatedRecall = JSON.parse((await call('urban_recall', { scope: 'branch', range: 'all', detail: 'card', token_limit: 2000 })).content[0].text);
  assert.equal(repeatedRecall.status, 'already_loaded');
  assert.equal(repeatedRecall.records, undefined);
  assert.match(repeatedRecall.remaining_action, /synthesize/i);
});
