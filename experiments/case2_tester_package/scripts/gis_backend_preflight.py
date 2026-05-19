#!/usr/bin/env python
"""Probe GIS backends through the real Urban-Hermes tool registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _find_paper4_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "hermes_urban_agent" / "urban_hermes" / "launcher.py").exists():
            return candidate
    raise RuntimeError("Could not locate paper4_urban_svgagent root from script path.")


PAPER4_ROOT = _find_paper4_root(Path(__file__).resolve())
for path in (PAPER4_ROOT / "hermes_urban_agent", PAPER4_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _dispatch(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    from tools.registry import registry

    raw = registry.dispatch(tool_name, args)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"success": False, "error": f"non-json response: {exc}", "raw": raw[:1000]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe QGIS and ArcGIS Pro backends through Urban-Hermes.")
    parser.add_argument("--output", default="D:/UrbanAgents_Case2_Output/preflight/gis_backend_preflight.json")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    from urban_hermes.bootstrap import bootstrap

    registered = bootstrap()
    probes = {}
    for backend in ["qgis_desktop", "arcgis_pro"]:
        payload = _dispatch("urban_gis_workspace", {"backend": backend, "mode": "probe", "timeout": args.timeout})
        result = payload.get("result") if payload.get("success") else payload.get("result", payload)
        probes[backend] = result

    summary = {
        "paper4_root": str(PAPER4_ROOT),
        "registered_has_urban_gis_workspace": "urban_gis_workspace" in registered,
        "qgis_desktop": probes.get("qgis_desktop"),
        "arcgis_pro": probes.get("arcgis_pro"),
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()