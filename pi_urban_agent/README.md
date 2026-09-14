# Urban Agent v2.2 — Pi-native runtime

Urban Agent v2 is a clean Pi runtime for reviewable, scale-sensitive urban
analysis. Pi owns the dialogue session, model protocol, tool loop, session
branching, and compaction lifecycle. Urban Agent adds a separate, persistent
Urban Research Git Tree for scientific decisions and evidence.

The primary runtime no longer imports Hermes. Existing Python analysis scripts
remain reusable through a small bounded subprocess bridge, but personal-assistant
memory, Hermes prompts, and the Hermes tool registry are not loaded.

## Three completed migration stages

1. **Pi foundation and vertical slice** — typed research state, immutable data
   contract, hashed artifacts, serialized and atomic state transactions, a
   bounded Python bridge, and a migrated Shanghai scale-sensitivity run.
2. **Research-aware context management** — Pi keeps chronological dialogue
   compaction, while a short action bookmark points to the external Research
   Git Tree. Exact branches return on demand through bounded `urban_recall`
   evidence cards. Recall, checkpoints, route-decision supersession, and
   compaction remain auditable without serializing the whole tree every turn.
3. **Governed execution** — isolated Worker and Reviewer packets, explicit human
   checkpoints, deterministic finalization, checkpoint scoring, and a standalone
   frontend record.

See [CONTEXT_MANAGEMENT.md](CONTEXT_MANAGEMENT.md) for the full design.

## Install and verify

```powershell
cd D:\GitHub_1\world_agent\urban-mobility-agent\paper4_urban_svgagent\pi_urban_agent
npm install
npm run validate
```

`npm run validate` performs TypeScript checking, invariant tests, a Python bridge
check, a Worker/Reviewer packet check, and deterministic finalization.

## Start an interactive run

Kimi Code:

```powershell
.\run_pi_urban.ps1 -RunDir D:\urban_runs\scale_case_01
```

Qwen served by vLLM:

```powershell
$env:VLLM_BASE_URL = "http://127.0.0.1:8000/v1"
$env:VLLM_API_KEY = "local-vllm"
.\run_pi_urban.ps1 `
  -RunDir /root/autodl-tmp/urban_runs/scale_case_01 `
  -Provider local-vllm `
  -Model Qwen3-30B-A3B-FP8
```

The first turn exposes only `urban_initialize`. Once a contract exists, tools
change with the phase; the model does not receive every schema on every turn.

The same runtime can serve API frontier models and local Qwen 30B/8B/4B
deployments. Pi supplies the active model's context metadata automatically. For
a local server whose declared limits are inaccurate, use deployment overrides:

```powershell
.\run_pi_urban.ps1 `
  -RunDir D:\urban_runs\small_model_case `
  -Provider local-vllm `
  -Model Qwen3-8B `
  -ContextWindow 16384 `
  -MaxOutputTokens 4096 `
  -ContextProfile auto
```

Do not select a context profile from parameter count alone. Use the actual
window configured by the provider or vLLM server.

Local Qwen3.5-9B on a 12GB NVIDIA GPU through Ollama:

```powershell
ollama pull qwen3.5:9b
ollama create qwen3.5:9b-urban16k -f .\local_models\qwen35_9b_urban16k.Modelfile
.\run_pi_urban.ps1 `
  -RunDir D:\urban_runs\qwen35_local `
  -Provider local-ollama `
  -Model qwen3.5:9b-urban16k `
  -ContextWindow 16384 `
  -MaxOutputTokens 4096
```

The official model may support a much longer context, but the configured
runtime window must reflect available VRAM. For the local 12GB target, 16k is
the conservative default used by this project.

Run the deterministic multi-window stress test and a real local-model recovery
test against a completed Research Git Tree:

```powershell
npm run context:stress
npm run context:local-eval -- `
  --source-run "..\experiments\case2_multiscale_gwr_20260815\pi_runtime_v2_20260824_final" `
  --output-dir "..\experiments\context_recovery_qwen35_9b_20260824" `
  --provider local-ollama `
  --model qwen3.5:9b-urban16k `
  --context-window 16384 `
  --max-output-tokens 4096
```

The local evaluation records the JSONL model trace, exact recall events,
stderr, GPU/Ollama snapshots, and an evaluation summary in the output run.

## Run isolated roles

After the Planner creates a Worker packet and moves the state to `execute`:

```powershell
npm run role -- --role worker --run-dir D:\urban_runs\scale_case_01 --provider local-vllm --model Qwen3-30B-A3B-FP8
```

After evidence is attached and a Reviewer packet is created:

```powershell
npm run role -- --role reviewer --run-dir D:\urban_runs\scale_case_01 --provider local-vllm --model Qwen3-30B-A3B-FP8
```

Each role runs in a fresh Pi process. Its context is reconstructed from the
active research branch rather than inheriting the Planner's entire chat.

## Reconstruct the current Shanghai record

```powershell
npm run migrate:shanghai -- "..\experiments\case2_multiscale_gwr_20260815\pi_runtime_v2_new"
```

This does not rerun the models. It imports the existing verified CSV artifacts,
hashes them, records the reviewed/human decisions, and creates:

- `research_state.json`
- `research_events.jsonl`
- `checkpoint_submission.json`
- `evidence_manifest.json`
- `route_tree_frontend_state.json`
- `research_route_viewer.html`

Open `research_route_viewer.html` directly in a browser to inspect the record.

## Shared Python tool contract

Urban and the Pi-default-compaction control load the same `urban_python` tool.
For file inspection use `{"method":"inspect_csv","arguments":{"path":"/absolute/data.csv","limit":3}}`.
For script execution use:

```json
{"method":"run_script","arguments":{"script":"/absolute/analysis.py","args":["--action","inventory"]}}
```

`script` is one existing file, never inline Python or a shell command. `args`
is an array of separate string tokens; do not put `action`, `model` or other CLI
flags at top level. Working directory defaults to the script's parent; use
absolute output paths when targeting a separate research run. Unknown fields,
wrong argument shapes and nonzero script exits produce real tool errors. An
exit-zero result still requires scientific review; a preview is not the full
artifact. See `long_case/tool_manifest.json` for the case CLI and units.

## Core directories

- `src/core/` — research state, context compiler, tool policy, packets, frontend
- `src/pi-extension.ts` — Pi extension and native lifecycle hooks
- `python/urban_tool_server.py` — bounded Python operations without Hermes
- `.pi/extensions/urban-agent.ts` — project-local Pi entry point
- `scripts/` — smoke, role runner, and Shanghai migration
- `tests/` — state, context, phase-policy, and finalization invariants

The previous Hermes runtime remains elsewhere in the repository only as a
historical baseline for ablation and result comparison.
