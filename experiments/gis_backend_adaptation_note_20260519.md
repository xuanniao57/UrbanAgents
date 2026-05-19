# GIS Backend Adaptation Note: QGIS Desktop, ArcGIS Pro, and QGIS Web

Date: 2026-05-19

Concrete implementation architecture: `paper4_urban_svgagent/docs/gis_tool_extension_architecture.md`.

## 1. Bottom Line

If the collaborator only has ArcGIS Pro, the fastest reliable path is **not** to force local QGIS installation. We should make Urban-Hermes GIS output backend-agnostic:

1. Keep the current common artifact contract: GeoJSON/GPKG/CSV + style metadata + `spatial_reasoning_manifest.json`.
2. Use `plugins/gis_backends/qgis_desktop` as the canonical QGIS Desktop backend: `.qgz` + PNG preview + independent validation JSON.
3. Use `plugins/gis_backends/arcgis_pro` as the ArcGIS Pro backend: ArcPy runtime probe + FileGDB import + validation JSON; full `.aprx`/PNG/PDF export requires a `template_aprx`.
4. Add QGIS Web / browser map as a lightweight visual-review backend later, preferably via MapLibre/Leaflet first, not by requiring a full QGIS Server stack.

For the collaborator package, the rule should be:

> If QGIS is unavailable but ArcGIS Pro is installed, run the ArcGIS Pro packager/validator. Return ArcGIS `.aprx`, exported map images, file geodatabase, and validation JSON instead of QGIS `.qgz`.

## 2. What We Have Already Built For Local QGIS

### 2.1 Urban-Hermes Tool Surface

Current Urban-Hermes registers two QGIS-specific tools in `urban_hermes.tools`:

- `urban_qgis_workspace`
- `urban_qgis_process`

`urban_qgis_workspace` packages completed GIS outputs into a QGIS workspace. It expects an experiment `run_dir`, then creates or invokes a packager script. For the built-in case it uses `scripts/package_case1_qgis_workspace.py`; for other cases it accepts a custom `packager_script`.

`urban_qgis_process` calls QGIS Processing algorithms through `qgis_process`, e.g. `native:fixgeometries`, `native:lineintersections`, etc. It records the command, stdout/stderr tails, generated output paths, and output verification into a JSONL log.

### 2.2 QGIS Runtime Detection

The runtime searches standard Windows paths:

```text
C:/Program Files/QGIS 3.40.11/bin/python-qgis-ltr.bat
C:/Program Files/QGIS 3.40.11/bin/qgis_process-qgis-ltr.bat
```

It also supports explicit overrides through arguments or environment variables:

```text
QGIS_PYTHON / QGIS_PYTHON_PATH
QGIS_PROCESS / QGIS_PROCESS_PATH
```

Important lesson: do not import `qgis` from a normal conda Python. Use QGIS-bundled Python.

### 2.3 Project Generation

We learned that hand-writing `.qgs` XML is fragile. QGIS Desktop may open with an empty layer panel even when the XML looks plausible. The reliable path is:

1. Run QGIS-bundled Python.
2. Use PyQGIS API: `QgsVectorLayer`, `QgsProject.addMapLayer`, renderers, `project.write()`.
3. Reopen the written `.qgz` through `QgsProject.read()`.
4. Validate `write_ok`, `read_ok`, and `reopen_layer_count` instead of trusting the process exit code alone.

Current generator code lives in:

```text
plugins/qgis/qgis_project_gen.py
plugins/qgis/qgis_tools.py
```

### 2.4 Live QGIS Bridge

We also have a QGIS live-control concept:

```text
plugins/qgis/qgis_bridge.py
web/app.py
web/static/js/app.js
```

The bridge exposes a local HTTP server inside QGIS at:

```text
http://127.0.0.1:8766
```

UrbanAgent Web can check `/status`, send `/commands`, and queue commands if QGIS is offline. This is useful for demos but is not the main evidence path. The paper evidence should rely on file artifacts and independent validation, not GUI state.

### 2.5 Independent QGIS Validation

We have an independent validator in the Case2 package:

```text
experiments/case2_tester_package/qgis_validation/validate_case_qgis.py
```

It must be run with QGIS Python:

```powershell
& 'C:/Program Files/QGIS 3.40.11/bin/python-qgis-ltr.bat' validate_case_qgis.py <CASE_DIR> --output artifact_validation_independent.json
```

It checks:

- `.qgs/.qgz` readability
- invalid layers
- missing datasources
- renderer field bindings, especially graduated symbol renderers
- basemap ordering
- metric CSV row counts and fields
- `spatial_reasoning_manifest.json` consistency

Key validation fields:

```text
qgis_read_ok
invalid_layers
missing_datasources
renderer_bound_fields
missing_core_renderer_fields
manifest.missing_paths
needs_correction
```

### 2.6 Current QGIS Evidence Rules

The current evidence standard is:

1. A map claim is not valid just because the report says it exists.
2. Layer names alone are insufficient.
3. Metric values in CSV alone are insufficient when they are spatially attributable.
4. A formal GIS artifact should include:
   - source/context layers
   - AOI-clipped analysis layers
   - computed metric layers
   - style or renderer metadata
   - manifest entries
   - independent QGIS read validation

## 3. ArcGIS Pro Adaptation

### 3.1 Recommended Role For ArcGIS Pro

ArcGIS Pro should first be treated as an **artifact backend and validator**, not as a live UI controller. The collaborator has ArcGIS Pro, so we can produce ArcGIS-native review artifacts:

```text
case2_arcgis_workspace/
  project/case2_workflow.aprx
  data/case2_artifacts.gdb
  layers/*.lyrx
  maps/*.png
  maps/*.pdf
  manifests/spatial_reasoning_manifest.json
  manifests/arcgis_validation.json
  README.md
```

This preserves the same reviewer logic as QGIS: generate layers, open project, check broken layers, export view, validate manifest.

### 3.2 Minimal ArcGIS Pro Tooling Needed

Add a detachable skill or backend script, not necessarily core runtime first:

```text
scripts/package_arcgis_pro_workspace.py
scripts/validate_arcgis_pro_workspace.py
```

Run with ArcGIS Pro Python, for example:

```powershell
& 'C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe' package_arcgis_pro_workspace.py --run-dir <RUN_DIR>
& 'C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe' validate_arcgis_pro_workspace.py <CASE_DIR> --output arcgis_validation.json
```

If the user has cloned the ArcGIS Pro Python environment, the path may be a named conda env instead. The validator should record the actual Python path and ArcGIS Pro version.

### 3.3 ArcPy Packager Responsibilities

The ArcGIS Pro packager should:

1. Read the common artifacts generated by Urban-Hermes: GeoJSON/GPKG/CSV/manifest.
2. Create a file geodatabase.
3. Import spatial layers into the geodatabase.
4. Create or copy an `.aprx` template.
5. Add layers to a map.
6. Apply `.lyrx` symbology or programmatic symbology.
7. Export a layout or map view to PNG/PDF.
8. Write `arcgis_workspace_manifest.json`.

Typical ArcPy APIs:

```python
import arcpy
aprx = arcpy.mp.ArcGISProject("CURRENT" or template_path)
map_obj = aprx.listMaps()[0]
map_obj.addDataFromPath(feature_class_path)
aprx.saveACopy(output_aprx)
arcpy.management.GetCount(feature_class_path)
```

For layer validation:

```python
for layer in map_obj.listLayers():
    layer.isBroken
    layer.name
    layer.dataSource
    layer.connectionProperties
```

For layout export:

```python
layout.exportToPNG(output_png, resolution=150)
layout.exportToPDF(output_pdf)
```

### 3.4 ArcGIS Pro Validator Responsibilities

The ArcGIS validator should produce JSON analogous to QGIS validation:

```json
{
  "arcgis_read_ok": true,
  "project_path": "...aprx",
  "map_count": 1,
  "layers": [
    {
      "layer_name": "...",
      "is_broken": false,
      "data_source_exists": true,
      "feature_count": 123,
      "spatial_reference": "WGS 1984",
      "renderer_field": "road_density_m_per_ha"
    }
  ],
  "broken_layers": [],
  "missing_datasources": [],
  "missing_metric_fields": [],
  "exported_maps": ["...png", "...pdf"],
  "manifest_consistent": true,
  "needs_correction": false
}
```

The reviewer standard should be parallel to QGIS:

- project opens
- layers are not broken
- data sources exist
- metric fields exist
- map export exists
- manifest paths exist
- known limits are recorded

### 3.5 How Urban-Hermes Should Call ArcGIS Pro

Short term, no core source change is required. Urban-Hermes already has `urban_host_python`, which can run an external Python executable. It can call ArcGIS Pro Python like this:

```json
{
  "python": "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe",
  "script_path": "D:/.../package_arcgis_pro_workspace.py",
  "argv": ["--run-dir", "D:/UrbanAgents_Case2_Output/realistic_dialogue/turn2b_execute"],
  "timeout": 600
}
```

Medium term, add explicit tools:

```text
urban_arcgis_workspace
urban_arcgis_process
urban_arcgis_validate
```

But I would not add these directly to core until the script-based backend has passed at least one collaborator run.

### 3.6 Risks With ArcGIS Pro

ArcGIS Pro integration is more constrained than QGIS:

- licensing and login may affect headless runs
- ArcPy availability depends on the ArcGIS Pro Python env
- GUI state is harder to control than QGIS through a simple HTTP bridge
- `.aprx` is less transparent than `.qgs/.qgz`
- symbology inspection may be less uniform across renderer types

So for paper evidence, ArcGIS Pro should be a valid collaborator backend, but our canonical evidence can remain QGIS unless the collaborator run becomes central.

## 4. QGIS Web / Browser Map Adaptation

### 4.1 Clarify What "QGIS Web" Means

There are several possible meanings:

1. QGIS Server serving `.qgs/.qgz` projects as WMS/WFS.
2. Lizmap or QWC2 web client on top of QGIS Server.
3. `qgis2web` exporting Leaflet/OpenLayers from a QGIS project.
4. A custom MapLibre/Leaflet viewer generated directly from GeoJSON/vector tiles.

For our experiment, option 4 is the easiest and most robust. It does not require QGIS Desktop or QGIS Server. It still gives reviewer-visible map artifacts.

### 4.2 Recommended Web Backend

Add a web map packager:

```text
scripts/package_web_map_workspace.py
scripts/validate_web_map_workspace.py
```

Output:

```text
web_map_workspace/
  index.html
  layers/*.geojson
  styles/map_style.json
  manifests/spatial_reasoning_manifest.json
  screenshots/desktop.png
  screenshots/mobile.png
  web_validation.json
```

Use Leaflet or MapLibre. For validation, use Playwright to open the page and check:

- map container is nonblank
- expected layer names exist in the page manifest
- GeoJSON files load with HTTP 200 or file access
- screenshot is nonblank
- layer count matches manifest
- legend labels match renderer fields

This complements QGIS/ArcGIS because it is easier for collaborators to open in a browser.

### 4.3 QGIS Server Later

If we need true QGIS Web later, the path is:

1. Generate a QGIS Server-compatible `.qgs/.qgz`.
2. Ensure all datasources use portable paths or packaged GPKG.
3. Run QGIS Server locally or in Docker.
4. Expose WMS/WFS endpoints.
5. Validate `GetCapabilities`, layer list, bbox, style names, and sample `GetMap` images.

This is heavier and should be phase 2.

## 5. Recommended Architecture: GIS Backend Interface

We should introduce a backend-neutral contract:

```text
Common artifacts:
  spatial layers: GeoJSON/GPKG/FileGDB-compatible feature classes
  tables: CSV/Parquet
  styles: style spec with layer name, renderer type, renderer field, palette
  manifest: spatial_reasoning_manifest.json

Backends:
  qgis_desktop: .qgz + PyQGIS validator
  arcgis_pro: .aprx + ArcPy validator
  web_map: HTML + Playwright validator
```

Suggested abstract tool names:

```text
urban_gis_workspace(backend="qgis" | "arcgis_pro" | "web_map")
urban_gis_validate(backend="qgis" | "arcgis_pro" | "web_map")
urban_gis_process(backend="qgis" | "arcgis_pro" | "geopandas")
```

Do not discard current QGIS-specific tools yet. Keep them, but add the generic layer above them.

## 6. What To Tell The Collaborator With Only ArcGIS Pro

The collaborator can still run the Case2 experiment. We should tell their local testing agent:

1. Do not install QGIS just for the test unless convenient.
2. Put data in `D:/UrbanAgents_Case2_Data`.
3. Run Urban-Hermes as usual.
4. If Urban-Hermes generates QGIS-specific outputs, record that QGIS validation is unavailable.
5. Run ArcGIS Pro packager/validator if available.
6. Return `.aprx`, `.gdb`, exported PNG/PDF, `arcgis_validation.json`, transcripts, and tester notes.

This keeps the experiment honest: lack of QGIS is an environment condition, not a failed urban-analysis task.

## 7. Immediate Implementation Checklist

### Phase 0: Documentation

- Add fallback note to `TESTER_ROLE.md`: ArcGIS Pro-only collaborator should run ArcGIS validation instead of QGIS validation.
- Add `GIS_BACKENDS.md` or include this note in the package.

### Phase 1: ArcGIS Pro backend scripts

- `package_arcgis_pro_workspace.py`
- `validate_arcgis_pro_workspace.py`
- `arcgis_workspace_manifest.schema.json`
- one small smoke dataset

### Phase 2: Urban-Hermes tool wrapper

- Add `urban_arcgis_workspace` after script smoke passes.
- Add memory rules: ArcGIS broken layers, missing data sources, map export validation.

### Phase 3: Web backend

- Build Leaflet/MapLibre static viewer.
- Add Playwright screenshot validation.
- Use it as cross-platform fallback when neither QGIS nor ArcGIS is available.

## 8. Paper Framing

For the paper, frame this as backend-plural artifact validation:

> Urban-Hermes does not rely on the model's verbal claim that a spatial analysis is complete. It externalizes spatial reasoning into GIS artifacts. QGIS Desktop is the currently implemented canonical backend; ArcGIS Pro and web-map backends follow the same manifest-and-validator contract, allowing collaborators to verify artifacts in the GIS environment available on their machine.
