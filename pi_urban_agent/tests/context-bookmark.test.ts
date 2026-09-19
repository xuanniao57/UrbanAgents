import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { ResearchStore } from '../src/core/research-store.js';
import { renderStateBookmark } from '../src/core/context-bookmark.js';
import { selectActiveHumanAuthorization } from '../src/core/human-patch.js';
import { buildRecoveryCapsule, recallResearchState } from '../src/core/context-memory.js';
import { CONTRACT } from './fixtures.js';
import type { PendingHumanPatch } from '../src/core/types.js';

async function fixture() {
  const store = await ResearchStore.initialize(await mkdtemp(join(tmpdir(), 'urban-bookmark-regression-')), CONTRACT);
  await store.openBranch({ nodeId: 'comparison_route', nodeType: 'parameter_route', title: 'Comparison route', decisionQuestion: 'Retain?', parameters: {}, claimBoundary: 'Sensitivity only', summary: '' });
  const s = await store.load(); s.activeBranchId = 'comparison_route'; s.phase = 'human';
  return s;
}
const pending = (): PendingHumanPatch => ({ patchId: 'patch_new', actorId: 'logged-in-user', source: 'rpc', sourceMessageHash: 'current', targetBranchIds: ['comparison_route'], proposedDecision: 'retain_sensitivity', expectedSupersedesDecisionId: 'decision_old', rawTextDigest: 'Retain this comparison', status: 'pending', createdAt: '2026-08-30T00:00:00Z' });

test('whole-field assembly preserves priority, recall entry and closing envelope under large state', async () => {
  const s = await fixture(); s.contract.researchQuestion = 'long question '.repeat(500); s.contract.prohibitedClaims = ['long constraint '.repeat(500)];
  s.pendingHumanPatches = [pending()];
  for (let i = 0; i < 100; i++) s.humanDecisions.push({ decisionId: `human_${i}`, branchIds: [`route_${i}`], decision: 'retain_sensitivity', rationale: 'long rationale '.repeat(100), actor: 'expert', createdAt: '' });
  for (const maxTokens of [256, 360, 512]) {
    const b = renderStateBookmark(s, { maxTokens, sourceMessageHash: 'current' });
    assert.match(b, /latest user message is the active instruction/);
    assert.match(b, /recall_next: urban_recall/);
    assert.ok(b.endsWith('</urban_state_bookmark>'));
    assert.ok(b.length <= maxTokens * 4);
    assert.match(b, /omitted_fields:/);
    assert.doesNotMatch(b, /\[truncated\]/);
  }
});

test('ordinary/unclassified messages never suggest a human decision write', async () => {
  const s = await fixture(); const old = pending();
  s.pendingHumanPatches = [old, { ...pending(), patchId: 'query', status: 'pending_unclassified', proposedDecision: undefined, targetBranchIds: [], sourceMessageHash: 'query' }];
  const b = renderStateBookmark(s, { sourceMessageHash: 'query' });
  assert.match(b, /pending_human_patch: none/);
  assert.doesNotMatch(b, /next_action:.*urban_human_decision/);
  assert.doesNotMatch(b, /the named target|then call/);
});

test('explicit current choice includes exact target and superseded decision, without forced all-route recall', async () => {
  const s = await fixture(); s.pendingHumanPatches = [pending()];
  const b = renderStateBookmark(s, { sourceMessageHash: 'current' });
  assert.match(b, /targets=\["comparison_route"\]/);
  assert.match(b, /supersedes=decision_old/);
  assert.match(b, /next_action:.*urban_human_decision/);
  assert.doesNotMatch(b, /Call urban_recall once|the named target/);
});

test('bookmark and tool authorization agree on the current message, not stale or consumed patches', async () => {
  const s = await fixture(); s.pendingHumanPatches = [pending()];
  assert.match(renderStateBookmark(s, { sourceMessageHash: 'read-only-message' }), /pending_human_patch: none/);
  assert.throws(() => selectActiveHumanAuthorization(s, 'retain_sensitivity', ['comparison_route'], 'read-only-message'));
  s.pendingHumanPatches[0].status = 'applied';
  assert.match(renderStateBookmark(s, { sourceMessageHash: 'current' }), /pending_human_patch: none/);
});

test('resolved review text remains historical and is not resurrected as pending', async () => {
  const s = await fixture(); s.nodes.comparison_route.status = 'retained_sensitivity';
  s.reviews = [{ reviewId: 'review_old', branchId: 'comparison_route', decision: 'escalate', requiredAction: 'Should expert retain this route?', checks: {}, rationale: '', affectedClaims: [], createdAt: '' }];
  s.pendingQuestions = []; const original = JSON.stringify(s);
  const b = renderStateBookmark(s);
  assert.match(b, /unresolved_review_action: none/);
  assert.doesNotMatch(b, /Should expert retain/);
  assert.equal(JSON.stringify(s), original);
  assert.ok(!buildRecoveryCapsule(s).openLoops.some((x) => x.includes('Should expert retain')));
  assert.equal(s.reviews.length, 1);
});

test('recall hints cannot revive unclassified or wrong-message authorization', async () => {
  const s = await fixture(); s.pendingHumanPatches = [pending()];
  assert.equal(recallResearchState(s, { scope: 'branch', ids: ['comparison_route'], detail: 'card', sourceMessageHash: 'other' }).nextAction, undefined);
  s.pendingHumanPatches[0].status = 'pending_unclassified'; s.pendingHumanPatches[0].proposedDecision = undefined;
  assert.equal(recallResearchState(s, { scope: 'branch', ids: ['comparison_route'], detail: 'card', sourceMessageHash: 'current' }).nextAction, undefined);
  assert.ok(!buildRecoveryCapsule(s).openLoops.some((x) => x.includes('AUTHENTICATED HUMAN PATCH')));
});

test('live pending questions and live repairs are not hidden by the stale-review fix', async () => {
  const s = await fixture(); s.pendingQuestions = ['Confirm the new comparison'];
  assert.match(renderStateBookmark(s), /unresolved_review_action: Confirm the new comparison/);
  s.pendingQuestions = []; s.nodes.comparison_route.status = 'repair_required';
  s.reviews = [{ reviewId: 'repair', branchId: 'comparison_route', decision: 'repair', requiredAction: 'Repair mismatched covariates', checks: {}, rationale: '', affectedClaims: [], createdAt: '' }];
  assert.match(renderStateBookmark(s), /unresolved_review_action: Repair mismatched covariates/);
});

test('oversize identifiers are omitted whole and remain recoverable by pointer', async () => {
  const s = await fixture(); const p = pending(); p.targetBranchIds = ['NODE_' + 'x'.repeat(4000)]; s.pendingHumanPatches = [p];
  const b = renderStateBookmark(s);
  assert.match(b, /pending_human_patch: explicit choice; retrieve details/);
  assert.doesNotMatch(b, /NODE_x/);
  assert.ok(b.length <= 1440);
});
