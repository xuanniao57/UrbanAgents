# Hermes Urban Agent Adapter

This folder is a Hermes-based UrbanAgent adapter carried inside the
UrbanAgents repository branch. It registers urban analysis tools into a normal
Hermes runtime while keeping runtime memory and generated artifacts local.

The adapter implements the three paper gaps as Hermes-native extensions:

- Step 1: `urban_hermes.tools` registers an `urban` toolset with Hermes `tools.registry`.
- Step 2: `urban_ground_task` and `urban_review` expose input grounding and review routing.
- Step 3: `urban_hermes.memory_provider` implements a single Hermes `MemoryProvider` that internally composes feedback memory and place memory.

## Start the interactive CLI

From the `paper4_urban_svgagent` repository root:

```powershell
$env:PYTHONPATH = "d:/GitHub_1/world_agent/urban-mobility-agent/paper4_urban_svgagent/hermes_urban_agent"
C:/Users/18029/.conda/envs/four-seasons/python.exe -m urban_hermes --toolsets urban,todo,memory
```

This enters the normal Hermes CLI after registering the `urban` toolset.
Type your task at the Hermes prompt, for example:

```text
Assess walkability in Le Marais and review evidence gaps before giving recommendations.
```

For one-shot mode, pass the query directly:

```powershell
$env:PYTHONPATH = "d:/GitHub_1/world_agent/urban-mobility-agent/paper4_urban_svgagent/hermes_urban_agent"
C:/Users/18029/.conda/envs/four-seasons/python.exe -m urban_hermes "Assess walkability in Le Marais and review evidence gaps" --toolsets urban,todo,memory
```

On Windows, Hermes-Urban filters upstream generic `file` and `terminal` toolsets
by default even if they are requested, because upstream Hermes executes them via
Git Bash. Use `urban_host_fs`, `urban_host_python`, and `urban_qgis_process` for
native `D:/...` paths and QGIS artifacts. Pass `--allow-wsl-tools` only when you
explicitly want the upstream Git-Bash/WSL-style tools.

## Quick smoke test

From the repository root:

```powershell
$env:PYTHONPATH = "d:/GitHub_1/world_agent/urban-mobility-agent/paper4_urban_svgagent/hermes_urban_agent"
C:/Users/18029/.conda/envs/four-seasons/python.exe -m urban_hermes.dogfood
```

The smoke test prints a JSON diagnostic report.
It uses synthetic OSM-like data by default so it works without network access.

Expected minimum signal from a passing run:

- 17 registered urban tools.
- `grounding_status` is `grounded` or `grounded_with_gaps`.
- `review_recommendation` is `accept` or `accept_with_warnings` for the fixture.
- `research_memory_hit` is `true` for the built-in research-design cue store.
- `memory_recall_hit` is `true` after the feedback write.
- `host_fs_hit` and `host_python_hit` are `true` for native host execution.

## Non-interactive and QGIS runs

For scripted experiments, prefer plain/quiet mode so Hermes does not route
output through `prompt_toolkit`:

```powershell
$env:PYTHONPATH = "d:/GitHub_1/world_agent/urban-mobility-agent/paper4_urban_svgagent/hermes_urban_agent"
C:/Users/18029/.conda/envs/four-seasons/python.exe -m urban_hermes "..." --quiet --plain --toolsets urban,todo,memory
```

If the run must execute shell/GIS commands without interactive approval prompts,
add `--yolo` for that process:

```powershell
C:/Users/18029/.conda/envs/four-seasons/python.exe -m urban_hermes "..." --quiet --plain --yolo --toolsets urban,todo,memory
```

Use the `urban_qgis_process` tool for real QGIS Processing artifacts. It wraps
`qgis_process`, writes a JSONL command log when `output_dir` or `log_path` is
provided, and verifies GeoJSON outputs with feature counts. Use `urban_host_fs`
to list/read native files and `urban_host_python` for small Windows-native
preparation scripts when QGIS Processing alone is not enough.

Use `urban_qgis_workspace` after a GIS-heavy run to package loose layers into a
QGIS workbench: source layers, derived metric layers, `.qgz/.qgs`, README, and
`spatial_reasoning_manifest.json` for later agent reasoning.

## Launch Hermes with the explicit launcher

```powershell
$env:PYTHONPATH = "d:/GitHub_1/world_agent/urban-mobility-agent/paper4_urban_svgagent/hermes_urban_agent"
C:/Users/18029/.conda/envs/four-seasons/python.exe -m urban_hermes.launcher --toolsets urban,todo,memory
```

The launcher imports `urban_hermes.bootstrap` before entering Hermes, so the dynamic `urban` toolset is visible to Hermes' toolset resolver.

## Install the Hermes memory bridge

This creates a small `urban_memory` bridge under the active Hermes home plugin directory.

```powershell
$env:PYTHONPATH = "d:/GitHub_1/world_agent/urban-mobility-agent/paper4_urban_svgagent/hermes_urban_agent"
C:/Users/18029/.conda/envs/four-seasons/python.exe -m urban_hermes.install_plugin
```

If `hermes-agent/` is not a sibling of this repository root, set
`URBAN_HERMES_HERMES_ROOT` to the Hermes source directory before launching.

Then set `memory.provider: urban_memory` in Hermes `config.yaml` if you want the normal Hermes memory-provider discovery path to load it automatically.

## Programmatic use

```python
from urban_hermes.bootstrap import bootstrap

names = bootstrap()
print(names)

from tools.registry import registry
print(registry.dispatch("urban_ground_task", {"task": "Assess walkability in Le Marais"}))
```

## Hermes memory plugin shape

Hermes allows only one external memory provider at a time.
Use `UrbanMemoryProvider`, which combines feedback and place stores behind one provider.

```python
from agent.memory_manager import MemoryManager
from urban_hermes.memory_provider import UrbanMemoryProvider

manager = MemoryManager()
provider = UrbanMemoryProvider()
provider.initialize("dogfood-session")
manager.add_provider(provider)
```
