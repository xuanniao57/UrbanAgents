from typing import List, Tuple, Dict
from ..utils.llm_utils import get_llm_response
from ..utils.spatial_tools import SpatialTools
import json

class SpatialLayer:
    def __init__(self):
        self.tools = SpatialTools()

    def translate(self, shared_narrative: str, spatial_keywords: List[List[str]], address: str = "Tianzifang, Shanghai") -> Tuple[str, Dict]:
        """
        DeGIM Spatial Layer 2.2: Dual-Space Generation (Topological -> Vector)
        Each space has its own Gen-Inspect Loop.
        """
        print(f"   [Spatial Skill] Fetching OSM context for: {address}")
        site_info, roads, buildings = self.tools.get_site_context(address)
        
        if not site_info:
            return "<svg>Error loading site context</svg>", {}

        # --- Hierarchical Space 1: Topological Decision Space ---
        print("   [Spatial Skill] L2.1: Topological Layer (Abstract Logic)")
        topological_graph = self._topological_propose(shared_narrative, site_info)
        topo_critique = self._topological_inspect(topological_graph, shared_narrative)
        final_topology = self._topological_refine(topological_graph, topo_critique, shared_narrative)
        
        # --- Hierarchical Space 2: Vector Decision Space ---
        print("   [Spatial Skill] L2.2: Vector Layer (Metric Mapping)")
        vector_layout = self._vector_propose(final_topology, site_info, address)
        vector_critique = self._vector_inspect(vector_layout, site_info, roads)
        final_layout = self._vector_refine(vector_layout, vector_critique, site_info)
        
        # Final Render
        print("   [Spatial Skill] Phase D: Vector Rendering (SVG)")
        svg_xml = self.tools.generate_svg_layout(roads, buildings, final_layout)
        
        metadata = {
            "site_info": site_info,
            "topology": final_topology,
            "vector_layout": final_layout,
            "spatial_deliberation": {
                "topological_critique": topo_critique,
                "vector_critique": vector_critique
            }
        }
        
        return svg_xml, metadata

    # --- Topological Space Methods ---
    def _topological_propose(self, narrative: str, site_info: Dict) -> List[Dict]:
        prompt = f"""
        [Space] Topological Design Space (Relational Logic).
        [Task] Propose an abstract design graph (nodes and conceptual links) based on:
        Narrative: {narrative}
        Site Info: {json.dumps(site_info)}
        
        [Format] Return a JSON object with a "relations" key:
        {{
            "relations": [
                {{"type": "relation", "from": "Node A", "to": "Node B", "logic": "Connection/Buffer/Axis"}},
                ...
            ]
        }}
        Only focus on LOGIC, not coordinates.
        """
        response = get_llm_response(prompt, system_prompt="You are a topological urban designer.")
        return self._safe_parse_json(response, "relations")

    def _topological_inspect(self, graph: List[Dict], narrative: str) -> str:
        prompt = f"""
        [Role] Connectivity Inspector.
        [Input] Topological Graph: {json.dumps(graph)}
        [Task] Review the relational logic. Does it solve the narrative's spatial conflicts?
        """
        return get_llm_response(prompt, system_prompt="Review urban design topology logic.")

    def _topological_refine(self, graph: List[Dict], critique: str, narrative: str) -> List[Dict]:
        prompt = f"""
        [Role] Topological Designer. Refine the abstract design graph based on critique: {critique}
        Return a JSON object with a "relations" key.
        """
        response = get_llm_response(prompt, system_prompt="Refine urban topology.")
        return self._safe_parse_json(response, "relations")

    # --- Vector Space Methods ---
    def _vector_propose(self, topology: List[Dict], site_info: Dict, address: str) -> List[Dict]:
        prompt = f"""
        [Space] Vector Design Space (Metric Mapping).
        [Objective] Translate abstract design logic into precise SVG coordinates [0.0 - 1.0].
        
        [Context]
        Site: {address}
        Orientation: {site_info.get('site_orientation')}
        Building Cluster Density: {site_info.get('building_clusters')} nodes
        Bbox: {site_info.get('bbox')}
        
        [Topology to Map]
        {json.dumps(topology, indent=2)}
        
        [Design Rules]
        1. Axes must align with the site's orientation ({site_info.get('site_orientation')}).
        2. Nodes (Interventions) should be placed in areas where building density is likely lower (check centroid {site_info.get('center')}).
        3. Use professional labels (e.g., 'Eco-Social Spine', 'Heritage Buffer Zone').
        
        [Output Format]
        Return JSON list of design elements:
        - "type": "node", "label": "...", "rel_x": 0.3, "rel_y": 0.4
        - "type": "axis", "label": "...", "points": [[x1, y1], [x2, y2]]
        - "type": "zone", "label": "...", "points": [[x1, y1], [x2, y2], [x3, y3], ...]
        """
        response = get_llm_response(prompt, system_prompt="You are a GIS-proficient urban designer.")
        return self._safe_parse_json(response, "design_elements")

    def _vector_inspect(self, layout: List[Dict], site_info: Dict, roads: any) -> str:
        prompt = f"""
        [Role] Spatial Inspector Agent.
        [Task] Verify the design layout against the site's physical reality.
        
        [Proposal] {json.dumps(layout, indent=2)}
        [Site Context]
        Roads: {site_info.get('road_count')} segments
        Orientation: {site_info.get('site_orientation')}
        
        [Checklist]
        1. Metric Realism: Are axes too long? (Max 0.8 rel).
        2. Site Integration: Do the axes cut through massive building blocks or follow the grain?
        3. Label Precision: Are labels descriptive and professional?
        
        Return a critical evaluation (max 100 words).
        """
        return get_llm_response(prompt, system_prompt="Expert in precision urban planning.")

    def _vector_refine(self, layout: List[Dict], critique: str, site_info: Dict) -> List[Dict]:
        prompt = f"""
        [Role] Vector Designer. Refine the vector layout based on critique: {critique}
        
        [Requirement]
        Return a JSON object with a "design_elements" key containing a list of objects.
        Each object MUST have: "type" (node/axis/zone), "label", and either "rel_x"/"rel_y" or "points".
        """
        response = get_llm_response(prompt, system_prompt="Refine metric coordinates for SVG.")
        return self._safe_parse_json(response, "design_elements")

    def _safe_parse_json(self, response: str, key: str) -> List:
        if not response: return []
        try:
            clean = response.strip().strip("```json").strip("```")
            data = json.loads(clean)
            return data.get(key, data) if isinstance(data, dict) else data
        except:
            return []
