# Urban Analysis Dogfood Skill

Use the `urban` toolset as a workflow harness, not as isolated utilities.

Default sequence:

1. Call `urban_ground_task` before analysis.
2. If the question is an early-stage research design, call `urban_research_memory` and use recalled lessons as cues, not as fixed rules.
3. On Windows-native runs, inspect local `D:/...` or `C:/...` files with `urban_host_fs`; run small local preparation/check scripts with `urban_host_python`. Do not reinterpret native paths as Linux paths.
4. Use operator tools such as `urban_fetch_osm`, `urban_analyze_connectivity`, `urban_measure_accessibility`, `urban_calculate_density`, `urban_build_topology`, `urban_generate_svg_overlay`, and `urban_export_geojson` as needed.
5. When real GIS intermediate artifacts are required, prefer `urban_qgis_process` over merely drafting a script. Report the command log and verified output paths.
6. Call `urban_review` before presenting final urban claims.
7. When the user corrects a spatial assumption, spatial unit, data source, scale, stakeholder caveat, variable operationalization, or rerun rule, call `urban_record_feedback`, `urban_research_memory(action="record")`, or the memory provider tool `urban_memory_record`.

The three required review surfaces are input grounding, reasoning review, and feedback reuse.

Domain-memory stance:

- AOI/context-buffer separation is a research-design lesson. Recall it when the task involves study areas, historical districts, or surrounding context; do not hard-code it as mandatory for every task.
- For built-environment X variables and perception/social-media Y variables, consider grid, street-segment, or block units to align observations and avoid one-record-per-district designs when that would make modeling weak.
- If a run provides native Windows paths and needs artifacts, treat path access as a host-execution problem, not a WSL problem. Use `urban_host_fs`, `urban_host_python`, and `urban_qgis_process` first.
