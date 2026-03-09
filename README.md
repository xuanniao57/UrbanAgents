# UrbanAgent

UrbanAgent is an open Python package for LLM-orchestrated urban spatial analysis. It combines OSM-grounded perception, dual-space spatial cognition, task-specific reasoning, MCP-style tool invocation, and human-in-the-loop checkpoints in one reusable workflow.

This directory also contains benchmark runners, a lightweight web interface, connector integrations, and reproducible artifacts used to validate the package.

## What is included

- `urban_agent/`: installable package code
- `web/`: FastAPI-based interactive interface
- `scripts/benchmarks/`: benchmark runners and regression-style validation scripts
- `docs/`: runbooks, connector setup, release checklist, and design notes
- `third_party/CityBench-main/`: vendored benchmark dependency

## Installation

### Core package

```bash
pip install -e .
```

### Development extras

```bash
pip install -e .[dev]
```

### Full local environment used in this repository

If you need the wider benchmark and research stack used during development, install the pinned environment:

```bash
pip install -r requirements_combined.txt
```

## Public APIs

UrbanAgent currently exposes two supported entrypoints:

- `urban_agent.UrbanAgent`: legacy synchronous workflow for direct spatial analysis
- `urban_agent.UrbanTaskAgent`: async task-oriented agent used by benchmark and workflow execution

Example:

```python
from urban_agent import UrbanAgent, UrbanTaskAgent

legacy_agent = UrbanAgent()

task_agent = UrbanTaskAgent()
```

## Quick start

### Legacy synchronous analysis

```python
from urban_agent import UrbanAgent

agent = UrbanAgent()
context = agent.analyze("田子坊, 上海", "改善公共空间连通性", radius=500)
print(context.spatial_understanding)
```

### Run the web interface

```bash
cd web
pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:8765`.

### Run the quick benchmark

```bash
python scripts/benchmarks/run_citydata_quick_benchmark.py --help
```

For full CityBench runtime details, see `docs/CITYBENCH_RUNBOOK.md`.

## Testing

Run the package test suite from this directory:

```bash
pytest
```

The included baseline tests avoid external APIs and focus on package integrity, public API stability, and in-memory workflow behavior.

## Documentation index

- `docs/CITYBENCH_RUNBOOK.md`: benchmark runtime instructions
- `docs/RHINO_GRASSHOPPER_CONNECTOR_SETUP.md`: connector setup guide
- `docs/RELEASE_CHECKLIST.md`: minimum release checklist
- `CONTRIBUTING.md`: contribution workflow
- `CHANGELOG.md`: release history

## Current maturity

UrbanAgent is now structured as an installable open-source package, but it is still an early-stage research software project. The current strengths are reproducible benchmark runners, inspectable workflow artifacts, and modular connectors. The next maturity steps are broader automated coverage, formal release tagging, and public issue-driven maintenance.
