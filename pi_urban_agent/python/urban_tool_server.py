"""Small, Pi-owned bridge for deterministic urban-analysis operations.

The primary runtime does not import Hermes. Large analytical outputs stay on
disk and only bounded previews plus hashes return to the model context.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any


MAX_PREVIEW_CHARS = 4_000


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_path(value: str, roots: list[Path]) -> Path:
    path = Path(value).expanduser().resolve()
    if roots and not any(path == root or root in path.parents for root in roots):
        raise ValueError(f"Path is outside allowed roots: {path}")
    return path


def allowed_roots(request: dict[str, Any]) -> list[Path]:
    values = request.get("allowed_roots") or []
    env_root = os.environ.get("URBAN_PI_REPOSITORY_ROOT")
    if env_root:
        values.append(env_root)
    return [Path(value).expanduser().resolve() for value in values]


def inspect_json(arguments: dict[str, Any], roots: list[Path]) -> dict[str, Any]:
    path = ensure_path(str(arguments["path"]), roots)
    json.loads(path.read_text(encoding="utf-8"))  # Validate format; paging uses the original text.
    return inspect_text(arguments, roots)


def inspect_text(arguments: dict[str, Any], roots: list[Path]) -> dict[str, Any]:
    path = ensure_path(str(arguments["path"]), roots)
    if path.is_dir():
        raise ValueError("path is a directory; use list_directory, then inspect an exact file")
    text = path.read_text(encoding="utf-8-sig")
    offset = arguments.get("offset", 0)
    end = min(len(text), offset + arguments.get("limit", 1600))
    return {"path": str(path), "sha256": sha256_file(path), "preview": text[offset:end],
            "has_more": end < len(text), "next_offset": end if end < len(text) else None, "size_bytes": path.stat().st_size}


def list_directory(arguments: dict[str, Any], roots: list[Path]) -> dict[str, Any]:
    path = ensure_path(str(arguments["path"]), roots)
    entries = sorted(path.iterdir())
    offset = arguments.get("offset", 0)
    end = min(len(entries), offset + min(arguments.get("limit", 12), 50))
    return {"path": str(path), "entries": [{"name": p.name, "is_directory": p.is_dir()} for p in entries[offset:end]],
            "has_more": end < len(entries), "next_offset": end if end < len(entries) else None}


def read_file(arguments: dict[str, Any], roots: list[Path]) -> dict[str, Any]:
    path = ensure_path(str(arguments["path"]), roots)
    if path.is_dir():
        return {"page_unit": "entries", **list_directory(arguments, roots)}
    if path.suffix.lower() == ".csv":
        return {"page_unit": "rows", **inspect_csv(arguments, roots)}
    return {"page_unit": "characters", **inspect_text(arguments, roots)}


def inspect_csv(arguments: dict[str, Any], roots: list[Path]) -> dict[str, Any]:
    path = ensure_path(str(arguments["path"]), roots)
    limit = max(1, min(int(arguments.get("limit", 8)), 50))
    offset = arguments.get("offset", 0)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        has_more = False
        for index, row in enumerate(reader):
            if index < offset:
                continue
            if len(rows) >= limit:
                has_more = True
                break
            rows.append(row)
        columns = reader.fieldnames or []
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "columns": columns,
        "rows": rows,
        "preview_rows": len(rows),
        "has_more": has_more,
        "next_offset": offset + len(rows) if has_more else None,
        "size_bytes": path.stat().st_size,
    }


def hash_artifact(arguments: dict[str, Any], roots: list[Path]) -> dict[str, Any]:
    path = ensure_path(str(arguments["path"]), roots)
    return {"path": str(path), "sha256": sha256_file(path), "size_bytes": path.stat().st_size}


def run_script(arguments: dict[str, Any], roots: list[Path]) -> dict[str, Any]:
    script = ensure_path(str(arguments["script"]), roots)
    if not script.is_file():
        raise ValueError("script must be one existing Python file path, not inline code or a shell command; put CLI tokens in args")
    cwd = ensure_path(str(arguments.get("cwd") or script.parent), roots)
    script_args = arguments.get("args", [])
    timeout = max(1, min(int(arguments.get("timeout_seconds", 1_800)), 7_200))
    python = str(arguments.get("python") or sys.executable)
    completed = subprocess.run(
        [python, str(script), *script_args],
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        check=False,
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    log_root = ensure_path(os.environ.get("URBAN_TOOL_RESULT_ROOT", str(cwd / ".urban-executions")), roots) / uuid.uuid4().hex
    log_root.mkdir(parents=True)
    stdout_path, stderr_path = log_root / "stdout.txt", log_root / "stderr.txt"
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    manifest_path = log_root / "manifest.json"
    output_dir = None
    if "--out" in script_args:
        i = script_args.index("--out")
        if i + 1 < len(script_args):
            output_dir = ensure_path(str(cwd / script_args[i + 1]), roots)
    manifest = {"exit_code": completed.returncode, "script": str(script), "args": script_args,
                "stdout_path": str(stdout_path), "stderr_path": str(stderr_path),
                "output_directory": str(output_dir) if output_dir else None,
                "files": [str(p) for p in sorted(output_dir.iterdir()) if p.is_file()] if output_dir and output_dir.is_dir() else []}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "manifest_path": str(manifest_path),
        "output_directory": manifest["output_directory"],
        "script": str(script),
        "cwd": str(cwd),
        "exit_code": completed.returncode,
        "stdout_preview": completed.stdout[-1200:],
        "stderr_preview": completed.stderr[-600:],
    }


METHODS = {
    "read_file": read_file,
    "inspect_text": inspect_text,
    "list_directory": list_directory,
    "inspect_json": inspect_json,
    "inspect_csv": inspect_csv,
    "hash_artifact": hash_artifact,
    "run_script": run_script,
}


def validate_arguments(method: str, arguments: dict[str, Any]) -> None:
    """One contract for direct bridge calls and both Pi context conditions."""
    allowed = ({"script", "args", "cwd", "timeout_seconds", "python"} if method == "run_script"
               else {"path", "limit", "offset"} if method in {"read_file", "inspect_csv", "inspect_json", "inspect_text", "list_directory"} else {"path"})
    unknown = arguments.keys() - allowed
    if unknown:
        raise ValueError(f"Unexpected arguments for {method}: {', '.join(sorted(unknown))}. "
                         "For run_script put CLI flags/values in args, e.g. [\"--action\",\"inventory\"].")
    required = "script" if method == "run_script" else "path"
    if not isinstance(arguments.get(required), str) or not arguments[required].strip():
        raise ValueError(f"{method} requires arguments.{required} as a nonempty file path")
    for key in ("cwd", "python"):
        if key in arguments and (not isinstance(arguments[key], str) or not arguments[key].strip()):
            raise ValueError(f"{key} must be a nonempty string")
    if "args" in arguments and (not isinstance(arguments["args"], list)
                                or not all(isinstance(value, str) for value in arguments["args"])):
        raise ValueError('args must be an array of strings, e.g. ["--action","inventory"], not a command string')
    if "offset" in arguments and (type(arguments["offset"]) is not int or arguments["offset"] < 0):
        raise ValueError("offset must be a nonnegative integer")
    for key, maximum in (("limit", 4000 if method in {"read_file", "inspect_text", "inspect_json"} else 50), ("timeout_seconds", 7200)):
        if key in arguments and (type(arguments[key]) is not int or not 1 <= arguments[key] <= maximum):
            raise ValueError(f"{key} must be an integer from 1 to {maximum}")


def dispatch(request: dict[str, Any]) -> dict[str, Any]:
    method = str(request.get("method") or "").strip()
    if method not in METHODS:
        return {"success": False, "method": method, "error": f"Unknown method. Available: {', '.join(sorted(METHODS))}"}
    arguments = request.get("arguments", {})
    if not isinstance(arguments, dict):
        return {"success": False, "method": method, "error": "arguments must be an object"}
    try:
        unknown = request.keys() - {"method", "arguments", "allowed_roots"}
        if unknown:
            raise ValueError(f"Unexpected top-level fields: {', '.join(sorted(unknown))}; use method and arguments")
        validate_arguments(method, arguments)
        result = METHODS[method](arguments, allowed_roots(request))
        if method == "run_script" and result["exit_code"] != 0:
            return {"success": False, "method": method, "result": result,
                    "error": f"Python script exited with code {result['exit_code']}: "
                             f"{result['stderr_preview'] or result['stdout_preview'] or 'no diagnostic output'}"}
        return {"success": True, "method": method, "result": result}
    except Exception as exc:  # noqa: BLE001 - errors are serialized for the tool caller.
        return {"success": False, "method": method, "error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("request must be an object")
        response = dispatch(request)
    except Exception as exc:  # noqa: BLE001
        response = {"success": False, "method": "", "error": f"BridgeError: {type(exc).__name__}: {exc}"}
    print(json.dumps(response, ensure_ascii=False))
    return 0 if response.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
