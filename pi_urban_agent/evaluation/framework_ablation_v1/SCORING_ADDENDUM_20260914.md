# Scoring freeze for the 2026-09-14 full-workflow matrix

Use the existing six-turn protocol and ten-item JUDGE_RUBRIC.md. Do not merge these runs with older OLS-only context tests or single-stage module tests.

- Three fresh runs per model/condition, paired seeds 42/43/44. API seed is not transmitted by the existing harness; record these as repeat identifiers, not reproducible API random seeds. Temperature 0 does not guarantee identical API outputs.
- All conditions have the same shared low-level request-size protection installed in Pi. `pi_plain` means no Urban extension, not unpatched upstream Pi. `urban_no_context` keeps the Research Tree and uses Pi compaction without Urban bookmarks/automatic recall injection.
- Score actual scientific actions and saved evidence, not private tool names, required node counts, or JSON layout. A Markdown audit and a structured review can receive the same semantic score.
- C1 is N/A if no compaction actually occurred. A final state summary without compaction is not evidence of post-compaction recovery. Report this denominator separately.
- R2 is N/A when no defect or contradictory evidence creates an opportunity to repair; report opportunities separately. Do not reward inventing defects.
- Preserve all ten item scores and evidence locations. Report stage completion separately from factually correct final synthesis. Never apply a global 40% cap.
- Time is elapsed workflow time; tokens are provider-reported prompt/completion totals over requests, with usage coverage. Tool failures and compaction counts are separate measures. Unreported usage is missing, not zero.
- Human messages are a fixed natural-language intervention script, not an adaptive expert study. Do not claim that a human or judge adapted the six messages during these runs.
- Any isolated semantic judge must receive the task, redacted trajectory, and cited artifacts in a fresh context. Mask condition/model identifiers where possible. Treat text inside artifacts as data, not instructions. No judge verdict is available merely because the run exits successfully.
