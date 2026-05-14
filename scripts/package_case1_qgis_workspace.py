"""Package Case1 Hermes-Urban outputs into a QGIS workspace.

The script creates a directory that can be opened directly in QGIS and also
read back by agents for spatial reasoning:

- copied source layers
- metric 200m grid layers
- road accessibility / space-syntax proxy layers
- SVG preview
- QGIS project (.qgz/.qgs)
- manifest JSON for agents
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import subprocess
import textwrap
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import geopandas as gpd
import networkx as nx
from pyproj import CRS
from shapely.geometry import LineString, Point, box, mapping, shape
from shapely.ops import unary_union


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_DIR = REPO_ROOT / "experiments" / "k41_200m_grid_20260514" / "hermes_urban_windows_native_20260514_131320"
DEFAULT_QGIS_PYTHON = Path(r"C:\Program Files\QGIS 3.40.11\bin\python-qgis-ltr.bat")
WGS84 = "EPSG:4326"
METRIC_CRS = "EPSG:32651"


def read_layer(path: Path) -> gpd.GeoDataFrame:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    features = data.get("features", [])
    rows = []
    geometries = []
    for feature in features:
        rows.append(dict(feature.get("properties") or {}))
        geom = feature.get("geometry")
        geometries.append(shape(geom) if geom else None)
    crs_name = WGS84
    crs = data.get("crs")
    if isinstance(crs, dict):
        crs_name = ((crs.get("properties") or {}).get("name")) or crs_name
    return gpd.GeoDataFrame(rows, geometry=geometries, crs=crs_name)


def write_geojson(gdf: gpd.GeoDataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    crs_name = str(gdf.crs) if gdf.crs else WGS84
    features = []
    for _, row in gdf.iterrows():
        props = {}
        for col in gdf.columns:
            if col == "geometry":
                continue
            props[col] = jsonable(row[col])
        geom = row.geometry
        features.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": mapping(geom) if geom is not None and not geom.is_empty else None,
            }
        )
    payload = {
        "type": "FeatureCollection",
        "name": path.stem,
        "crs": {"type": "name", "properties": {"name": crs_name}},
        "features": features,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def safe_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def haversine_like_length(line: LineString) -> float:
    return float(line.length)


def building_function(row: Any) -> str:
    for key in ("building", "amenity", "shop", "tourism", "building:use"):
        value = row.get(key)
        if value not in (None, "", "nan"):
            return str(value)
    return "unknown"


def entropy(values: list[str]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    counts = Counter(values)
    total = sum(counts.values())
    raw = -sum((count / total) * math.log(count / total) for count in counts.values())
    norm = raw / math.log(len(counts)) if len(counts) > 1 else 0.0
    return raw, norm


def node_key(x: float, y: float) -> tuple[float, float]:
    return (round(x, 1), round(y, 1))


def build_road_accessibility(roads_metric: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    exploded = roads_metric.explode(index_parts=False, ignore_index=True).copy()
    exploded = exploded[exploded.geometry.notna() & ~exploded.geometry.is_empty].copy()
    exploded = exploded[exploded.geometry.geom_type == "LineString"].copy()
    exploded["road_uid"] = [f"r{i}" for i in range(len(exploded))]

    graph = nx.Graph()
    road_nodes: dict[str, list[tuple[float, float]]] = {}
    road_lengths: dict[str, float] = {}

    for _, row in exploded.iterrows():
        uid = row["road_uid"]
        coords = list(row.geometry.coords)
        keys = [node_key(x, y) for x, y in coords]
        road_nodes[uid] = keys
        road_lengths[uid] = float(row.geometry.length)
        for key, (x, y) in zip(keys, coords):
            graph.add_node(key, x=float(x), y=float(y))
        for left, right in zip(keys, keys[1:]):
            if left == right:
                continue
            length = Point(left).distance(Point(right))
            if graph.has_edge(left, right):
                graph[left][right]["weight"] = min(graph[left][right]["weight"], length)
            else:
                graph.add_edge(left, right, weight=length)

    component_by_node: dict[tuple[float, float], int] = {}
    component_sizes: dict[int, int] = {}
    closeness: dict[tuple[float, float], float] = {}
    for component_id, nodes in enumerate(nx.connected_components(graph)):
        sub = graph.subgraph(nodes)
        component_sizes[component_id] = sub.number_of_nodes()
        for node in nodes:
            component_by_node[node] = component_id
        if sub.number_of_nodes() > 1:
            closeness.update(nx.closeness_centrality(sub, distance="weight"))
        else:
            closeness.update({node: 0.0 for node in nodes})

    close_values = list(closeness.values())
    min_close = min(close_values) if close_values else 0.0
    max_close = max(close_values) if close_values else 1.0
    close_span = max(max_close - min_close, 1e-12)

    road_metrics = []
    for _, row in exploded.iterrows():
        uid = row["road_uid"]
        keys = road_nodes[uid]
        degrees = [graph.degree(key) for key in keys if key in graph]
        close = [closeness.get(key, 0.0) for key in keys]
        comp_counter = Counter(component_by_node.get(key, -1) for key in keys)
        component_id = comp_counter.most_common(1)[0][0] if comp_counter else -1
        accessibility = (sum(close) / len(close) - min_close) / close_span if close else 0.0
        road_metrics.append(
            {
                "length_m": round(road_lengths[uid], 2),
                "mean_node_degree": round(sum(degrees) / len(degrees), 3) if degrees else 0.0,
                "max_node_degree": max(degrees) if degrees else 0,
                "component_id": component_id,
                "component_nodes": component_sizes.get(component_id, 0),
                "closeness_mean": round(sum(close) / len(close), 9) if close else 0.0,
                "accessibility_score": round(float(accessibility), 6),
            }
        )

    roads_out = exploded.copy()
    for key in road_metrics[0].keys() if road_metrics else []:
        roads_out[key] = [metric[key] for metric in road_metrics]
    roads_out = roads_out.to_crs(WGS84)

    node_rows = []
    for key, data in graph.nodes(data=True):
        value = closeness.get(key, 0.0)
        node_rows.append(
            {
                "node_id": f"{key[0]}_{key[1]}",
                "degree": graph.degree(key),
                "component_id": component_by_node.get(key, -1),
                "component_nodes": component_sizes.get(component_by_node.get(key, -1), 0),
                "closeness": round(value, 9),
                "accessibility_score": round((value - min_close) / close_span, 6),
                "geometry": Point(data["x"], data["y"]),
            }
        )
    nodes_out = gpd.GeoDataFrame(node_rows, geometry="geometry", crs=METRIC_CRS).to_crs(WGS84)
    return roads_out, nodes_out


def make_metric_grid(
    context: gpd.GeoDataFrame,
    buildings: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame,
    roads_access: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    context_m = context.to_crs(METRIC_CRS)
    buildings_m = buildings.to_crs(METRIC_CRS)
    roads_m = roads.to_crs(METRIC_CRS)
    roads_access_m = roads_access.to_crs(METRIC_CRS)
    context_union = unary_union(context_m.geometry)
    minx, miny, maxx, maxy = context_union.bounds

    cells = []
    cell_id = 0
    row = 0
    y = miny
    while y < maxy:
        col = 0
        x = minx
        while x < maxx:
            geom = box(x, y, x + 200.0, y + 200.0)
            if geom.intersects(context_union):
                cells.append({"cell_id": cell_id, "row": row, "col": col, "grid_size_m": 200, "geometry": geom})
                cell_id += 1
            x += 200.0
            col += 1
        y += 200.0
        row += 1

    grid = gpd.GeoDataFrame(cells, geometry="geometry", crs=METRIC_CRS)
    metric_rows = []
    for _, cell in grid.iterrows():
        cell_geom = cell.geometry
        clipped_area = cell_geom.intersection(context_union).area
        b_subset = buildings_m[buildings_m.intersects(cell_geom)]
        r_subset = roads_m[roads_m.intersects(cell_geom)]
        ra_subset = roads_access_m[roads_access_m.intersects(cell_geom)]

        building_area = 0.0
        if not b_subset.empty:
            building_area = float(sum(geom.intersection(cell_geom).area for geom in b_subset.geometry if geom and not geom.is_empty))
        road_length = 0.0
        if not r_subset.empty:
            road_length = float(sum(geom.intersection(cell_geom).length for geom in r_subset.geometry if geom and not geom.is_empty))

        heritage_mask = b_subset.apply(
            lambda r: any(r.get(key) not in (None, "", "nan") for key in ("heritage", "heritage:operator", "heritage:ref", "start_date", "old_name", "tourism")),
            axis=1,
        ) if not b_subset.empty else []
        heritage_count = int(sum(heritage_mask)) if len(b_subset) else 0
        funcs = [building_function(row) for _, row in b_subset.iterrows()]
        mix_entropy, mix_entropy_norm = entropy(funcs)
        access_mean = float(ra_subset["accessibility_score"].mean()) if not ra_subset.empty and "accessibility_score" in ra_subset else 0.0

        metric_rows.append(
            {
                "cell_area_m2": round(float(cell_geom.area), 2),
                "context_area_m2": round(float(clipped_area), 2),
                "building_count": int(len(b_subset)),
                "heritage_building_count": heritage_count,
                "road_count": int(len(r_subset)),
                "building_footprint_area_m2": round(building_area, 2),
                "building_coverage_ratio": round(building_area / cell_geom.area, 6),
                "road_length_m": round(road_length, 2),
                "road_density_m_per_ha": round(road_length / max(clipped_area, 1.0) * 10000.0, 3),
                "function_mix_entropy": round(mix_entropy, 6),
                "function_mix_entropy_norm": round(mix_entropy_norm, 6),
                "heritage_proxy_score": round(heritage_count / max(len(b_subset), 1), 6),
                "road_accessibility_mean": round(access_mean, 6),
            }
        )

    metrics = gpd.GeoDataFrame([{**dict(grid.iloc[i].drop(labels="geometry")), **metric_rows[i], "geometry": grid.iloc[i].geometry} for i in range(len(grid))], geometry="geometry", crs=METRIC_CRS)
    return metrics.to_crs(WGS84)


def write_csv(gdf: gpd.GeoDataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [col for col in gdf.columns if col != "geometry"]
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for _, row in gdf.iterrows():
            writer.writerow({field: row.get(field) for field in fields})


def geometry_type_counts(gdf: gpd.GeoDataFrame) -> dict[str, int]:
    return dict(Counter(str(item) for item in gdf.geometry.geom_type))


def layer_summary(path: Path, purpose: str, metric_fields: list[str] | None = None) -> dict[str, Any]:
    gdf = read_layer(path)
    return {
        "path": str(path),
        "purpose": purpose,
        "crs": str(gdf.crs),
        "feature_count": int(len(gdf)),
        "geometry_types": geometry_type_counts(gdf),
        "fields": [str(col) for col in gdf.columns if col != "geometry"],
        "metric_fields": metric_fields or [],
    }


def write_svg_preview(grid: gpd.GeoDataFrame, path: Path) -> None:
    grid_m = grid.to_crs(METRIC_CRS)
    minx, miny, maxx, maxy = grid_m.total_bounds
    width = 1200
    height = max(420, int(width * (maxy - miny) / max(maxx - minx, 1)))
    values = list(grid_m["building_coverage_ratio"].fillna(0))
    vmax = max(values) if values else 1.0

    def project(x: float, y: float) -> tuple[float, float]:
        px = (x - minx) / max(maxx - minx, 1) * width
        py = height - (y - miny) / max(maxy - miny, 1) * height
        return px, py

    def color(value: float) -> str:
        t = 0 if vmax <= 0 else min(max(value / vmax, 0), 1)
        r = int(255 - 120 * t)
        g = int(245 - 160 * t)
        b = int(210 - 170 * t)
        return f"#{r:02x}{g:02x}{b:02x}"

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f7f7f2"/>',
        '<text x="20" y="32" font-family="Arial" font-size="22" fill="#222">Case1 Nanjing Road 200m Grid - Building Coverage</text>',
    ]
    for _, row in grid_m.iterrows():
        coords = list(row.geometry.exterior.coords)
        points = " ".join(f"{project(x, y)[0]:.1f},{project(x, y)[1]:.1f}" for x, y in coords)
        parts.append(f'<polygon points="{points}" fill="{color(float(row["building_coverage_ratio"]))}" stroke="#ffffff" stroke-width="1.2"/>')
        cx, cy = project(row.geometry.centroid.x, row.geometry.centroid.y)
        parts.append(f'<text x="{cx:.1f}" y="{cy:.1f}" text-anchor="middle" font-family="Arial" font-size="10" fill="#202020">{int(row["cell_id"])}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def write_qgis_project_script(workspace: Path, project_qgz: Path, project_qgs: Path, layer_paths: dict[str, Path]) -> Path:
    script = workspace / "scripts" / "build_qgis_project.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        textwrap.dedent(
            f"""
            from pathlib import Path

            from qgis.core import (
                QgsApplication,
                QgsFillSymbol,
                QgsGraduatedSymbolRenderer,
                QgsLayerTreeGroup,
                QgsLineSymbol,
                QgsMarkerSymbol,
                QgsProject,
                QgsRasterLayer,
                QgsRendererRange,
                QgsSingleSymbolRenderer,
                QgsVectorLayer,
            )

            workspace = Path(r"{workspace}")
            project_qgz = Path(r"{project_qgz}")
            project_qgs = Path(r"{project_qgs}")

            app = QgsApplication([], False)
            app.initQgis()
            project = QgsProject.instance()
            project.clear()
            project.setTitle("Hermes-Urban Case1 Nanjing Road 200m Grid Workspace")

            root = project.layerTreeRoot()

            def group(name):
                existing = root.findGroup(name)
                return existing if existing else root.addGroup(name)

            def add_vector(group_name, name, path, style=None, graduated=None, subset=None):
                layer = QgsVectorLayer(str(path), name, "ogr")
                if not layer.isValid():
                    print(f"INVALID_LAYER {{name}} {{path}}")
                    return None
                if subset:
                    layer.setSubsetString(subset)
                if graduated:
                    field, colors = graduated
                    values = []
                    for feature in layer.getFeatures():
                        try:
                            values.append(float(feature[field]))
                        except Exception:
                            pass
                    if values:
                        low, high = min(values), max(values)
                        span = max(high - low, 1e-9)
                        ranges = []
                        for idx, color in enumerate(colors):
                            lower = low + span * idx / len(colors)
                            upper = low + span * (idx + 1) / len(colors)
                            symbol = QgsFillSymbol.createSimple({{"color": color, "outline_color": "#ffffff", "outline_width": "0.18"}}) if layer.geometryType() == 2 else QgsLineSymbol.createSimple({{"color": color, "width": "0.65"}})
                            ranges.append(QgsRendererRange(lower, upper, symbol, f"{{lower:.3f}} - {{upper:.3f}}"))
                        layer.setRenderer(QgsGraduatedSymbolRenderer(field, ranges))
                elif style == "context":
                    symbol = QgsFillSymbol.createSimple({{"color": "255,255,255,0", "outline_color": "#d1495b", "outline_width": "0.8"}})
                    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
                elif style == "buildings":
                    symbol = QgsFillSymbol.createSimple({{"color": "120,120,120,75", "outline_color": "#575757", "outline_width": "0.05"}})
                    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
                elif style == "heritage":
                    symbol = QgsFillSymbol.createSimple({{"color": "#b85c38", "outline_color": "#5a2113", "outline_width": "0.25"}})
                    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
                elif style == "roads":
                    symbol = QgsLineSymbol.createSimple({{"color": "#777777", "width": "0.35"}})
                    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
                elif style == "nodes":
                    symbol = QgsMarkerSymbol.createSimple({{"name": "circle", "color": "#2b7a78", "size": "1.25", "outline_color": "#ffffff", "outline_width": "0.1"}})
                    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
                project.addMapLayer(layer, False)
                group(group_name).addLayer(layer)
                return layer

            add_vector("01 Source data", "Context buffer 3x", r"{layer_paths['context']}", style="context")
            add_vector("01 Source data", "OSM buildings", r"{layer_paths['buildings']}", style="buildings")
            add_vector("01 Source data", "OSM heritage/start_date buildings", r"{layer_paths['buildings']}", style="heritage", subset='"heritage" IS NOT NULL OR "start_date" IS NOT NULL OR "old_name" IS NOT NULL OR "tourism" IS NOT NULL')
            add_vector("01 Source data", "OSM roads", r"{layer_paths['roads']}", style="roads")

            grid_colors = ["#fff7bc", "#fec44f", "#fe9929", "#ec7014", "#cc4c02"]
            add_vector("02 200m grid metrics", "Grid - building coverage", r"{layer_paths['grid_metrics']}", graduated=("building_coverage_ratio", grid_colors))
            add_vector("02 200m grid metrics", "Grid - building count", r"{layer_paths['grid_metrics']}", graduated=("building_count", ["#edf8fb", "#b2e2e2", "#66c2a4", "#2ca25f", "#006d2c"]))
            add_vector("02 200m grid metrics", "Grid - heritage proxy score", r"{layer_paths['grid_metrics']}", graduated=("heritage_proxy_score", ["#f7f7f7", "#cccccc", "#969696", "#636363", "#252525"]))
            add_vector("02 200m grid metrics", "Grid - road density", r"{layer_paths['grid_metrics']}", graduated=("road_density_m_per_ha", ["#eff3ff", "#bdd7e7", "#6baed6", "#3182bd", "#08519c"]))
            add_vector("02 200m grid metrics", "Grid centroids / cell IDs", r"{layer_paths['centroids']}", style="nodes")

            add_vector("03 Road accessibility", "Road accessibility score", r"{layer_paths['road_access']}", graduated=("accessibility_score", ["#d9f0a3", "#addd8e", "#78c679", "#31a354", "#006837"]))
            add_vector("03 Road accessibility", "Road mean node degree", r"{layer_paths['road_access']}", graduated=("mean_node_degree", ["#f1eef6", "#d7b5d8", "#df65b0", "#dd1c77", "#980043"]))
            add_vector("03 Road accessibility", "Road network nodes", r"{layer_paths['road_nodes']}", style="nodes")

            add_vector("04 QGIS derived checks", "QGIS fixed grid", r"{layer_paths['qgis_fixed']}", graduated=("building_count", ["#ffffcc", "#c2e699", "#78c679", "#31a354", "#006837"]))
            add_vector("04 QGIS derived checks", "QGIS fixed grid centroids", r"{layer_paths['qgis_centroids']}", style="nodes")

            # Add the opaque XYZ basemap last so it is at the bottom of the
            # layer tree. If it sits above vectors, refreshing/toggling layers
            # can make the canvas look like a solid blue OSM ocean tile.
            osm = QgsRasterLayer("type=xyz&url=https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png&zmax=19&zmin=0", "OpenStreetMap XYZ", "wms")
            if osm.isValid():
                osm.setOpacity(0.75)
                project.addMapLayer(osm, False)
                group("99 Basemap").addLayer(osm)

            project.write(str(project_qgz))
            project.write(str(project_qgs))
            print(f"PROJECT_QGZ={{project_qgz}}")
            print(f"PROJECT_QGS={{project_qgs}}")
            app.exitQgis()
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return script


def build_workspace(run_dir: Path, qgis_python: Path | None = None) -> dict[str, Any]:
    outputs = run_dir / "outputs"
    workspace = run_dir / "qgis_workspace"
    data_dir = workspace / "data"
    derived_dir = data_dir / "derived"
    source_dir = data_dir / "source"
    grid_dir = data_dir / "grid"
    project_dir = workspace / "project"
    manifest_dir = workspace / "manifests"
    styles_dir = workspace / "styles"
    for path in (derived_dir, source_dir, grid_dir, project_dir, manifest_dir, styles_dir):
        path.mkdir(parents=True, exist_ok=True)

    source_paths = {
        "context": REPO_ROOT / "artifacts" / "case1_shanghai_nanjing_supplemented" / "case1_context_buffer_3x.geojson",
        "roads": REPO_ROOT / "artifacts" / "case1_shanghai_nanjing_supplemented" / "osm_roads_context_3x.geojson",
        "buildings": REPO_ROOT / "artifacts" / "case1_shanghai_nanjing_supplemented" / "osm_buildings_context_3x.geojson",
    }
    copied_sources = {}
    for key, src in source_paths.items():
        dst = source_dir / src.name
        safe_copy(src, dst)
        copied_sources[key] = dst

    for name in (
        "case1_200m_grid.geojson",
        "case1_200m_grid_with_metrics.geojson",
        "case1_200m_grid_metrics.csv",
        "case1_200m_grid_qgis_fixed.geojson",
        "case1_200m_grid_qgis_centroids.geojson",
        "case1_200m_grid_preview.svg",
        "final_report.md",
    ):
        src = outputs / name
        if src.exists():
            safe_copy(src, grid_dir / name)

    context = read_layer(copied_sources["context"])
    roads = read_layer(copied_sources["roads"])
    buildings = read_layer(copied_sources["buildings"])

    roads_access, road_nodes = build_road_accessibility(roads.to_crs(METRIC_CRS))
    road_access_path = derived_dir / "case1_roads_accessibility_space_syntax_proxy.geojson"
    road_nodes_path = derived_dir / "case1_road_nodes_accessibility.geojson"
    write_geojson(roads_access, road_access_path)
    write_geojson(road_nodes, road_nodes_path)

    grid_metrics = make_metric_grid(context, buildings, roads, roads_access)
    grid_metrics_path = derived_dir / "case1_200m_grid_metric_layers.geojson"
    grid_metrics_csv_path = derived_dir / "case1_200m_grid_metric_layers.csv"
    write_geojson(grid_metrics, grid_metrics_path)
    write_csv(grid_metrics, grid_metrics_csv_path)
    write_svg_preview(grid_metrics, workspace / "case1_200m_grid_metric_preview.svg")

    project_qgz = project_dir / "case1_nanjing_road_200m_grid_workspace.qgz"
    project_qgs = project_dir / "case1_nanjing_road_200m_grid_workspace.qgs"
    layer_paths = {
        "context": copied_sources["context"],
        "roads": copied_sources["roads"],
        "buildings": copied_sources["buildings"],
        "grid_metrics": grid_metrics_path,
        "centroids": grid_dir / "case1_200m_grid_qgis_centroids.geojson",
        "road_access": road_access_path,
        "road_nodes": road_nodes_path,
        "qgis_fixed": grid_dir / "case1_200m_grid_qgis_fixed.geojson",
        "qgis_centroids": grid_dir / "case1_200m_grid_qgis_centroids.geojson",
    }
    qgis_script = write_qgis_project_script(workspace, project_qgz, project_qgs, layer_paths)

    qgis_result = None
    if qgis_python and qgis_python.exists():
        completed = subprocess.run(
            [str(qgis_python), str(qgis_script)],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            shell=False,
        )
        qgis_result = {
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }

    layers = [
        layer_summary(copied_sources["context"], "study area plus context buffer"),
        layer_summary(copied_sources["roads"], "raw OSM road network"),
        layer_summary(copied_sources["buildings"], "raw OSM buildings with heritage/start_date/function proxy fields"),
        layer_summary(grid_metrics_path, "true 200m grid cells with metric attributes", ["building_coverage_ratio", "road_density_m_per_ha", "function_mix_entropy_norm", "heritage_proxy_score", "road_accessibility_mean"]),
        layer_summary(road_access_path, "road-network accessibility / space-syntax proxy", ["length_m", "mean_node_degree", "component_nodes", "closeness_mean", "accessibility_score"]),
        layer_summary(road_nodes_path, "road graph nodes used for accessibility reasoning", ["degree", "component_nodes", "closeness", "accessibility_score"]),
    ]

    manifest = {
        "workspace": str(workspace),
        "project_qgz": str(project_qgz),
        "project_qgs": str(project_qgs),
        "created_for": "Hermes-Urban Case1 Nanjing Road 200m grid workspace",
        "crs": {"display": WGS84, "metric_computation": METRIC_CRS, "metric_crs_note": str(CRS.from_user_input(METRIC_CRS))},
        "layers": layers,
        "qgis_result": qgis_result,
        "agent_reasoning_notes": [
            "Read this manifest first before spatial reasoning.",
            "Use case1_200m_grid_metric_layers.geojson for grid-level X variables.",
            "Use case1_roads_accessibility_space_syntax_proxy.geojson for road-network accessibility proxy reasoning.",
            "OSM heritage/start_date/old_name/tourism fields are proxy evidence, not authoritative heritage registers.",
            "For precise publication metrics, recompute grid/road lengths in EPSG:32651 or a locally validated projected CRS.",
        ],
        "known_limits": [
            "Road accessibility is a graph-topology proxy based on available OSM roads, not a full Depthmap/space-syntax axial or segment analysis.",
            "The QGIS project stores an XYZ OpenStreetMap basemap; tile loading requires internet when opened.",
            "Only Case1/Nanjing Road is fully packaged in this workspace.",
        ],
    }
    manifest_path = manifest_dir / "spatial_reasoning_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    readme = f"""# Hermes-Urban QGIS Workspace

Open this QGIS project:

`{project_qgz}`

Key layers:

- `Grid - building coverage`: 200m grid with building intensity.
- `Grid - heritage proxy score`: OSM heritage/start_date/old_name/tourism proxy.
- `Grid - road density`: road length per hectare inside each grid cell.
- `Road accessibility score`: road-network closeness/accessibility proxy.
- `Road network nodes`: graph nodes used by the accessibility proxy.

Agent-readable manifest:

`{manifest_path}`

The workspace is designed so a human can inspect the map in QGIS and Hermes-Urban
agents can read the same layer paths and metrics for follow-up spatial reasoning.
"""
    (workspace / "README.md").write_text(readme, encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--qgis-python", type=Path, default=DEFAULT_QGIS_PYTHON)
    args = parser.parse_args()
    manifest = build_workspace(args.run_dir.resolve(), args.qgis_python)
    print(json.dumps({
        "workspace": manifest["workspace"],
        "project_qgz": manifest["project_qgz"],
        "project_qgs": manifest["project_qgs"],
        "qgis_result": manifest["qgis_result"],
        "layer_count": len(manifest["layers"]),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
