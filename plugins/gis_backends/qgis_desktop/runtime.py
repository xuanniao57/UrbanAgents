"""Runtime discovery for the QGIS Desktop backend."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def candidate_qgis_python_paths() -> list[str]:
    env_path = os.getenv("QGIS_PYTHON") or os.getenv("QGIS_PYTHON_PATH")
    candidates = [env_path] if env_path else []
    candidates.extend(
        [
            r"C:\Program Files\QGIS 3.40.11\bin\python-qgis-ltr.bat",
            r"C:\Program Files\QGIS 3.40\bin\python-qgis-ltr.bat",
            r"C:\Program Files\QGIS 3.40.11\bin\python.exe",
            r"C:\Program Files\QGIS 3.40\bin\python.exe",
        ]
    )
    return [item for item in candidates if item]


def resolve_qgis_python(value: object | None = None) -> str | None:
    candidates = [str(value)] if value else []
    candidates.extend(candidate_qgis_python_paths())
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return str(path)
    return None


def qgis_command(executable: str, *args: str) -> list[str]:
    if os.name == "nt" and executable.lower().endswith((".bat", ".cmd")):
        return ["cmd.exe", "/c", executable, *args]
    return [executable, *args]


def probe_runtime(executable: object | None = None, *, timeout: int = 60) -> dict[str, Any]:
    qgis_python = resolve_qgis_python(executable)
    result: dict[str, Any] = {
        "backend": "qgis_desktop",
        "available": bool(qgis_python),
        "executable": qgis_python,
        "searched": candidate_qgis_python_paths(),
    }
    if not qgis_python:
        result["message"] = "QGIS Python was not found."
        return result

    script = Path(tempfile.gettempdir()) / "urban_hermes_qgis_probe.py"
    script.write_text(
        "import json\n"
        "from qgis.core import Qgis, QgsApplication\n"
        "qgs = QgsApplication([], False)\n"
        "qgs.initQgis()\n"
        "print(json.dumps({'ok': True, 'qgis_version': Qgis.QGIS_VERSION}, ensure_ascii=False))\n"
        "qgs.exitQgis()\n",
        encoding="utf-8",
    )
    try:
        completed = subprocess.run(
            qgis_command(qgis_python, str(script)),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except Exception as exc:
        result.update({"available": False, "message": str(exc)})
        return result
    finally:
        try:
            script.unlink(missing_ok=True)
        except OSError:
            pass

    result.update(
        {
            "returncode": completed.returncode,
            "stdout_tail": (completed.stdout or "")[-1000:],
            "stderr_tail": (completed.stderr or "")[-1000:],
        }
    )
    for line in reversed((completed.stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            import json

            try:
                payload = json.loads(line)
            except Exception:
                continue
            result["available"] = bool(payload.get("ok"))
            result["version"] = payload.get("qgis_version")
            result["message"] = "QGIS Python probe succeeded." if result["available"] else "QGIS Python probe failed."
            return result
    result["available"] = False
    result["message"] = "QGIS Python probe did not return parseable JSON."
    return result