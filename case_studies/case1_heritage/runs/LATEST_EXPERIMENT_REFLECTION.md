# Latest Experiment Reflection

Latest raw run: `20260509_174939_c6_vanilla_t3`.

## What Happened

This run is the vanilla baseline: planning, review, quality control, dual-space
diagnostics, and memory are all disabled. It finished quickly (`23.63s`) with a
low estimated cost (`$0.40925`), but it produced no review score, no execution
confidence, no review warnings, and no artifacts. It still reports `success=true`
because the current success flag mainly checks runtime completion rather than
evidence quality.

## Interpretation

The result is useful as a speed/cost baseline, but it is too weak as a paper
claim by itself. The strongest signal is not raw success rate, because every
condition currently reports 1.0 success. The more persuasive comparison is:

- full UrbanAgent produces confidence/review/runtime traces and more metric rows;
- vanilla produces a short answer and metric rows but lacks verification,
  artifact production, confidence, and cumulative memory reuse;
- disabling memory, dual-space, review, or QC should be evaluated through
  evidence completeness, error detection, artifact validity, and correction
  reuse rather than only completion.

## Risks In Current Protocol

- `success=true` is too permissive and hides quality differences.
- Full mode has higher latency and cost, so the paper needs a quality-normalized
  metric rather than a raw speed table.
- `review_score=1.0` appears saturated in several conditions, reducing ablation
  contrast.
- Some formal trials report more artifacts when review is disabled, which could
  be misread unless artifact validity is scored separately.

## Next Experiment Adjustments

1. Replace binary success with a composite score: evidence completeness, artifact
   validity, computability correctness, reviewer-detected issue count, and
   correction-memory reuse.
2. Add a deliberately flawed input condition: AOI-clipped OSM, mismatched CRS,
   missing street-view metadata, or absent function labels. This will test
   whether review and dual-space diagnostics catch real failures.
3. Separate artifact count from artifact validity. Count only artifacts with
   readable paths, expected layers, CRS, feature counts, and metric linkage.
4. Add a memory-transfer experiment: run Case1 first, then 20 similar heritage
   districts, and report whether workflow memory reduces missing evidence,
   unsupported claims, and rerun count.
5. Report a quality-cost frontier: full mode should justify extra latency by
   producing auditable artifacts, lower unsupported-claim rate, and reusable
   correction memory.
