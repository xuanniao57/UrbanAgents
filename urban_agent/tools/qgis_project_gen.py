"""QGIS project generation for UrbanAgent GIS artifacts.

The primary path uses QGIS' own Python API to write the project file.  A
hand-written .qgs file is kept only as a fallback for machines without QGIS.
"""

from __future__ import annotations

import os
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree.ElementTree import Element, SubElement, tostring


QGIS_BUNDLED_PYTHON = os.environ.get(
    "QGIS_PYTHON_BIN",
    r"C:\Program Files\QGIS 3.40.11\bin\python-qgis-ltr.bat",
)


_QGIS_PROJECT_WRITER_SCRIPT = r'''
import json
import sys
from pathlib import Path

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsFillSymbol,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsProject,
    QgsSingleSymbolRenderer,
    QgsVectorLayer,
)


def _style_for(layer_name, geometry_type, overrides):
    base = {
        "boundary": {"label": "AOI boundary", "color": "255,255,255,0", "outline_color": "17,27,39,255", "outline_width": "0.8"},
        "context_buffer": {"label": "3x context buffer", "color": "255,255,255,0", "outline_color": "100,116,139,255", "outline_width": "0.5"},
        "context_roads": {"label": "Context road centerlines", "color": "148,163,184,150", "line_width": "0.25"},
        "context_buildings": {"label": "Context building footprints", "color": "229,231,235,100", "outline_color": "203,213,225,150", "outline_width": "0.1"},
        "context_function_buildings": {"label": "Context functional buildings", "color": "199,210,254,80", "outline_color": "165,180,252,120", "outline_width": "0.1"},
        "context_function_poi": {"label": "Context function POIs", "color": "134,239,172,160", "outline_color": "22,163,74,180", "size": "1.5"},
        "aoi_metric_summary": {"label": "AOI metric result summary", "color": "253,230,138,70", "outline_color": "146,64,14,220", "outline_width": "0.5"},
        "roads": {"label": "Road centerlines", "color": "71,85,105,255", "line_width": "0.5"},
        "buildings": {"label": "Building footprints", "color": "216,199,170,180", "outline_color": "138,122,99,255", "outline_width": "0.2"},
        "function_buildings": {"label": "Functional buildings", "color": "100,149,237,120", "outline_color": "70,90,140,255", "outline_width": "0.15"},
        "function_poi": {"label": "Function POIs", "color": "102,187,106,255", "outline_color": "46,125,50,255", "size": "2.0"},
    }.get(layer_name, {"label": layer_name, "color": "200,200,200,128", "outline_color": "80,80,80,255", "outline_width": "0.3"})
    if isinstance(overrides.get(layer_name), dict):
        base.update(overrides[layer_name])
    base["geometry_type"] = (geometry_type or "").upper()
    return base


def _apply_renderer(layer, style):
    geometry_type = style.get("geometry_type", "")
    if "POLYGON" in geometry_type:
        symbol = QgsFillSymbol.createSimple({
            "color": style.get("color", "200,200,200,128"),
            "outline_color": style.get("outline_color", "80,80,80,255"),
            "outline_width": str(style.get("outline_width", "0.3")),
        })
    elif "POINT" in geometry_type:
        symbol = QgsMarkerSymbol.createSimple({
            "color": style.get("color", "102,187,106,255"),
            "outline_color": style.get("outline_color", "46,125,50,255"),
            "size": str(style.get("size", "2.0")),
        })
    else:
        symbol = QgsLineSymbol.createSimple({
            "color": style.get("color", "71,85,105,255"),
            "line_width": str(style.get("line_width", style.get("outline_width", "0.5"))),
        })
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def write_project(args):
    gpkg = Path(args["gpkg_path"])
    out = Path(args["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    layers = args.get("layers", [])
    legend = args.get("legend", {}) or {}
    title = args.get("title") or "UrbanAgent GIS Project"

    qgs = QgsApplication([], False)
    qgs.initQgis()
    try:
        project = QgsProject.instance()
        project.clear()
        project.setTitle(title)
        project.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))

        diagnostics = []
        for layer_info in layers:
            layer_name = layer_info["name"]
            style = _style_for(layer_name, layer_info.get("geometry_type", ""), legend)
            uri = f"{gpkg.as_posix()}|layername={layer_name}"
            layer = QgsVectorLayer(uri, style.get("label", layer_name), "ogr")
            valid = bool(layer.isValid())
            diagnostics.append({
                "layer": layer_name,
                "label": style.get("label", layer_name),
                "valid": valid,
                "feature_count": int(layer.featureCount()) if valid else None,
                "crs": layer.crs().authid() if valid else None,
                "extent": layer.extent().toString() if valid else None,
                "error": layer.error().message() if not valid else "",
            })
            if not valid:
                continue
            _apply_renderer(layer, style)
            project.addMapLayer(layer)

        if not project.mapLayers():
            result = {"status": "no_layers", "diagnostics": diagnostics, "reason": "QGIS API could not load any GPKG layers"}
            print(json.dumps(result, ensure_ascii=False, default=str), flush=True)
            return result

        qgz_path = out / "urbanagent_gis_project.qgz"
        write_ok = bool(project.write(str(qgz_path)))

        reopen = QgsProject()
        read_ok = bool(reopen.read(str(qgz_path)))
        reopen_layers = [layer.name() for layer in reopen.mapLayers().values()]

        result = {
            "status": "generated" if write_ok and read_ok else "failed",
            "qgis_project": str(qgz_path),
            "layer_count": len(project.mapLayers()),
            "layers": [layer.name() for layer in project.mapLayers().values()],
            "diagnostics": diagnostics,
            "write_ok": write_ok,
            "read_ok": read_ok,
            "reopen_layer_count": len(reopen_layers),
            "reopen_layers": reopen_layers,
        }
        print(json.dumps(result, ensure_ascii=False, default=str), flush=True)
        return result
    finally:
        qgs.exitQgis()


arg_path = Path(sys.argv[1])
with arg_path.open("r", encoding="utf-8") as handle:
    args = json.load(handle)
write_project(args)
'''


def generate_qgs_project(
    gpkg_path: str,
    output_dir: str,
    legend: Optional[Dict[str, Any]] = None,
    title: str = "UrbanAgent GIS Project",
    launch_qgis: bool = True,
) -> Dict[str, Any]:
    """Generate a QGIS project file from a GPKG with multiple layers."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Probe GPKG layers
    layers = _probe_gpkg_layers(gpkg_path)

    qgis_result = _write_project_with_qgis_api(
        gpkg_path=gpkg_path,
        output_dir=str(out),
        layers=layers,
        legend=legend or {},
        title=title,
    )
    if qgis_result.get("status") == "generated":
        qgis_project = qgis_result["qgis_project"]
        launched = _launch_qgis(qgis_project) if launch_qgis else False
        artifacts = [{
            "type": "qgis_project",
            "path": qgis_project,
            "description": "QGIS API generated project with loaded layer tree and symbology",
        }]
        return {
            "status": "generated",
            "qgis_project": qgis_project,
            "layers": qgis_result.get("layers", []),
            "layer_count": qgis_result.get("layer_count", 0),
            "artifacts": artifacts,
            "qgis_launched": launched,
            "diagnostics": qgis_result.get("diagnostics", []),
            "write_ok": qgis_result.get("write_ok"),
            "read_ok": qgis_result.get("read_ok"),
            "reopen_layer_count": qgis_result.get("reopen_layer_count"),
            "instruction": f"Open {qgis_project} in QGIS Desktop" if not launched else None,
        }

    # Build fallback QGIS project XML when QGIS Python is unavailable.
    qgs = _build_qgs_xml(gpkg_path, layers, legend or {}, title)

    qgs_path = out / "urbanagent_gis_project.qgs"
    qgs_path.write_text(qgs, encoding="utf-8")

    artifacts = [{"type": "qgis_project", "path": str(qgs_path), "description": "QGIS project file with layer symbology"}]

    # Launch QGIS if requested
    launched = False
    if launch_qgis:
        launched = _launch_qgis(str(qgs_path))

    return {
        "status": "generated",
        "qgis_project": str(qgs_path),
        "layers": [l["name"] for l in layers],
        "layer_count": len(layers),
        "artifacts": artifacts,
        "qgis_launched": launched,
        "fallback_reason": qgis_result.get("reason") or qgis_result.get("status"),
        "diagnostics": qgis_result.get("diagnostics", []),
        "instruction": f"Open {qgs_path} in QGIS Desktop" if not launched else None,
    }


def _write_project_with_qgis_api(
    *,
    gpkg_path: str,
    output_dir: str,
    layers: List[Dict[str, Any]],
    legend: Dict[str, Any],
    title: str,
) -> Dict[str, Any]:
    """Write a real QGIS project using the bundled QGIS Python runtime."""
    qgis_python = Path(QGIS_BUNDLED_PYTHON)
    if not qgis_python.exists():
        return {"status": "unavailable", "reason": f"QGIS Python not found at {qgis_python}"}

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    script_path = out / "_qgis_project_writer.py"
    args_path = out / "_qgis_project_writer_args.json"
    script_path.write_text(_QGIS_PROJECT_WRITER_SCRIPT, encoding="utf-8")
    args_path.write_text(json.dumps({
        "gpkg_path": str(gpkg_path),
        "output_dir": str(output_dir),
        "layers": layers,
        "legend": legend,
        "title": title,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        proc = subprocess.run(
            [str(qgis_python), str(script_path), str(args_path)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(out),
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        _cleanup_temp_writer_files(script_path, args_path)
        return {"status": "timeout", "reason": "QGIS project writer timed out after 120 seconds"}
    except Exception as error:
        _cleanup_temp_writer_files(script_path, args_path)
        return {"status": "failed", "reason": str(error)}

    _cleanup_temp_writer_files(script_path, args_path)

    stdout_lines = [line for line in proc.stdout.strip().splitlines() if line.strip()]
    if stdout_lines:
        try:
            parsed = json.loads(stdout_lines[-1])
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    if proc.returncode != 0:
        return {
            "status": "failed",
            "returncode": proc.returncode,
            "reason": (proc.stderr or proc.stdout).strip()[:2000],
            "stdout": proc.stdout.strip()[:1000],
        }

    try:
        return json.loads(stdout_lines[-1])
    except Exception as error:
        return {
            "status": "failed",
            "reason": f"Could not parse QGIS writer output: {error}",
            "stdout": proc.stdout.strip()[:2000],
            "stderr": proc.stderr.strip()[:1000],
        }


def _cleanup_temp_writer_files(*paths: Path) -> None:
    """Remove transient QGIS writer files after subprocess execution."""
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


def _probe_gpkg_layers(gpkg_path: str) -> List[Dict[str, Any]]:
    """Probe available layers in a GPKG."""
    layers = []
    try:
        import sqlite3
        conn = sqlite3.connect(gpkg_path)
        cursor = conn.execute("SELECT table_name FROM gpkg_contents")
        for (name,) in cursor.fetchall():
            # Get geometry type
            geom_cursor = conn.execute(
                "SELECT geometry_type_name FROM gpkg_geometry_columns WHERE table_name = ?", (name,)
            )
            geom_type = geom_cursor.fetchone()
            layers.append({
                "name": name,
                "geometry_type": geom_type[0] if geom_type else "GEOMETRY",
            })
        conn.close()
    except Exception:
        pass
    return layers


def _build_qgs_xml(
    gpkg_path: str,
    layers: List[Dict[str, Any]],
    legend: Dict[str, Any],
    title: str,
) -> str:
    """Build a QGIS 3.x project XML string."""
    qgis = Element("qgis", version="3.40.0-Bratislava")
    qgis.set("projectname", title)

    # Home (project CRS)
    home = SubElement(qgis, "home")
    dest = SubElement(home, "destination")
    dest.set("epsg", "4326")

    # Project properties
    props = SubElement(qgis, "properties")
    gui = SubElement(props, "Gui")
    canvas = SubElement(gui, "CanvasColor")
    SubElement(canvas, "Red").text = "255"
    SubElement(canvas, "Green").text = "255"
    SubElement(canvas, "Blue").text = "255"

    # Default layer styles
    styles = {
        "boundary": {"color": "17,27,39,255", "fill": "17,27,39,0", "width": "0.8"},
        "context_buffer": {"color": "100,116,139,255", "fill": "255,255,255,0", "width": "0.5"},
        "context_roads": {"color": "148,163,184,150", "width": "0.25"},
        "context_buildings": {"color": "203,213,225,150", "fill": "229,231,235,100", "width": "0.1"},
        "context_function_buildings": {"color": "165,180,252,120", "fill": "199,210,254,80", "width": "0.1"},
        "context_function_poi": {"color": "22,163,74,180", "fill": "134,239,172,160", "size": "1.5"},
        "aoi_metric_summary": {"color": "146,64,14,220", "fill": "253,230,138,70", "width": "0.5"},
        "roads": {"color": "71,85,105,255", "width": "0.5"},
        "buildings": {"color": "138,122,99,255", "fill": "216,199,170,255", "width": "0.2"},
        "function_buildings": {"color": "192,192,192,255", "fill": "100,149,237,120", "width": "0.15"},
        "function_poi": {"color": "46,125,50,255", "fill": "102,187,106,255", "size": "2.0"},
    }
    # Apply legend overrides
    for layer_name, override in (legend or {}).items():
        if layer_name in styles and isinstance(override, dict):
            styles[layer_name].update(override)

    # Map layers
    project_layers = SubElement(qgis, "projectlayers")
    for idx, layer_info in enumerate(layers):
        layer_name = layer_info["name"]
        style = styles.get(layer_name, {"color": "100,100,100,255", "fill": "200,200,200,128", "width": "0.3"})

        maplayer = SubElement(project_layers, "maplayer")
        maplayer.set("type", "vector")
        maplayer.set("name", layer_name)
        maplayer.set("show", "1")

        # datasource must be direct child of maplayer (QGIS 3.x), NOT inside provider
        datasource = SubElement(maplayer, "datasource")
        datasource.text = f"{gpkg_path}|layername={layer_name}"
        provider = SubElement(maplayer, "provider")
        provider.set("encoding", "UTF-8")
        provider.text = "ogr"

        # Determine geometry type (case-insensitive)
        geom_type = layer_info.get("geometry_type", "").upper()

        # Simple renderer
        renderer = SubElement(maplayer, "renderer-v2")
        renderer.set("type", "singleSymbol")
        renderer.set("symbollevels", "0")
        renderer.set("forceraster", "0")

        if "POLYGON" in geom_type:
            symbol = SubElement(renderer, "symbol")
            symbol.set("type", "fill")
            symbol.set("name", layer_name)
            symbol.set("alpha", "1")
            layer_style = SubElement(symbol, "layer")
            layer_style.set("class", "SimpleFill")
            layer_style.set("pass", "0")
            layer_style.set("enabled", "1")
            border = style.get("color", "0,0,0,255")
            fill = style.get("fill", "200,200,200,128")
            SubElement(layer_style, "prop", k="color", v=fill)
            SubElement(layer_style, "prop", k="outline_color", v=border)
            SubElement(layer_style, "prop", k="outline_width", v=style.get("width", "0.3"))
        elif "POINT" in geom_type:
            symbol = SubElement(renderer, "symbol")
            symbol.set("type", "marker")
            symbol.set("name", layer_name)
            symbol.set("alpha", "1")
            layer_style = SubElement(symbol, "layer")
            layer_style.set("class", "SimpleMarker")
            layer_style.set("pass", "0")
            layer_style.set("enabled", "1")
            SubElement(layer_style, "prop", k="color", v=style.get("fill", "102,187,106,255"))
            SubElement(layer_style, "prop", k="outline_color", v=style.get("color", "46,125,50,255"))
            SubElement(layer_style, "prop", k="size", v=style.get("size", "2.0"))
        else:
            symbol = SubElement(renderer, "symbol")
            symbol.set("type", "line")
            symbol.set("name", layer_name)
            symbol.set("alpha", "1")
            layer_style = SubElement(symbol, "layer")
            layer_style.set("class", "SimpleLine")
            layer_style.set("pass", "0")
            layer_style.set("enabled", "1")
            SubElement(layer_style, "prop", k="line_color", v=style.get("color", "0,0,0,255"))
            SubElement(layer_style, "prop", k="line_width", v=style.get("width", "0.5"))

    # Layout
    layout = SubElement(qgis, "Layouts")
    print_layout = SubElement(layout, "Layout")
    print_layout.set("name", "UrbanAgent_Map")
    print_layout.set("units", "mm")

    # Add map item to layout
    composer = SubElement(print_layout, "ComposerMap")
    composer.set("name", "map0")
    composer.set("x", "5")
    composer.set("y", "5")
    composer.set("width", "287")
    composer.set("height", "190")

    # Return pretty-printed XML
    import xml.dom.minidom
    dom = xml.dom.minidom.parseString(tostring(qgis, "utf-8"))
    return dom.toprettyxml(indent="  ")


def _launch_qgis(project_path: str) -> bool:
    """Try to launch QGIS with the project file."""
    candidates = [
        r"C:\Program Files\QGIS 3.40.11\bin\qgis-ltr-bin.exe",
        r"C:\Program Files\QGIS 3.34\bin\qgis-ltr-bin.exe",
        r"C:\Program Files\QGIS 3.40.11\bin\qgis-bin.exe",
        r"C:\OSGeo4W64\bin\qgis-ltr-bin.exe",
    ]
    for qgis_bin in candidates:
        if Path(qgis_bin).exists():
            subprocess.Popen([qgis_bin, "--project", project_path])
            return True
    return False


def build_qgis_project_capability(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Capability entry point for QGIS project generation."""
    gpkg_path = arguments.get("gpkg_path", "")
    output_dir = arguments.get("output_dir", arguments.get("artifact_dir", "artifacts"))
    legend = arguments.get("legend", {})
    title = arguments.get("title", "UrbanAgent GIS Project")
    launch = arguments.get("launch_qgis", True)

    if not gpkg_path:
        # Try to find GPKG from context
        for k in ("artifact_dir", "output_dir", "run_dir"):
            d = arguments.get(k)
            if d:
                candidate = Path(d) / "artifacts" / "urbanagent_gis_layers.gpkg"
                if candidate.exists():
                    gpkg_path = str(candidate)
                    break

    if not gpkg_path:
        return {"status": "unavailable", "reason": "No GPKG path provided or auto-discovered"}

    return generate_qgs_project(gpkg_path, output_dir, legend, title, launch)
