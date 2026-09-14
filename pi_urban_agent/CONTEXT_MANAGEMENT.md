# Urban Agent v2.2 context-management strategy

## 1. Two trees, two responsibilities

Pi's session tree stores conversation turns and enables dialogue branching,
navigation, and compaction. It is not the scientific record. The Urban Research
Git Tree stores the immutable research contract, analytical alternatives,
parameters, evidence artifacts, review gates, human decisions, and claim limits.

The two structures are linked only by a small Pi custom entry containing the
research run directory, run ID, active branch, phase, and contract hash. Pi
custom entries are persistent but are not sent to the model. On resume, Urban
Agent reloads the structured state from disk and reconstructs the relevant view.
`research_state.json` is the sole scientific source of truth; Markdown recovery
views and Pi summaries are disposable projections of that state.

## 2. A short invariant system prompt

The primary system prompt defines role boundaries and invariants, not a
catalogue of urban methods. Each turn receives only a short action bookmark:
state version, active node, unresolved review action, latest route decision,
claim ceiling, and the next allowed action. The complete Research Tree is not
automatically injected.

Long-term personal memory is disabled by default. Previous studies or decisions
are retrieved only when an artifact or explicit reference in the active research
state requests them.

## 3. Model-adaptive token allocation

No context window is hard-coded into the research architecture. On every Pi
turn, Urban Agent reads the active model's `contextWindow` and `maxTokens`
metadata. It then selects a policy from the window size rather than from the
model name or parameter count:

| Effective window | Automatic profile | Checkpoint/recall budget |
|---:|---|---|
| up to 8k | `micro` | short bookmark; small evidence-card pages |
| 8k--24k | `compact` | short bookmark; moderate evidence-card pages |
| 24k--64k | `balanced` | short bookmark; broader explicit recall budget |
| above 64k | `spacious` | short bookmark; larger recall pages, still capped |

Each profile reserves output and tokenizer safety first. The remainder is
allocated among the invariant prompt, phase-specific tool schemas, recall
results, and recent dialogue. The bookmark remains small at every window size;
larger deployments can retrieve broader evidence pages without changing the
authoritative scientific state.

Pi metadata is normally sufficient. If a local vLLM deployment exposes
incorrect metadata, deployment-level overrides are available:

```text
URBAN_CONTEXT_WINDOW
URBAN_MAX_OUTPUT_TOKENS
URBAN_CONTEXT_PROFILE=auto|micro|compact|balanced|spacious
```

Overrides change prompt compilation only. They do not modify the research tree.
The launchers also materialize a run-local Pi `models.json`, so Pi's own
compaction threshold and Urban Agent's compiler use the same effective limits.
The source model registry is not mutated.

## 4. Bookmark-first, on-demand Research Tree recall

Every model call receives a fresh `urban_state_bookmark`. The bookmark tells the
model where it is and how to retrieve authoritative detail, but does not attempt
to summarize every branch. When a decision depends on prior work, the preferred
two-step path is:

1. `urban_recall(scope='tree', detail='digest')` returns a bounded index of
   stable node IDs;
2. `urban_recall(scope='branch', ids=[...], detail='card')` returns compact,
   exact evidence cards for the required routes.

Tree-index calls are capped at 640 tokens and cannot return full records.
Multi-branch full requests are automatically reduced to evidence cards, whose
fields include node ID, parameters, exact artifact metrics, review outcome,
human route role, and claim boundary. An unqualified branch, artifact, review,
or human-decision recall defaults to the active node. Full tables and raw logs
remain external artifacts.

The recall layer is deliberately deterministic. Stable IDs and graph
dependencies are primary; a bounded lexical query is only a convenience. An
embedding database or a second LLM-generated memory graph is not required for
correctness. This keeps the same mechanism usable with API frontier models and
4B--9B local models.

## 5. Large outputs are artifacts, not chat messages

Python operations return at most a bounded preview. Complete CSV, JSON, model,
map, and log outputs remain on disk. `urban_attach_evidence` hashes the file and
binds it to the branch that produced it. Pi tool-result `details` retain the
structured response for inspection, while the LLM-visible text is capped.

Evidence paths may be absolute, run-directory relative, or repository relative.
The extension resolves the two relative scopes explicitly before hashing, so a
task artifact under `data/evidence/` is not accidentally searched for inside the
run-state directory.

This prevents one large grounding result or model table from consuming the
remaining window. It also prevents a diagnostic from being accidentally applied
to a sibling route.

## 6. Dynamic tool exposure

All tools are registered with Pi, but `setActiveTools()` exposes only the current
phase subset:

| Phase | Exposed capabilities |
|---|---|
| plan | initialize/read state, open a branch, create Worker packet |
| execute | run bounded Python, attach evidence, create Worker packet |
| review | create Reviewer packet, record one review gate |
| human | record explicit human choices |
| finalize | read state and finalize only |
| complete | read-only state inspection |

A `tool_call` hook also enforces the policy, so a stale model-generated call is
blocked even if a UI has not refreshed yet. Invalid phase jumps are rejected by
the state store.

Mutating calls are serialized per research directory even when Pi issues
several independent tool calls in parallel. Each mutation reloads the latest
authoritative state inside the serialized transaction, validates invariants,
and writes a temporary file before an atomic rename. This prevents lost branch
updates and prevents readers from observing a partially written JSON document.
The append-only event ledger is updated in the same transaction.

## 7. Research-aware Pi compaction and recovery

Pi triggers automatic compaction when
`contextTokens > contextWindow - reserveTokens`, or after a provider overflow;
the user can also invoke `/compact`. Urban Agent writes run-local Pi settings so
`reserveTokens` and `keepRecentTokens` scale with the deployed model window
instead of inheriting Pi's 16k/20k defaults. At 16,384 tokens, for example, both
values are 3,276; at 4,096 they are 819.

Urban Agent observes `session_before_compact`, writes a structured checkpoint of
the authoritative state, and then lets Pi perform its normal chronological
dialogue compaction. It no longer replaces Pi's summary with a second Research
Tree summary. After compaction, the next turn receives the same short bookmark;
scientific facts return only through explicit recall. This avoids duplicated
summaries and makes a failed recall visible in the tool trace.

Each compaction writes:

- `checkpoints/context_checkpoint_*.json` — machine-readable recovery capsule;
- `views/recovery_capsule.md` — human-readable derived view;
- `logs/context_manifest.jsonl` — tokens before/after, state version, checkpoint
  node IDs, omitted counts, recall events, and trigger reason.

This makes compression itself auditable while keeping the scientific state
independent of summary quality, session restart, model switch, or dialogue-tree
navigation.

The `session_before_tree` hook applies the same rule when the user navigates to a
different Pi dialogue branch. Repeated injected context packets are deduplicated
by the `context` hook. The Research Git Tree remains independent of whichever Pi
conversation branch is currently visible.

## 8. Compression triggers beyond token pressure

Token pressure is not the only relevant event. The current implementation also
recompiles or checkpoints context at these boundaries:

- every model turn: recompile the active state and phase-specific tool set;
- state mutation: increment a monotonic `stateVersion`;
- Pi tree navigation: write a fresh recovery checkpoint;
- large evidence: keep the artifact external and inject only a bounded pointer;
- explicit recall: log which omitted records re-entered working context.

This avoids a monolithic background memory agent. Scientific state changes are
handled structurally; ordinary short dialogue remains Pi's responsibility.

## 9. Worker and Reviewer isolation

A Worker receives a packet containing one branch, its dependency path, expected
artifacts, contract hash, and execute-only tools. A Reviewer receives a fresh
packet containing the same contract hash, the branch evidence manifest, and
review questions. The Reviewer does not inherit the Worker's chain of thought or
the Planner's unrelated conversation.

The supplied role runner launches each role in a fresh Pi process. This preserves
the clean ReAct loop while preventing long multi-role conversations from
accumulating in one context.

## 10. Human authorization and finalization

Reviewer outcomes are limited to `proceed`, `repair`, `new_branch`, `block`, and
`escalate`. They change executable state. Human decisions are separately typed as
main-route selection, sensitivity retention, comparison request, deferral,
blocking, or claim approval. Silence is never interpreted as approval.

Finalization requires at least one hashed artifact, one review record, and one
human checkpoint. It then writes the checkpoint submission, evidence manifest,
frontend state, and a self-contained browser viewer. The state becomes immutable,
and only the read-state tool remains active.

## 11. What has been deliberately removed

- automatic injection of a personal long-term-memory profile;
- the 29k-character general workflow prompt;
- the 23-tool all-at-once schema surface;
- full tool outputs copied into model context;
- free-form `node_type` and status strings;
- automatic merging of raw conversation histories;
- repeated LLM summarization of already-compressed scientific state;
- embedding retrieval as a correctness-critical dependency;
- a late-stage prose request that merely asks the model to remember to finalize.

The resulting strategy is hybrid and retrieval-led: Pi manages chronological
conversation; Urban Agent stores scientific provenance externally; the bookmark
maintains action orientation; and the model recalls only the records needed for
the next decision.
