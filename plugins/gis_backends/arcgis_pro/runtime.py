"""Runtime discovery for the ArcGIS Pro backend."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def candidate_arcgis_python_paths() -> list[str]:
    env_path = os.getenv("ARCGIS_PYTHON") or os.getenv("ARCGIS_PRO_PYTHON") or os.getenv("ARCPY_PYTHON")
    candidates = [env_path] if env_path else []
    candidates.extend(
        [
            r"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe",
            r"C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\propy.bat",
            r"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\pythonw.exe",
        ]
    )
    return [item for item in candidates if item]


def resolve_arcgis_python(value: object | None = None) -> str | None:
    candidates = [str(value)] if value else []
    candidates.extend(candidate_arcgis_python_paths())
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return str(path)
    return None


def arcgis_command(executable: str, *args: str) -> list[str]:
    if os.name == "nt" and executable.lower().endswith((".bat", ".cmd")):
        return ["cmd.exe", "/c", executable, *args]
    return [executable, *args]


def probe_runtime(executable: object | None = None, *, timeout: int = 60) -> dict[str, Any]:
    arcgis_python = resolve_arcgis_python(executable)
    result: dict[str, Any] = {
        "backend": "arcgis_pro",
        "available": bool(arcgis_python),
        "executable": arcgis_python,
        "searched": candidate_arcgis_python_paths(),
    }
    if not arcgis_python:
        result["message"] = "ArcGIS Pro Python was not found."
        return result

    script = Path(tempfile.gettempdir()) / "urban_hermes_arcgis_probe.py"
    script.write_text(
        "import json\n"
        "try:\n"
        "    import arcpy\n"
        "    info = arcpy.GetInstallInfo()\n"
        "    print(json.dumps({'ok': True, 'install_info': info}, ensure_ascii=False, default=str))\n"
        "except Exception as exc:\n"
        "    print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))\n",
        encoding="utf-8",
    )
    try:
        completed = subprocess.run(
            arcgis_command(arcgis_python, str(script)),
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
            result["install_info"] = payload.get("install_info")
            result["version"] = (payload.get("install_info") or {}).get("Version") if isinstance(payload.get("install_info"), dict) else None
            result["message"] = "ArcPy probe succeeded." if result["available"] else payload.get("error") or "ArcPy probe failed."
            return result
    result["available"] = False
    result["message"] = "ArcPy probe did not return parseable JSON."
    return result