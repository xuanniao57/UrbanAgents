#!/usr/bin/env python
"""Build an offline Case2 collaborator release zip.

The zip is intentionally source-based: collaborators unzip it, create a conda
environment, set PYTHONPATH to `paper4_urban_svgagent/hermes_urban_agent` and
`paper4_urban_svgagent`, then run Urban-Hermes without cloning GitHub.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path


PAPER4_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PAPER4_ROOT.parent

INCLUDE_DIRS = [
    "hermes_urban_agent",
    "plugins/gis_backends",
    "plugins/qgis",
    "urban_agent",
    "web",
    "experiments/case2_tester_package",
]

INCLUDE_FILES = [
    "pyproject.toml",
    "README.md",
    "LICENSE",
    "requirements_combined.txt",
    "requirements_citybench_windows.txt",
    "docs/gis_tool_extension_architecture.md",
    "experiments/gis_backend_adaptation_note_20260519.md",
    "scripts/run_gis_backend_protocol_smoke.py",
]

EXCLUDED_DIR_NAMES = {"__pycache__", ".pytest_cache", ".git", "runtime_memory", "hermes_home"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp"}
EXCLUDED_FILE_NAMES = {".env", "kimi_code.env"}


def _copytree(src: Path, dst: Path) -> None:
    def ignore(_directory: str, names: list[str]) -> set[str]:
        ignored = set()
        for name in names:
            path = Path(name)
            if name in EXCLUDED_DIR_NAMES or name in EXCLUDED_FILE_NAMES:
                ignored.add(name)
            elif path.suffix.lower() in EXCLUDED_SUFFIXES:
                ignored.add(name)
            elif name.startswith(".env") and name != ".env.example":
                ignored.add(name)
        return ignored

    shutil.copytree(src, dst, ignore=ignore)


def _git_value(args: list[str]) -> str | None:
    try:
        completed = subprocess.run(["git", "-C", str(PAPER4_ROOT), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _zip_dir(source_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in source_dir.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir.parent))


def build_release(output_root: Path, release_name: str) -> dict:
    staging = output_root / release_name
    if staging.exists():
        shutil.rmtree(staging)
    paper4_dst = staging / "paper4_urban_svgagent"
    paper4_dst.mkdir(parents=True, exist_ok=True)

    copied = []
    for relative in INCLUDE_DIRS:
        src = PAPER4_ROOT / relative
        dst = paper4_dst / relative
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            _copytree(src, dst)
            copied.append(relative)
    for relative in INCLUDE_FILES:
        src = PAPER4_ROOT / relative
        dst = paper4_dst / relative
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied.append(relative)

    hermes_runtime = paper4_dst / "hermes_urban_agent" / "urban_hermes" / "_vendor" / "hermes_runtime"
    if not hermes_runtime.exists():
        raise RuntimeError(f"Vendored Hermes runtime missing from release: {hermes_runtime}")

    manifest = {
        "release_name": release_name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper4_root": str(PAPER4_ROOT),
        "git_commit": _git_value(["rev-parse", "HEAD"]),
        "git_branch": _git_value(["branch", "--show-current"]),
        "contains": copied,
        "required_local_paths_after_unzip": {
            "project_root": "D:/UrbanAgents_Case2/paper4_urban_svgagent",
            "case2_package": "D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_tester_package",
            "data_root": "D:/UrbanAgents_Case2_Data",
            "output_root": "D:/UrbanAgents_Case2_Output/realistic_dialogue",
        },
        "notes": [
            "This release includes Urban-Hermes and the vendored Hermes runtime under hermes_urban_agent/urban_hermes/_vendor/hermes_runtime.",
            "Secrets such as kimi_code.env and .env are intentionally excluded.",
            "ArcGIS Pro FileGDB validation is supported; full .aprx visual validation needs template_aprx.",
        ],
    }
    (staging / "RELEASE_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (staging / "START_HERE.md").write_text(
        "# UrbanAgents Case2 Offline Release\n\n"
        "1. Unzip this folder to `D:/UrbanAgents_Case2`.\n"
        "2. Open `paper4_urban_svgagent/experiments/case2_tester_package/README.md`.\n"
        "3. Follow `INSTALL.md`, then run `scripts/gis_backend_preflight.py`.\n"
        "4. Put research data under `D:/UrbanAgents_Case2_Data`.\n",
        encoding="utf-8",
    )

    zip_path = output_root / f"{release_name}.zip"
    if zip_path.exists():
        zip_path.unlink()
    _zip_dir(staging, zip_path)
    manifest["zip_path"] = str(zip_path)
    manifest["staging_dir"] = str(staging)
    (staging / "RELEASE_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Case2 offline collaborator release zip.")
    parser.add_argument("--output-root", default=str(PROJECT_ROOT / "artifacts" / "case2_releases"))
    parser.add_argument("--release-name", default=f"UrbanAgents_Case2_Offline_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    args = parser.parse_args()
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    manifest = build_release(output_root, args.release_name)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()