"""OpenStreetMap-oriented spatial data processor.

The core processor knows how to fetch OSM data and how to read an optional
local shapefile tree when one is explicitly configured. Benchmark-specific
paths and city aliases are injected by adapters or memory, not hard-coded here.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import geopandas as gpd
import numpy as np
from shapely.geometry import LineString, Point, Polygon


class OSMProcessor:
    """Process OSM or explicitly configured local vector data."""

    def __init__(
        self,
        data_source: str = "auto",
        local_data_path: Optional[str] = None,
        city_aliases: Optional[Dict[str, str]] = None,
    ):
        self.data_source = data_source
        self.city_data_path = local_data_path or os.getenv("URBAN_AGENT_LOCAL_CITYDATA_PATH", "")
        self.city_aliases = city_aliases or {}

    def process(self, location: str, radius: int = 500) -> Dict[str, Any]:
        if self.data_source == "osm" or self._looks_like_specific_location(location):
            return self._process_from_osm(location, radius)

        if self.data_source in {"auto", "local"}:
            city_name = self._extract_city_name(location)
            local_data = self._load_local_data(city_name)
            if local_data is not None:
                return self._process_local_data(local_data)
            if self.data_source == "local":
                return self._empty_features()

        return self._process_from_osm(location, radius)

    @staticmethod
    def _looks_like_specific_location(location: str) -> bool:
        lowered = location.lower()
        return "nearby" in lowered or "," in location or "附近" in location

    def _extract_city_name(self, location: str) -> str:
        for alias, canonical in self.city_aliases.items():
            if alias in location or canonical.lower() in location.lower():
                return canonical
        return location.split(",")[0].strip()

    def _load_local_data(self, city_name: str) -> Optional[gpd.GeoDataFrame]:
        if not self.city_data_path:
            return None
        shapefile_path = Path(self.city_data_path) / city_name / f"{city_name}.shp"
        if not shapefile_path.exists():
            return None
        try:
            return gpd.read_file(shapefile_path)
        except Exception:
            return None

    def _process_local_data(self, gdf: gpd.GeoDataFrame) -> Dict[str, Any]:
        if gdf.empty:
            return self._empty_features()
        local_utm = gdf.estimate_utm_crs() or gdf.crs or "EPSG:4326"
        gdf = gdf.to_crs(local_utm)
        buildings = gdf[gdf.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
        roads = self._generate_roads_from_buildings(buildings)
        return {
            "roads": self._analyze_roads(roads),
            "buildings": self._analyze_buildings(buildings),
            "pois": {},
            "landuse": {},
            "spatial_patterns": {
                "grid_regularity": 0.5,
                "building_clustering": self._calculate_clustering(buildings),
            },
            "connectivity": {"average_degree": 2.5, "intersection_density": 0.1},
            "_gdf_roads": roads,
            "_gdf_buildings": buildings,
            "_gdf_landuse": None,
            "_graph": None,
            "_bbox": tuple(float(value) for value in gdf.total_bounds),
            "_crs": str(local_utm),
        }

    def _process_from_osm(self, location: str, radius: int) -> Dict[str, Any]:
        try:
            import osmnx as ox
        except Exception as error:
            return {**self._empty_features(), "error": f"osmnx unavailable: {error}"}

        try:
            road_graph = ox.graph_from_address(location, dist=radius, network_type="all", simplify=True)
        except Exception:
            road_graph = None

        try:
            buildings = ox.features_from_address(location, tags={"building": True}, dist=radius)
        except Exception:
            buildings = gpd.GeoDataFrame()

        if len(buildings) > 0:
            local_utm = buildings.estimate_utm_crs() or buildings.crs or "EPSG:4326"
            buildings = buildings.to_crs(local_utm)
            bounds = tuple(float(value) for value in buildings.total_bounds)
        else:
            local_utm = "EPSG:4326"
            bounds = (0.0, 0.0, 0.0, 0.0)

        if road_graph is not None:
            nodes, edges = ox.graph_to_gdfs(road_graph)
            edges = edges.to_crs(local_utm)
            connectivity = self._analyze_connectivity(road_graph)
        else:
            edges = gpd.GeoDataFrame(geometry=[], crs=local_utm)
            connectivity = {"average_degree": 0, "intersection_density": 0}

        return {
            "roads": self._analyze_roads(edges),
            "buildings": self._analyze_buildings(buildings),
            "pois": self._fetch_pois(location, radius),
            "landuse": {},
            "spatial_patterns": {
                "grid_regularity": self._calculate_grid_regularity(edges),
                "building_clustering": self._calculate_clustering(buildings),
            },
            "connectivity": connectivity,
            "_gdf_roads": edges,
            "_gdf_buildings": buildings,
            "_gdf_landuse": None,
            "_graph": road_graph,
            "_bbox": bounds,
            "_crs": str(local_utm),
        }

    def _fetch_pois(self, location: str, radius: int) -> Dict[str, Any]:
        try:
            import osmnx as ox

            pois = ox.features_from_address(
                location,
                tags={"amenity": True, "shop": True, "tourism": True, "leisure": True},
                dist=radius,
            )
        except Exception:
            return {}

        categorized: Dict[str, list[Dict[str, Any]]] = {}
        for _, poi in pois.iterrows():
            poi_type = poi.get("amenity") or poi.get("shop") or poi.get("tourism") or "other"
            geom = poi.geometry
            if isinstance(geom, Point):
                coords = (geom.x, geom.y)
            elif isinstance(geom, Polygon):
                coords = (geom.centroid.x, geom.centroid.y)
            else:
                continue
            categorized.setdefault(str(poi_type), []).append(
                {"name": poi.get("name", "Unknown"), "type": poi_type, "coordinates": coords}
            )
        return categorized

    def _generate_roads_from_buildings(self, buildings_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        if len(buildings_gdf) < 3:
            return gpd.GeoDataFrame(geometry=[], crs=buildings_gdf.crs)
        try:
            from scipy.spatial import Delaunay

            coords = np.array([(point.x, point.y) for point in buildings_gdf.centroid])
            tri = Delaunay(coords)
            lines = []
            for simplex in tri.simplices:
                for index in range(3):
                    line = LineString([coords[simplex[index]], coords[simplex[(index + 1) % 3]]])
                    if line.length < 500:
                        lines.append(line)
            return gpd.GeoDataFrame(geometry=lines, crs=buildings_gdf.crs)
        except Exception:
            return gpd.GeoDataFrame(geometry=[], crs=buildings_gdf.crs)

    @staticmethod
    def _analyze_roads(edges_gdf: gpd.GeoDataFrame) -> Dict[str, Any]:
        if len(edges_gdf) == 0:
            return {"total_length_m": 0, "segment_count": 0, "road_types": {}}
        road_types = {}
        if "highway" in edges_gdf.columns:
            for highway_type, group in edges_gdf.groupby("highway"):
                road_types[str(highway_type)] = {"count": len(group), "total_length": float(group.length.sum())}
        return {
            "total_length_m": float(edges_gdf.length.sum()),
            "segment_count": len(edges_gdf),
            "road_types": road_types,
            "avg_segment_length": float(edges_gdf.length.mean()),
        }

    @staticmethod
    def _analyze_buildings(buildings_gdf: gpd.GeoDataFrame) -> Dict[str, Any]:
        if len(buildings_gdf) == 0:
            return {"count": 0, "total_area_m2": 0, "density": 0}
        areas = buildings_gdf.area
        bounds = buildings_gdf.total_bounds
        site_area = (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])
        building_types = {}
        if "building" in buildings_gdf.columns:
            building_types = {str(key): int(value) for key, value in buildings_gdf["building"].value_counts().items()}
        return {
            "count": len(buildings_gdf),
            "total_area_m2": float(areas.sum()),
            "density": float(areas.sum() / site_area) if site_area > 0 else 0,
            "avg_area_m2": float(areas.mean()),
            "building_types": building_types,
        }

    @staticmethod
    def _analyze_connectivity(graph: Any) -> Dict[str, Any]:
        try:
            degrees = [degree for _, degree in graph.degree()]
            return {
                "average_degree": float(np.mean(degrees)) if degrees else 0,
                "intersection_density": len([node for node, degree in graph.degree() if degree > 2]) / len(graph.nodes()) if graph.nodes() else 0,
            }
        except Exception:
            return {"average_degree": 0, "intersection_density": 0}

    @staticmethod
    def _calculate_grid_regularity(edges_gdf: gpd.GeoDataFrame) -> float:
        return 0.5

    @staticmethod
    def _calculate_clustering(buildings: gpd.GeoDataFrame) -> float:
        if len(buildings) < 2:
            return 0.0
        try:
            from scipy.spatial.distance import pdist

            coords = np.array([(point.x, point.y) for point in buildings.centroid])
            avg_distance = np.mean(pdist(coords))
            bounds = buildings.total_bounds
            max_dist = np.sqrt((bounds[2] - bounds[0]) ** 2 + (bounds[3] - bounds[1]) ** 2)
            return float(1 - min(1, avg_distance / (max_dist * 0.1 + 1e-10)))
        except Exception:
            return 0.0

    @staticmethod
    def _empty_features() -> Dict[str, Any]:
        return {
            "roads": {"total_length_m": 0, "segment_count": 0, "road_types": {}},
            "buildings": {"count": 0, "total_area_m2": 0, "density": 0},
            "pois": {},
            "landuse": {},
            "spatial_patterns": {},
            "connectivity": {"average_degree": 0, "intersection_density": 0},
            "_bbox": (0.0, 0.0, 0.0, 0.0),
            "_crs": "EPSG:4326",
        }
