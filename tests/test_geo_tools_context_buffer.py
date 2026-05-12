import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from urban_agent.tools import geo_tools


pytestmark = pytest.mark.skipif(not geo_tools.HAS_GEOPANDAS, reason="geopandas is required for GIS bundle tests")


def test_gis_bundle_exports_context_buffer_and_metric_result_layer(tmp_path):
    gpd = geo_tools.gpd
    boundary_path = tmp_path / "boundary.geojson"
    roads_path = tmp_path / "roads.geojson"
    buildings_path = tmp_path / "buildings.geojson"
    poi_dir = tmp_path / "sinobf"
    poi_dir.mkdir()
    poi_path = poi_dir / "sinobf_building_poi.geojson"

    boundary = gpd.GeoDataFrame({"id": [1]}, geometry=[geo_tools.box(121.470, 31.230, 121.480, 31.235)], crs="EPSG:4326")
    roads = gpd.GeoDataFrame({"id": [1]}, geometry=[geo_tools.LineString([(121.460, 31.232), (121.490, 31.232)])], crs="EPSG:4326")
    buildings = gpd.GeoDataFrame(
        {"id": [1, 2]},
        geometry=[
            geo_tools.box(121.472, 31.231, 121.473, 31.232),
            geo_tools.box(121.486, 31.232, 121.487, 31.233),
        ],
        crs="EPSG:4326",
    )
    pois = gpd.GeoDataFrame({"id": [1]}, geometry=[geo_tools.Point(121.486, 31.232)], crs="EPSG:4326")

    boundary.to_file(boundary_path, driver="GeoJSON")
    roads.to_file(roads_path, driver="GeoJSON")
    buildings.to_file(buildings_path, driver="GeoJSON")
    pois.to_file(poi_path, driver="GeoJSON")

    result = geo_tools.build_gis_artifact_bundle({
        "resources": [
            {"path": str(boundary_path)},
            {"path": str(roads_path)},
            {"path": str(buildings_path)},
            {"path": str(poi_path)},
        ],
        "artifact_dir": str(tmp_path / "artifacts"),
        "metric_rows": [
            {"group": "built_form", "metric": "building_coverage_ratio", "value": 0.42, "unit": "ratio", "method": "test"},
        ],
    })

    assert result["status"] == "visualization_complete"
    assert "context_buffer" in result["layer_stack"]
    assert "context_roads" in result["layer_stack"]
    assert "context_buildings" in result["layer_stack"]
    assert "aoi_metric_summary" in result["layer_stack"]
    assert "metric_result_layers" in result["outputs"]

    context_buffer = result["alignment_diagnostics"]["context_buffer"]
    assert context_buffer["status"] == "generated"
    assert context_buffer["width_factor"] == 3.0
    assert context_buffer["height_factor"] == 3.0
    assert context_buffer["area_ratio_to_aoi_bbox"] == 9.0
    assert context_buffer["centered_on_aoi"] is True

    metric_spatialization = result["alignment_diagnostics"]["metric_spatialization"]
    assert metric_spatialization["status"] == "spatialized"
    assert metric_spatialization["layer"] == "aoi_metric_summary"

def test_source_extent_metadata_takes_precedence_over_feature_bounds(tmp_path):
    from urban_agent.tools.geo_small_tools import validate_source_extent_against_context

    gpd = geo_tools.gpd
    boundary_path = tmp_path / "boundary.geojson"
    buildings_path = tmp_path / "buildings.geojson"
    source_extent_path = tmp_path / "source_extent.geojson"

    boundary = gpd.GeoDataFrame({"id": [1]}, geometry=[geo_tools.box(121.470, 31.230, 121.480, 31.235)], crs="EPSG:4326")
    buildings = gpd.GeoDataFrame(
        {"id": [1]},
        geometry=[geo_tools.box(121.474, 31.232, 121.475, 31.233)],
        crs="EPSG:4326",
    )
    source_extent = gpd.GeoDataFrame(
        {"id": [1]},
        geometry=[geo_tools.box(121.460, 31.225, 121.490, 31.240)],
        crs="EPSG:4326",
    )

    boundary.to_file(boundary_path, driver="GeoJSON")
    buildings.to_file(buildings_path, driver="GeoJSON")
    source_extent.to_file(source_extent_path, driver="GeoJSON")

    result = validate_source_extent_against_context({
        "paths": {
            "boundary": str(boundary_path),
            "buildings": str(buildings_path),
            "source_extent": str(source_extent_path),
        }
    })

    layer = result["alignment_diagnostics"]["layers"]["buildings"]
    assert layer["source_extent_basis"] == "source_acquisition_extent"
    assert layer["source_to_context_width_ratio"] >= 0.9
    assert layer["source_to_context_height_ratio"] >= 0.9
    assert layer["feature_to_context_width_ratio"] < 0.6
