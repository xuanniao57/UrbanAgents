"""QGIS Desktop backend orchestration for the GIS protocol."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from ..common.validation_report import acceptance_from_report
from ..protocol import MODE_PACKAGE, MODE_PACKAGE_AND_VALIDATE, MODE_PROBE, MODE_VALIDATE, normalize_mode
from .package_workspace import package_workspace
from .runtime import probe_runtime, qgis_command, resolve_qgis_python


def run(request: dict[str, Any]) -> dict[str, Any]:
    mode = normalize_mode(request.get("mode"))
    runtime = probe_runtime(request.get("runtime_executable") or request.get("qgis_python"), timeout=int(request.get("timeout") or 120))
    if mode == MODE_PROBE:
        return {"backend": "qgis_desktop", "mode": mode, "success": bool(runtime.get("available")), "runtime": runtime}
    if not runtime.get("available"):
        return {"backend": "qgis_desktop", "mode": mode, "success": False, "runtime": runtime, "error": "QGIS runtime unavailable"}

    if mode == MODE_PACKAGE:
        packaged = package_workspace(
            run_dir=request.get("run_dir"),
            manifest_path=request.get("artifact_manifest") or request.get("manifest"),
            output_dir=request.get("output_dir"),
            qgis_python=runtime.get("executable"),
            timeout=int(request.get("timeout") or 180),
        )
        packaged.update({"mode": mode, "runtime": runtime})
        return packaged

    if mode == MODE_VALIDATE:
        workspace_dir = request.get("workspace_dir") or request.get("output_dir") or Path(request.get("run_dir")) / "qgis_workspace"
        validated = _run_validation(Path(workspace_dir), runtime.get("executable"), timeout=int(request.get("timeout") or 180))
        return {"backend": "qgis_desktop", "mode": mode, "success": not validated.get("needs_correction"), "runtime": runtime, "validation": validated, "acceptance": acceptance_from_report(validated)}

    if mode == MODE_PACKAGE_AND_VALIDATE:
        packaged = package_workspace(
            run_dir=request.get("run_dir"),
            manifest_path=request.get("artifact_manifest") or request.get("manifest"),
            output_dir=request.get("output_dir"),
            qgis_python=runtime.get("executable"),
            timeout=int(request.get("timeout") or 180),
        )
        workspace_dir = Path(packaged.get("workspace_dir") or request.get("output_dir") or Path(request.get("run_dir")) / "qgis_workspace")
        validated = _run_validation(workspace_dir, runtime.get("executable"), timeout=int(request.get("timeout") or 180)) if packaged.get("success") else {}
        acceptance = acceptance_from_report(validated) if validated else {"accepted": False, "blocking_errors": [packaged.get("error") or "package failed"], "warnings": [], "known_limits": []}
        return {
            "backend": "qgis_desktop",
            "mode": mode,
            "success": bool(packaged.get("success")) and bool(acceptance.get("accepted")),
            "runtime": runtime,
            "package": packaged,
            "validation": validated,
            "acceptance": acceptance,
            "workspace_dir": str(workspace_dir),
            "workspace_manifest": packaged.get("workspace_manifest"),
            "validation_report": _validation_report_path(workspace_dir),
        }

    raise ValueError(f"unsupported mode: {mode}")


def _run_validation(workspace_dir: Path, qgis_python: str | None, *, timeout: int) -> dict[str, Any]:
    qgis_python = resolve_qgis_python(qgis_python)
    if not qgis_python:
        return {"backend": "qgis_desktop", "needs_correction": True, "blocking_errors": ["QGIS Python not found"]}
    output = workspace_dir / "manifests" / "qgis_validation_report.json"
    script = Path(__file__).with_name("validate_workspace.py")
    completed = subprocess.run(
        qgis_command(qgis_python, str(script), str(workspace_dir), "--output", str(output)),
        cwd=str(workspace_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    parsed = _parse_last_json(completed.stdout)
    if parsed:
        parsed["returncode"] = completed.returncode
        parsed["stdout_tail"] = (completed.stdout or "")[-2000:]
        parsed["stderr_tail"] = (completed.stderr or "")[-2000:]
        return parsed
    return {
        "backend": "qgis_desktop",
        "needs_correction": True,
        "blocking_errors": ["QGIS validation did not return parseable JSON"],
        "returncode": completed.returncode,
        "stdout_tail": (completed.stdout or "")[-2000:],
        "stderr_tail": (completed.stderr or "")[-2000:],
    }


def _parse_last_json(stdout: str | None) -> dict[str, Any] | None:
    for line in reversed((stdout or "").splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _validation_report_path(workspace_dir: Path) -> str:
    return str(workspace_dir / "manifests" / "qgis_validation_report.json")