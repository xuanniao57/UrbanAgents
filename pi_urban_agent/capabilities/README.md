# Research figures are evidence artifacts

The Pi-native runtime can execute declared Python/GIS plotting recipes through
`urban_python(method="run_script")` and bind their outputs with
`urban_attach_evidence`. No Hermes runtime or additional inference service is
required. The capability index is read on demand; the system prompt points to
the index without loading figure data into every model context.

## Current case recipe

Read `index.json`, then `shanghai_scale_figures.json`. Resolve its paths against
the `paper4_urban_svgagent` repository directory. The recipe reads the corrected
saved experiment, does not refit models or change source data, and refuses to
overwrite an existing output directory.

| Evidence | Figure/table | Input | Research use |
|---|---|---|---|
| Aligned support and shared regions | Figure 4 | Grid geometry and macro-region assignments | Check comparison geography |
| Separate OLS/adaptive/fixed trajectories | Figure 5 | Full 77-route results | Inspect support and neighbourhood sensitivity |
| Global coefficient trajectories | Figure 6 | Full eight-predictor OLS fits | Compare global association changes |
| Full 8-variable by 7-support maps | Figure 7 | Full-model local coefficients at fixed 7 km | Inspect where signs and magnitudes change |
| OLS-only summary | Table 2 | OLS results and cell-coverage ledger | Compare supports without bandwidth-selected GWR rows |

Use a Worker packet to pass the recipe, input contract and expected outputs.
After execution, inspect the manifest and `exit_code`, attach the manifest and
key figures, call `urban_set_phase` with `review`, then create the Reviewer
packet. Technical checks do not authorize an urban interpretation or preferred
scale. The manifest contains every vector/raster export and GIS layer with its
hash, so only a compact set of pointers needs to enter model context.

## Reproducible capability check

With the project's Python GIS environment configured as `URBAN_PI_PYTHON`:

```text
npx tsx scripts/verify-case-figure-tools.ts <new-run-directory>
```

This is a scripted replay of the **production extension callbacks**, Python
bridge and ResearchStore. It has no LLM calls and is not an autonomous research
benchmark. The initial local verification required a corrected execute-to-review
transition; it resumed from existing outputs without rerendering or deleting the
record. The final script includes that explicit transition.

The verification records tool arguments/results, source/export hashes, the
Worker/Reviewer packets and artifact links. The 30 August run reproduced all
eight PNG groups byte-for-byte, produced 34 files, and made no human decision.
The recipe's layout and model contract are case-specific; another research
question should supply another declared recipe rather than silently applying
the Shanghai settings.
