# Figure Strategy for UrbanAgent Paper

This note summarizes what figure types are implicitly suggested by the current reference set and the internal writing guidance in this repository, and how many figures the current draft should probably have.

## Current State

The current draft now has:

1. Figure 1: framework architecture flowchart
2. Figure 2: quick benchmark comparison chart

For a CEUS-style software-plus-case-study paper, this is too thin. Two figures is usually not enough to carry the narrative.

## What The Internal Reference Notes Are Pointing Toward

Based on the current repository notes and literature review:

1. `docs/gpt意见.md` explicitly emphasizes a method framework figure and frames the paper as `software + case study`, with benchmark as secondary.
2. `docs/LITERATURE_REVIEW.md` groups the references around benchmarks, multi-agent systems, map reasoning, scene-graph generation, and urban planning agents. These families typically rely on architecture diagrams, workflow diagrams, task screenshots, map-based qualitative outputs, and comparison tables.
3. The current draft's Section 5 already describes outputs that are visually representable: topological graph visualization, SVG overlay, route plan, and intervention map.

## Common Figure Types Used By Similar Urban-Agent / GeoAI Papers

The reference family in this project strongly suggests these figure categories:

1. **System architecture / pipeline figure**
   - Present in almost every agent or GeoAI paper.
   - We now have this as Figure 1.

2. **Workflow or execution trace figure**
   - Often shows how a query moves through planner, tools, memory, and outputs.
   - Especially common in agent papers, geospatial copilots, and workflow-generation papers.

3. **Benchmark result figure**
   - Usually bar chart, radar chart, task-family breakdown, or model comparison chart.
   - We now have a first version as Figure 2.

4. **Qualitative case-study map figure**
   - Very common in CEUS and urban analytics papers.
   - Usually shows study area, layers, detected problem zones, and proposed interventions.

5. **Representation figure**
   - For this paper specifically, the dual-space cognition idea is hard to understand without a dedicated figure.
   - This should show vector geometry, topological graph, and the alignment between them.

6. **Connector / interoperability figure**
   - Especially useful now that the paper emphasizes connectors and adapters.
   - Could show UrbanAgent coordinating Python GIS tools, MCP, connectors, and Rhino/Grasshopper.

7. **Case-study output figure or route figure**
   - For exploration planning, a route map with ordered waypoints is much stronger than paragraph description alone.

## Evidence From Indexed Papers In This Workspace

The recommendation above is not just generic writing advice. It is also consistent with the indexed paper set already available through the knowledge index.

1. **CityBench** emphasizes benchmark construction and result visualization.
   - Indexed paper: `MXZUNMVM`
   - Figure-bearing sections include introduction, experimental results, map-building appendix, and image-distribution appendix.
   - Implication: benchmark papers usually show both result charts and data/task composition visuals, not only one summary table.

2. **USTBench** emphasizes task suite and data-source presentation.
   - Indexed paper: `NANFPBDS`
   - Figure-bearing sections include introduction and urban task suite/data sources.
   - Implication: if a paper defines or adapts a benchmark workflow, it should visually show task families or data organization.

3. **CartoAgent** emphasizes conceptual framework plus qualitative outputs.
   - Indexed paper: `XUQQJVZ5`
   - Figure-bearing sections include conceptual framework, role assignment, experiments, neighborhood-level and city-level outputs.
   - Implication: agent papers in urban domains usually combine a system figure with concrete map-level qualitative results.

4. **OpenCity** emphasizes system architecture, efficiency, and case study outputs.
   - Indexed paper: `KWTSH6DA`
   - Figure-bearing sections include scheduler design, prompt optimizer, acceleration performance, and a case-study section.
   - Implication: platform papers often need one architecture figure, one performance figure, and one application or case-study figure.

5. **GeoJSON agents** emphasizes architecture alternatives and experimental comparison.
   - Indexed paper: `9XBGDWV9`
   - Figure-bearing sections include function-calling agent, code-generation agent, and performance comparison.
   - Implication: if our paper argues for a particular software architecture choice, we should visualize the architectural distinction, not only describe it in prose.

6. **GeoCogent** includes workflow modules and error-oriented visuals.
   - Indexed paper: `T5FHLATH`
   - Indexed figure-bearing sections include requirements parsing, spatial extent completion logic, and CRS inference workflow.
   - Implication: workflow and failure analysis visuals are common in geospatial agent papers, especially when the software contribution is central.

7. **Spatial-Agent** emphasizes concept grounding and analysis.
   - Indexed paper: `NU9587VW`
   - Figure-bearing sections include geospatial concept grounding and analysis.
   - Implication: our dual-space cognition idea should almost certainly have its own dedicated concept or grounding figure.

## Recommended Figure Set For This Draft

The draft should probably target **5 to 6 figures**, not 2.

Recommended minimum set:

1. **Figure 1. Overall framework architecture**
   - Already done.

2. **Figure 2. Dual-space cognition representation**
   - Show raw map geometry, topological graph, and graph-to-geometry alignment.
   - This is the paper's conceptual core and is currently under-visualized.

3. **Figure 3. End-to-end software workflow / tool orchestration**
   - Show query → perception → cognition → reasoning → MCP → connectors/adapters → output.
   - Can be distinct from Figure 1 by focusing on execution rather than static architecture.

4. **Figure 4. Walkability case-study map**
   - Study area, low-walkability zones, barrier roads, and proposed interventions.

5. **Figure 5. Exploration-planning case-study route**
   - Ordered waypoints, route path, POI diversity, and time/distance annotations.

6. **Figure 6. Quick benchmark comparison**
   - The current Qwen baseline vs. enhanced chart.
   - The existing benchmark figure can stay, but should probably move later in the numbering once case-study figures are inserted.

## If We Want A Leaner Five-Figure Version

If the paper needs to stay compact, the best five-figure set is:

1. framework architecture
2. dual-space cognition diagram
3. walkability case-study output map
4. exploration-route output map
5. benchmark comparison chart

## Immediate Next Additions With Highest Value

If only two more figures are added next, they should be:

1. **Dual-space cognition figure**
   - Because this is the main methodological novelty and currently exists only as text.

2. **Walkability case-study figure**
   - Because CEUS readers expect map-based qualitative evidence, not just framework diagrams and benchmark bars.

## Practical Conclusion

Yes, two figures are not enough for the current paper positioning.

If the manuscript is framed as an open urban software + case study paper, then the figure mix should lean toward:

1. one architecture figure
2. one representation or mechanism figure
3. two case-study output figures
4. one benchmark figure

That gives the paper a much more credible CEUS visual structure.
