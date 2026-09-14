# Current Pi-native framework snapshot — 2026-09-14

This is a development snapshot, not a claim of completed formal evaluation.

## Included

Pi-native runtime; general file/terminal execution; isolated research workspace; persistent Research Tree, indexed evidence cards and batch recall; Planner and Worker–Reviewer workflow; authenticated human decisions and supersession; context budgeting and archival; Python bridge; invariant tests; functional evaluation protocols. The existing frontend source is maintained separately under `frontend/urban_hermes_route_viewer`.

## Latest minimal recall changes

- Nonempty summaries near the output limit are retained and labelled possibly incomplete instead of always discarded.
- Summary budget is proportional to the configured model window and bounded by its output budget.
- Archived history/tool results use workspace-relative `.research-history/` references.
- Repeated `read` calls are allowed for recovery. State-changing repeated calls retain protection.
- No new current-work-note component was added.

TypeScript checking and 13 focused budget/recall tests passed. The local 4B pilot was interrupted at the user's request before the comparison completed. It exposed invalid OLS code and execution timeouts; one observed summary ended mid-sentence despite not reaching the local token threshold. Summary completeness/fidelity therefore still needs verification. Do not describe this snapshot as solving all recovery failures.

## Resume later

Use the six-stage OLS-only scientific task: plan, execute OLS, inspect evidence, apply the human role correction, read exact results, recover current state. Do not extend it to GWR execution when comparing the context/Planner/Reviewer components. Functional pilot prompts avoid requiring private tool names; they are not identical to the historical tool-specific prompt version.

Local tests are paused and must not restart automatically. Preserve interrupted output as administrative interruption, not model failure. Start new output directories on user-authorized resumption.

API preflight returned HTTP 403 for both configured Qwen endpoints with application proxy disabled and WLAN routing. Confirm endpoint entitlement before another API run; do not attribute this to framework performance.

## Installation and private configuration

From `pi_urban_agent`, install Node 22 dependencies with `npm ci` (postinstall applies the shared Pi budget patch). Copy `.pi-agent/models.example.json` to `.pi-agent/models.json` and configure the model actually served. Keep credentials in environment variables/private ignored files. Configure `URBAN_PI_PYTHON` to an absolute Python interpreter path for experiment sessions.

Case inputs, tokenizer/model caches, private provider configuration and raw experiment traces are intentionally excluded from Git. Obtain these separately in the authorized research environment. The historical `long_case` analysis helper is not injected as a recipe by the general-workspace experiment harness.
