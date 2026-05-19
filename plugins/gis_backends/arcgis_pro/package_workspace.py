"""Package protocol GIS artifacts into an ArcGIS Pro workspace."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..common.manifest_io import load_json, normalize_manifest, resolve_manifest_path, write_json
from .runtime import arcgis_command, resolve_arcgis_python, resolve_template_aprx


ARCPY_PACKAGER_SCRIPT = r'''
import json
import re
import sys
from pathlib import Path

import arcpy


def safe_name(text):
    value = re.sub(r"[^A-Za-z0-9_]+", "_", str(text or "layer")).strip("_")
    if not value:
        value = "layer"
    if value[0].isdigit():
        value = "l_" + value
    return value[:60]


def field_names(dataset):
    return [field.name for field in arcpy.ListFields(dataset)]


def spatial_reference(crs_text):
    text = str(crs_text or "EPSG:4326")
    match = re.search(r"EPSG[: ](\d+)", text, re.I)
    if match:
        return arcpy.SpatialReference(int(match.group(1)))
    return arcpy.SpatialReference(4326)


def safe_field_name(text, used):
    value = re.sub(r"[^A-Za-z0-9_]+", "_", str(text or "field")).strip("_")
    if not value:
        value = "field"
    if value[0].isdigit():
        value = "f_" + value
    value = value[:60]
    candidate = value
    suffix = 1
    while candidate.lower() in used:
        tail = f"_{suffix}"
        candidate = value[: 60 - len(tail)] + tail
        suffix += 1
    used.add(candidate.lower())
    return candidate


def infer_field_type(values):
    clean = [value for value in values if value is not None]
    if not clean:
        return "TEXT"
    if all(isinstance(value, bool) for value in clean):
        return "SHORT"
    if all(isinstance(value, int) and not isinstance(value, bool) for value in clean):
        return "LONG"
    if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in clean):
        return "DOUBLE"
    return "TEXT"


def geojson_geometry_type(features):
    for feature in features:
        geom = feature.get("geometry") or {}
        gtype = geom.get("type")
        if gtype in {"Point", "MultiPoint"}:
            return "POINT"
        if gtype in {"LineString", "MultiLineString"}:
            return "POLYLINE"
        if gtype in {"Polygon", "MultiPolygon"}:
            return "POLYGON"
    return "POINT"


def make_geometry(geometry, sr):
    gtype = (geometry or {}).get("type")
    coords = (geometry or {}).get("coordinates")
    if not gtype or coords is None:
        return None
    if gtype == "Point":
        return arcpy.PointGeometry(arcpy.Point(float(coords[0]), float(coords[1])), sr)
    if gtype == "LineString":
        return arcpy.Polyline(arcpy.Array([arcpy.Point(float(x), float(y)) for x, y in coords]), sr)
    if gtype == "MultiLineString":
        parts = arcpy.Array()
        for line in coords:
            parts.add(arcpy.Array([arcpy.Point(float(x), float(y)) for x, y in line]))
        return arcpy.Polyline(parts, sr)
    if gtype == "Polygon":
        parts = arcpy.Array()
        for ring in coords:
            parts.add(arcpy.Array([arcpy.Point(float(x), float(y)) for x, y in ring]))
        return arcpy.Polygon(parts, sr)
    if gtype == "MultiPolygon":
        parts = arcpy.Array()
        for polygon in coords:
            for ring in polygon:
                parts.add(arcpy.Array([arcpy.Point(float(x), float(y)) for x, y in ring]))
        return arcpy.Polygon(parts, sr)
    return None


def write_geojson_feature_class(source_path, target, sr):
    payload = json.loads(Path(source_path).read_text(encoding="utf-8-sig"))
    if payload.get("type") != "FeatureCollection":
        return False
    features = [feature for feature in payload.get("features", []) if isinstance(feature, dict)]
    geometry_type = geojson_geometry_type(features)
    target_path = Path(str(target))
    if arcpy.Exists(str(target)):
        arcpy.management.Delete(str(target))
    arcpy.management.CreateFeatureclass(str(target_path.parent), target_path.name, geometry_type, spatial_reference=sr)

    property_keys = []
    seen_props = set()
    for feature in features:
        for key in (feature.get("properties") or {}).keys():
            if key not in seen_props:
                seen_props.add(key)
                property_keys.append(key)
    used_fields = {field.name.lower() for field in arcpy.ListFields(str(target))}
    field_map = {}
    for key in property_keys:
        values = [(feature.get("properties") or {}).get(key) for feature in features]
        safe = safe_field_name(key, used_fields)
        field_type = infer_field_type(values)
        if field_type == "TEXT":
            arcpy.management.AddField(str(target), safe, field_type, field_length=512)
        else:
            arcpy.management.AddField(str(target), safe, field_type)
        field_map[key] = safe

    cursor_fields = ["SHAPE@", *field_map.values()]
    with arcpy.da.InsertCursor(str(target), cursor_fields) as cursor:
        for feature in features:
            geom = make_geometry(feature.get("geometry"), sr)
            if geom is None:
                continue
            props = feature.get("properties") or {}
            values = []
            for key in field_map.keys():
                value = props.get(key)
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False)
                values.append(value)
            cursor.insertRow([geom, *values])
    return True


def main(args):
    manifest_path = Path(args["manifest_path"])
    workspace_dir = Path(args["workspace_dir"])
    data_dir = Path(args["data_dir"])
    project_dir = Path(args["project_dir"])
    maps_dir = Path(args["maps_dir"])
    template_aprx = args.get("template_aprx")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    sr = spatial_reference(manifest.get("coordinate_reference_system") or (manifest.get("spatial_scope") or {}).get("crs"))

    arcpy.env.overwriteOutput = True
    gdb_path = data_dir / "protocol_arcgis_workspace.gdb"
    if gdb_path.exists():
        arcpy.management.Delete(str(gdb_path))
    arcpy.management.CreateFileGDB(str(data_dir), gdb_path.name)

    layer_results = []
    feature_classes = []
    for layer in manifest.get("layers", []):
        source = layer.get("path")
        name = layer.get("name") or layer.get("id")
        if not source or str(source).startswith(("http://", "https://", "type=xyz")):
            layer_results.append({"layer_name": name, "imported": False, "message": "unsupported or missing local source", "source": source})
            continue
        source_path = Path(source)
        if not source_path.exists():
            layer_results.append({"layer_name": name, "imported": False, "message": "source missing", "source": source})
            continue
        target = gdb_path / safe_name(name)
        try:
            if source_path.suffix.lower() in {".geojson", ".json"}:
                wrote = write_geojson_feature_class(str(source_path), str(target), sr)
                if not wrote:
                    arcpy.conversion.JSONToFeatures(str(source_path), str(target))
            else:
                arcpy.management.CopyFeatures(str(source_path), str(target))
            count = int(arcpy.management.GetCount(str(target))[0])
            fields = field_names(str(target))
            feature_classes.append(str(target))
            layer_results.append({"layer_name": name, "imported": True, "feature_class": str(target), "feature_count": count, "fields": fields, "source": str(source_path)})
        except Exception as exc:
            layer_results.append({"layer_name": name, "imported": False, "message": str(exc), "source": str(source_path)})

    aprx_path = project_dir / "protocol_arcgis_workspace.aprx"
    project_created = False
    exported_maps = []
    project_message = "template_aprx not available; file geodatabase was created without an .aprx project"
    if template_aprx and Path(template_aprx).exists():
        try:
            aprx = arcpy.mp.ArcGISProject(str(template_aprx))
            maps = aprx.listMaps()
            map_obj = maps[0] if maps else aprx.createMap("Urban-Hermes GIS Workspace")
            for feature_class in feature_classes:
                map_obj.addDataFromPath(feature_class)
            aprx.saveACopy(str(aprx_path))
            project_created = aprx_path.exists()
            project_message = "ArcGIS Pro project created from template_aprx"
            for layout in aprx.listLayouts()[:1]:
                png = maps_dir / "protocol_arcgis_layout.png"
                pdf = maps_dir / "protocol_arcgis_layout.pdf"
                layout.exportToPNG(str(png), resolution=150)
                layout.exportToPDF(str(pdf))
                exported_maps.extend([{"path": str(png), "exists": png.exists(), "type": "png"}, {"path": str(pdf), "exists": pdf.exists(), "type": "pdf"}])
        except Exception as exc:
            project_message = f"ArcGIS Pro project creation failed: {exc}"

    result = {
        "status": "generated" if feature_classes else "failed",
        "workspace_dir": str(workspace_dir),
        "gdb_path": str(gdb_path),
        "gdb_exists": gdb_path.exists(),
        "project_path": str(aprx_path) if project_created else None,
        "project_created": project_created,
        "project_message": project_message,
        "layers": layer_results,
        "feature_class_count": len(feature_classes),
        "exported_maps": exported_maps,
        "arcpy_install_info": arcpy.GetInstallInfo(),
    }
    print(json.dumps(result, ensure_ascii=False, default=str), flush=True)


with Path(sys.argv[1]).open("r", encoding="utf-8") as handle:
    main(json.load(handle))
'''


def package_workspace(
    *,
    run_dir: str | Path,
    manifest_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    arcgis_python: str | None = None,
    template_aprx: str | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    source_manifest_path = resolve_manifest_path(run_dir, manifest_path)
    manifest = normalize_manifest(load_json(source_manifest_path), run_dir=run_dir)
    workspace_dir = Path(output_dir) if output_dir else run_dir / "arcgis_workspace"
    data_dir = workspace_dir / "data"
    project_dir = workspace_dir / "project"
    maps_dir = workspace_dir / "maps"
    manifest_dir = workspace_dir / "manifests"
    for directory in (data_dir, project_dir, maps_dir, manifest_dir):
        directory.mkdir(parents=True, exist_ok=True)

    manifest = _materialize_layers(manifest, data_dir=data_dir)
    template_aprx = resolve_template_aprx(template_aprx or "auto")
    manifest.setdefault("backend_workspaces", {})
    manifest["backend_workspaces"]["arcgis_pro"] = {
        "workspace_dir": str(workspace_dir),
        "gdb_path": str(data_dir / "protocol_arcgis_workspace.gdb"),
        "project_path": str(project_dir / "protocol_arcgis_workspace.aprx") if template_aprx else None,
        "template_aprx": template_aprx,
    }
    manifest.setdefault("known_limits", [])
    if not template_aprx:
        manifest["known_limits"].append("ArcGIS Pro .aprx creation requires a readable local template_aprx; this run validates FileGDB import only because no template was found.")
    workspace_manifest_path = manifest_dir / "spatial_reasoning_manifest.json"
    write_json(workspace_manifest_path, manifest)
    _write_readme(workspace_dir, manifest)

    arcgis_python = resolve_arcgis_python(arcgis_python)
    if not arcgis_python:
        result = {
            "backend": "arcgis_pro",
            "success": False,
            "workspace_dir": str(workspace_dir),
            "workspace_manifest": str(workspace_manifest_path),
            "error": "ArcGIS Pro Python not found",
        }
        write_json(manifest_dir / "arcgis_backend_package_result.json", result)
        return result

    script = project_dir / "_arcgis_protocol_packager.py"
    args_path = project_dir / "_arcgis_protocol_packager_args.json"
    script.write_text(ARCPY_PACKAGER_SCRIPT, encoding="utf-8")
    write_json(args_path, {"manifest_path": str(workspace_manifest_path), "workspace_dir": str(workspace_dir), "data_dir": str(data_dir), "project_dir": str(project_dir), "maps_dir": str(maps_dir), "template_aprx": template_aprx})
    completed = subprocess.run(
        arcgis_command(arcgis_python, str(script), str(args_path)),
        cwd=str(workspace_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    parsed = _parse_last_json(completed.stdout)
    success = bool(parsed and parsed.get("status") == "generated" and parsed.get("gdb_exists") and parsed.get("feature_class_count", 0) > 0)
    result = {
        "backend": "arcgis_pro",
        "success": success,
        "workspace_dir": str(workspace_dir),
        "workspace_manifest": str(workspace_manifest_path),
        "template_aprx_resolved": template_aprx,
        "returncode": completed.returncode,
        "parsed_stdout": parsed,
        "stdout_tail": (completed.stdout or "")[-4000:],
        "stderr_tail": (completed.stderr or "")[-4000:],
        "error": None if success else "ArcGIS Pro packager did not complete cleanly",
    }
    write_json(manifest_dir / "arcgis_backend_package_result.json", result)
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
                target = data_dir / "input" / subdir / source.name
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
        "# ArcGIS Pro Workspace",
        "",
        f"Task: {manifest.get('task_id')}",
        f"Case: {manifest.get('case_id')}",
        f"CRS: {manifest.get('coordinate_reference_system')}",
        "",
        "This workspace was generated through the Urban-Hermes GIS backend protocol.",
        "When a readable ArcGIS Pro template .aprx is available, the backend also writes a reviewable .aprx project. Otherwise it validates ArcPy import into a FileGDB.",
    ]
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
    parser = argparse.ArgumentParser(description="Package a manifest-driven ArcGIS Pro workspace.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--arcgis-python", default=None)
    parser.add_argument("--template-aprx", default=None)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    result = package_workspace(run_dir=args.run_dir, manifest_path=args.manifest, output_dir=args.output_dir, arcgis_python=args.arcgis_python, template_aprx=args.template_aprx, timeout=args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()