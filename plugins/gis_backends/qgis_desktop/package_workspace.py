"""Package protocol GIS artifacts into a QGIS Desktop workspace."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..common.manifest_io import load_json, normalize_manifest, resolve_manifest_path, write_json
from .runtime import qgis_command, resolve_qgis_python


QGIS_WRITER_SCRIPT = r'''
import json
import sys
from pathlib import Path

from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsFillSymbol,
    QgsGraduatedSymbolRenderer,
    QgsLineSymbol,
    QgsMapRendererParallelJob,
    QgsMapSettings,
    QgsMarkerSymbol,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsSingleSymbolRenderer,
    QgsSymbol,
    QgsVectorLayer,
)


def _vector_layer(path, name):
    return QgsVectorLayer(str(path), str(name), "ogr")


def _apply_renderer(layer, layer_def):
    renderer = layer_def.get("renderer") if isinstance(layer_def.get("renderer"), dict) else {}
    field = renderer.get("field") or layer_def.get("renderer_field")
    if field and layer.fields().indexFromName(str(field)) >= 0:
        graduated = QgsGraduatedSymbolRenderer(str(field))
        graduated.setMode(QgsGraduatedSymbolRenderer.EqualInterval)
        graduated.updateClasses(layer, QgsGraduatedSymbolRenderer.EqualInterval, 5)
        layer.setRenderer(graduated)
        return {"renderer_type": "graduated", "field": str(field), "ok": True}

    geom = layer.geometryType()
    if geom == 0:
        symbol = QgsMarkerSymbol.createSimple({"color": "31,119,180,220", "outline_color": "15,78,120,255", "size": "2.2"})
    elif geom == 1:
        symbol = QgsLineSymbol.createSimple({"line_color": "71,85,105,255", "line_width": "0.35"})
    else:
        symbol = QgsFillSymbol.createSimple({"color": "230,210,160,130", "outline_color": "132,96,52,255", "outline_width": "0.25"})
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    return {"renderer_type": "singleSymbol", "field": None, "ok": True}


def _combined_extent(layers):
    extent = QgsRectangle()
    initialized = False
    for layer in layers:
        if not layer.isValid():
            continue
        layer_extent = layer.extent()
        if not initialized:
            extent = QgsRectangle(layer_extent)
            initialized = True
        else:
            extent.combineExtentWith(layer_extent)
    if initialized and not extent.isEmpty():
        extent.scale(1.08)
        return extent
    return None


def _render_preview(project, layers, preview_path):
    extent = _combined_extent(layers)
    if extent is None:
        return {"path": str(preview_path), "exists": False, "message": "no valid vector extent"}
    settings = QgsMapSettings()
    settings.setLayers(layers)
    settings.setDestinationCrs(project.crs())
    settings.setExtent(extent)
    settings.setOutputSize(QSize(1200, 900))
    settings.setBackgroundColor(QColor(255, 255, 255))
    job = QgsMapRendererParallelJob(settings)
    job.start()
    job.waitForFinished()
    image = job.renderedImage()
    saved = bool(image.save(str(preview_path)))
    return {"path": str(preview_path), "exists": bool(preview_path.exists()), "saved": saved}


def write_project(args):
    manifest_path = Path(args["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    project_path = Path(args["project_path"])
    preview_path = Path(args["preview_path"])
    project_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.parent.mkdir(parents=True, exist_ok=True)

    qgs = QgsApplication([], False)
    qgs.initQgis()
    try:
        project = QgsProject.instance()
        project.clear()
        project.setTitle(str(manifest.get("task_id") or "Urban-Hermes GIS Workspace"))
        crs = manifest.get("coordinate_reference_system") or (manifest.get("spatial_scope") or {}).get("crs") or "EPSG:4326"
        project.setCrs(QgsCoordinateReferenceSystem(str(crs)))

        diagnostics = []
        added_layers = []
        for layer_def in manifest.get("layers", []):
            name = layer_def.get("name") or layer_def.get("id") or "layer"
            path = layer_def.get("path") or layer_def.get("source")
            layer_type = str(layer_def.get("type") or "vector").lower()
            if not path:
                diagnostics.append({"layer": name, "valid": False, "error": "missing path"})
                continue
            if layer_type == "raster" and (str(path).startswith("type=xyz") or str(path).startswith("http")):
                layer = QgsRasterLayer(str(path), str(name), "wms")
            else:
                layer = _vector_layer(path, name)
            record = {
                "layer": str(name),
                "path": str(path),
                "valid": bool(layer.isValid()),
                "provider": layer.providerType() if hasattr(layer, "providerType") else None,
                "error": layer.error().message() if not layer.isValid() and hasattr(layer, "error") else "",
            }
            if layer.isValid() and isinstance(layer, QgsVectorLayer):
                record["feature_count"] = int(layer.featureCount())
                record["fields"] = [field.name() for field in layer.fields()]
                record["renderer"] = _apply_renderer(layer, layer_def)
                added_layers.append(layer)
                project.addMapLayer(layer)
            elif layer.isValid():
                project.addMapLayer(layer)
            diagnostics.append(record)

        write_ok = bool(project.write(str(project_path)))
        reopen = QgsProject()
        read_ok = bool(reopen.read(str(project_path)))
        preview = _render_preview(project, added_layers, preview_path) if added_layers else {"path": str(preview_path), "exists": False, "message": "no vector layers rendered"}
        result = {
            "status": "generated" if write_ok and read_ok else "failed",
            "project_path": str(project_path),
            "preview_path": str(preview_path),
            "write_ok": write_ok,
            "read_ok": read_ok,
            "layer_count": len(project.mapLayers()),
            "reopen_layer_count": len(reopen.mapLayers()),
            "diagnostics": diagnostics,
            "preview": preview,
        }
        print(json.dumps(result, ensure_ascii=False, default=str), flush=True)
        return result
    finally:
        qgs.exitQgis()


with Path(sys.argv[1]).open("r", encoding="utf-8") as handle:
    write_project(json.load(handle))
'''


def package_workspace(
    *,
    run_dir: str | Path,
    manifest_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    qgis_python: str | None = None,
    timeout: int = 180,
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    source_manifest_path = resolve_manifest_path(run_dir, manifest_path)
    manifest = normalize_manifest(load_json(source_manifest_path), run_dir=run_dir)
    workspace_dir = Path(output_dir) if output_dir else run_dir / "qgis_workspace"
    data_dir = workspace_dir / "data"
    project_dir = workspace_dir / "project"
    manifest_dir = workspace_dir / "manifests"
    preview_dir = workspace_dir / "previews"
    for directory in (data_dir, project_dir, manifest_dir, preview_dir):
        directory.mkdir(parents=True, exist_ok=True)

    manifest = _materialize_layers(manifest, data_dir=data_dir)
    project_path = project_dir / "protocol_qgis_workspace.qgz"
    preview_path = preview_dir / "protocol_preview.png"
    manifest.setdefault("backend_workspaces", {})
    manifest["backend_workspaces"]["qgis_desktop"] = {
        "workspace_dir": str(workspace_dir),
        "project_path": str(project_path),
        "preview_path": str(preview_path),
    }
    manifest.setdefault("maps", [])
    manifest["maps"].append({"id": "qgis_protocol_preview", "type": "png", "path": str(preview_path), "backend": "qgis_desktop"})
    workspace_manifest_path = manifest_dir / "spatial_reasoning_manifest.json"
    write_json(workspace_manifest_path, manifest)
    _write_readme(workspace_dir, manifest)

    qgis_python = resolve_qgis_python(qgis_python)
    if not qgis_python:
        result = {
            "backend": "qgis_desktop",
            "success": False,
            "workspace_dir": str(workspace_dir),
            "workspace_manifest": str(workspace_manifest_path),
            "error": "QGIS Python not found",
        }
        write_json(manifest_dir / "qgis_backend_package_result.json", result)
        return result

    writer_script = project_dir / "_qgis_protocol_writer.py"
    writer_args = project_dir / "_qgis_protocol_writer_args.json"
    writer_script.write_text(QGIS_WRITER_SCRIPT, encoding="utf-8")
    write_json(
        writer_args,
        {
            "manifest_path": str(workspace_manifest_path),
            "project_path": str(project_path),
            "preview_path": str(preview_path),
        },
    )
    try:
        completed = subprocess.run(
            qgis_command(qgis_python, str(writer_script), str(writer_args)),
            cwd=str(workspace_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        result = {
            "backend": "qgis_desktop",
            "success": False,
            "workspace_dir": str(workspace_dir),
            "workspace_manifest": str(workspace_manifest_path),
            "error": f"QGIS project writer timed out after {timeout}s",
            "stdout_tail": (exc.stdout or "")[-2000:] if isinstance(exc.stdout, str) else exc.stdout,
            "stderr_tail": (exc.stderr or "")[-2000:] if isinstance(exc.stderr, str) else exc.stderr,
        }
        write_json(manifest_dir / "qgis_backend_package_result.json", result)
        return result

    parsed = _parse_last_json(completed.stdout)
    success = bool(parsed and parsed.get("status") == "generated" and parsed.get("write_ok") and parsed.get("read_ok"))
    result = {
        "backend": "qgis_desktop",
        "success": success,
        "workspace_dir": str(workspace_dir),
        "workspace_manifest": str(workspace_manifest_path),
        "project_path": str(project_path),
        "preview_path": str(preview_path),
        "returncode": completed.returncode,
        "parsed_stdout": parsed,
        "stdout_tail": (completed.stdout or "")[-4000:],
        "stderr_tail": (completed.stderr or "")[-4000:],
        "error": None if success else "QGIS project writer did not complete cleanly",
    }
    write_json(manifest_dir / "qgis_backend_package_result.json", result)
    return result


def _materialize_layers(manifest: dict[str, Any], *, data_dir: Path) -> dict[str, Any]:
    materialized = dict(manifest)
    layers = []
    for layer in manifest.get("layers", []):
        item = dict(layer)
        path_text = str(item.get("path") or "")
        if path_text and not path_text.startswith(("http://", "https://", "type=xyz")):
            source = Path(path_text)
            if source.exists() and source.is_file():
                subdir = "derived" if item.get("role") == "metric_layer" else "source"
                target = data_dir / subdir / source.name
                target.parent.mkdir(parents=True, exist_ok=True)
                if source.resolve() != target.resolve():
                    shutil.copy2(source, target)
                item["path"] = str(target)
                item["source_path"] = str(source)
        layers.append(item)
    materialized["layers"] = layers
    return materialized


def _write_readme(workspace_dir: Path, manifest: dict[str, Any]) -> None:
    lines = [
        "# QGIS Desktop Workspace",
        "",
        f"Task: {manifest.get('task_id')}",
        f"Case: {manifest.get('case_id')}",
        f"CRS: {manifest.get('coordinate_reference_system')}",
        "",
        "This workspace was generated through the Urban-Hermes GIS backend protocol.",
        "It should be inspected together with manifests/spatial_reasoning_manifest.json and the validation report.",
        "",
        "## Layers",
    ]
    for layer in manifest.get("layers", []):
        lines.append(f"- {layer.get('name') or layer.get('id')}: {layer.get('role')} -> {layer.get('path')}")
    (workspace_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Package a manifest-driven QGIS Desktop workspace.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--qgis-python", default=None)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    result = package_workspace(
        run_dir=args.run_dir,
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        qgis_python=args.qgis_python,
        timeout=args.timeout,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()