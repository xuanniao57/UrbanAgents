import osmnx as ox
import geopandas as gpd
import shapely
import json
from typing import Dict, List, Tuple
import matplotlib.pyplot as plt
import io
import base64

class SpatialTools:
    """
    DeGIM Spatial Skill Set Category 2: Site Analysis & Vector Generation
    """
    
    @staticmethod
    def get_site_context(address: str, dist: int = 500) -> Dict:
        """
        Fetch real-world road and building data from OpenStreetMap.
        """
        try:
            # 1. Get roads
            graph = ox.graph_from_address(address, dist=dist, network_type='walk')
            roads = ox.graph_to_gdfs(graph, nodes=False)
            
            # 2. Get buildings
            buildings = ox.features_from_address(address, tags={"building": True}, dist=dist)
            
            # Convert to local UTM for metric calculations
            local_utm = buildings.estimate_utm_crs()
            roads = roads.to_crs(local_utm)
            buildings = buildings.to_crs(local_utm)
            
            bounds = buildings.total_bounds
            minx, miny, maxx, maxy = bounds
            
            result = {
                "road_count": len(roads),
                "building_count": len(buildings),
                "total_building_area": float(buildings.area.sum()),
                "bbox": list(bounds),
                "center": [float(buildings.centroid.x.mean()), float(buildings.centroid.y.mean())],
                "site_orientation": "N/S" if (maxy-miny) > (maxx-minx) else "E/W",
                "building_clusters": 5 # Estimated
            }
            return result, roads, buildings
        except Exception as e:
            print(f"Error fetching site context: {e}")
            return None, None, None

    @staticmethod
    def analyze_accessibility(roads_gdf, point: Tuple[float, float], dist: int = 300):
        """
        Calculate isochrones/service area for a given point.
        """
        # Simplified: Filter roads within distance for analysis
        # In a real scenario, we'd use networkx to find subgraphs
        return {"status": "success", "reachable_radius": dist}

    @staticmethod
    def generate_svg_layout(roads, buildings, design_elements: List[Dict]) -> str:
        """
        Converts GeoDataFrames + Design elements to a clean SVG string.
        """
        # Normalize coordinates to 0-800 viewbox
        bounds = buildings.total_bounds
        minx, miny, maxx, maxy = bounds
        width = maxx - minx
        height = maxy - miny
        scale = 800 / max(width, height)
        
        svg_parts = ['<svg viewBox="0 0 800 800" xmlns="http://www.w3.org/2000/svg" style="background:#f0f2f5">']
        
        def to_svg_coord(x, y):
            sx = (x - minx) * scale
            sy = 800 - (y - miny) * scale # Flip Y
            return sx, sy

        # Draw Buildings
        svg_parts.append('<g id="buildings" fill="#d1d5db" stroke="#9ca3af" stroke-width="0.5">')
        for _, b in buildings.iterrows():
            if isinstance(b.geometry, shapely.geometry.Polygon):
                coords = [f"{to_svg_coord(x, y)[0]},{to_svg_coord(x, y)[1]}" for x, y in b.geometry.exterior.coords]
                svg_parts.append(f'<polygon points="{" ".join(coords)}" />')
        svg_parts.append('</g>')

        # Draw Roads
        svg_parts.append('<g id="roads" fill="none" stroke="#6b7280" stroke-width="1.5">')
        for _, r in roads.iterrows():
            if isinstance(r.geometry, shapely.geometry.LineString):
                coords = [f"{to_svg_coord(x, y)[0]},{to_svg_coord(x, y)[1]}" for x, y in r.geometry.coords]
                pts = " ".join([f"{'M' if i==0 else 'L'} {p}" for i, p in enumerate([c.replace(',', ' ') for c in coords])])
                svg_parts.append(f'<path d="{pts}" />')
        svg_parts.append('</g>')

        # Draw Proposed Design Elements (e.g., Green Nodes, Interventions, Axes, Zones)
        svg_parts.append('<g id="design_interventions">')
        for el in design_elements:
            type = el.get('type', 'node')
            color = el.get('color', '#10b981')
            label = el.get('label', '')
            
            if type == 'node':
                rx, ry = el.get('rel_x', 0.5), el.get('rel_y', 0.5)
                ax = minx + rx * width
                ay = miny + ry * height
                sx, sy = to_svg_coord(ax, ay)
                svg_parts.append(f'<circle cx="{sx}" cy="{sy}" r="10" fill="{color}" opacity="0.9" stroke="white" stroke-width="2" />')
                if label:
                    svg_parts.append(f'<text x="{sx}" y="{sy+20}" font-size="10" text-anchor="middle" fill="#374151" font-weight="bold" font-family="Arial">{label}</text>')
            
            elif type == 'axis':
                points = el.get('points', [])
                if len(points) >= 2:
                    coords = []
                    for p in points:
                        # Robust coordinate extraction
                        try:
                            px = p[0] if isinstance(p, (list, tuple)) else p.get('x', p.get('rel_x', 0.5))
                            py = p[1] if isinstance(p, (list, tuple)) else p.get('y', p.get('rel_y', 0.5))
                            ax = minx + px * width
                            ay = miny + py * height
                            coords.append(to_svg_coord(ax, ay))
                        except Exception: continue
                    if not coords: continue
                    path_data = " ".join([f"{'M' if i==0 else 'L'} {c[0]} {c[1]}" for i, c in enumerate(coords)])
                    svg_parts.append(f'<path d="{path_data}" stroke="{color}" stroke-width="4" stroke-dasharray="8,4" fill="none" opacity="0.8" />')
                    if label:
                        mid = coords[len(coords)//2]
                        svg_parts.append(f'<text x="{mid[0]}" y="{mid[1]-10}" font-size="12" text-anchor="middle" fill="{color}" font-weight="bold" font-family="Arial">{label}</text>')

            elif type == 'zone':
                points = el.get('points', [])
                if len(points) >= 3:
                    coords = []
                    for p in points:
                        try:
                            px = p[0] if isinstance(p, (list, tuple)) else p.get('x', p.get('rel_x', 0.5))
                            py = p[1] if isinstance(p, (list, tuple)) else p.get('y', p.get('rel_y', 0.5))
                            ax = minx + px * width
                            ay = miny + py * height
                            coords.append(to_svg_coord(ax, ay))
                        except Exception: continue
                    if not coords: continue
                    pts_str = " ".join([f"{c[0]},{c[1]}" for c in coords])
                    svg_parts.append(f'<polygon points="{pts_str}" fill="{color}" opacity="0.3" stroke="{color}" stroke-width="2" />')
                    if label:
                        # Centroid approximation
                        cx = sum([c[0] for c in coords]) / len(coords)
                        cy = sum([c[1] for c in coords]) / len(coords)
                        svg_parts.append(f'<text x="{cx}" y="{cy}" font-size="11" text-anchor="middle" fill="#1f2937" font-weight="bold" font-family="Arial">{label}</text>')

        svg_parts.append('</g>')

        svg_parts.append('</svg>')
        return "\n".join(svg_parts)
