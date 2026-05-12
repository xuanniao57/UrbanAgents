"""
Street View Image Processor

Handles processing of street view images for urban analysis:
- Urban perception scoring (beautiful, safe, wealthy, lively, boring, depressing)
- Scene graph generation
- Geolocation from street view
"""

from typing import Dict, List, Optional
from pathlib import Path


class StreetViewProcessor:
    """Processor for street view images"""
    
    # Generic urban perception attributes
    PERCEPTION_ATTRIBUTES = [
        "beautiful", "safe", "wealthy", "lively", "boring", "depressing"
    ]
    
    def __init__(self, vlm_client=None):
        """
        Initialize street view processor
        
        Args:
            vlm_client: Vision-language model client
        """
        self.vlm_client = vlm_client
    
    def analyze_perception(self, image_path: str, attributes: Optional[List[str]] = None) -> Dict:
        """
        Analyze urban perception attributes from street view image
        
        Args:
            image_path: Path to street view image
            attributes: List of attributes to analyze (default: all)
        
        Returns:
            Dict with perception scores (1-10 scale) and reasoning
        """
        if attributes is None:
            attributes = self.PERCEPTION_ATTRIBUTES
        
        if not Path(image_path).exists():
            return {"error": f"Image not found: {image_path}"}
        
        prompt = f"""Analyze this street view image and rate the following urban perception attributes on a scale of 1-10:

{chr(10).join(f"- {attr.capitalize()}" for attr in attributes)}

For each attribute:
1. Provide a score from 1 (lowest) to 10 (highest)
2. Explain your reasoning based on visual elements in the image
3. Identify specific features that influenced your rating

Return your response in this format:
Attribute: Score
Reasoning: Explanation

Example:
Beautiful: 7
Reasoning: The street has mature trees, well-maintained buildings, and colorful storefronts..."""

        if self.vlm_client:
            result = self.vlm_client.analyze_image(image_path, prompt)
            
            # Parse scores from result
            scores = self._parse_perception_scores(result, attributes)
            
            return {
                "task": "perception_analysis",
                "image_path": image_path,
                "attributes": attributes,
                "scores": scores,
                "raw_analysis": result
            }
        else:
            return {
                "task": "perception_analysis",
                "image_path": image_path,
                "attributes": attributes,
                "scores": {},
                "status": "fallback",
                "message": "VLM client not available"
            }
    
    def generate_scene_graph(self, image_path: str) -> Dict:
        """
        Generate scene graph from street view image
        
        Scene graph represents:
        - Objects (buildings, vehicles, pedestrians, trees, etc.)
        - Relationships (next to, in front of, behind, etc.)
        - Attributes (color, size, type, etc.)
        
        Returns:
            Dict with scene graph structure
        """
        if not Path(image_path).exists():
            return {"error": f"Image not found: {image_path}"}
        
        prompt = """Analyze this street view image and generate a scene graph representation.

Identify:
1. Objects: List all distinct objects visible in the scene (buildings, vehicles, people, trees, signs, etc.)
2. Relationships: Describe spatial relationships between objects (e.g., "tree next to building", "car in front of store")
3. Attributes: Note key attributes of each object (color, size, type, condition)

Return the scene graph in a structured format:

Objects:
- Object ID: Name (attributes)

Relationships:
- Subject - Relationship - Object

Example:
Objects:
- obj1: Building (tall, brick, red)
- obj2: Tree (mature, green, leafy)
- obj3: Car (sedan, blue, parked)

Relationships:
- obj2 - next to - obj1
- obj3 - in front of - obj1"""

        if self.vlm_client:
            result = self.vlm_client.analyze_image(image_path, prompt)
            
            # Parse scene graph
            scene_graph = self._parse_scene_graph(result)
            
            return {
                "task": "scene_graph_generation",
                "image_path": image_path,
                "scene_graph": scene_graph,
                "raw_analysis": result
            }
        else:
            return {
                "task": "scene_graph_generation",
                "image_path": image_path,
                "scene_graph": {"objects": [], "relationships": []},
                "status": "fallback",
                "message": "VLM client not available"
            }
    
    def geolocate(self, image_path: str, candidate_cities: Optional[List[str]] = None) -> Dict:
        """
        Geolocate street view image to candidate cities
        
        Args:
            image_path: Path to street view image
            candidate_cities: List of candidate cities
        
        Returns:
            Dict with ranked city predictions
        """
        if candidate_cities is None:
            candidate_cities = [
                "Beijing", "London", "Paris", "Tokyo", "New York",
                "Moscow", "Mumbai", "Sao Paulo", "Sydney", "Nairobi",
                "Cape Town", "Shanghai"
            ]
        
        if not Path(image_path).exists():
            return {"error": f"Image not found: {image_path}"}
        
        prompt = f"""Analyze this street view image and identify which city it depicts.

Consider visual cues such as:
1. Architecture style and building materials
2. Street signs and traffic infrastructure
3. Vegetation and climate indicators
4. Vehicle types and license plates
5. Pedestrian clothing and demographics
6. Language on signs and storefronts
7. Overall urban atmosphere

Candidate cities: {', '.join(candidate_cities)}

Rank the top 3 most likely cities with confidence scores (0-100%) and detailed reasoning for each."""

        if self.vlm_client:
            result = self.vlm_client.analyze_image(image_path, prompt)
            
            # Parse city rankings
            rankings = self._parse_city_rankings(result)
            
            return {
                "task": "street_view_geolocation",
                "image_path": image_path,
                "candidate_cities": candidate_cities,
                "rankings": rankings,
                "raw_analysis": result
            }
        else:
            return {
                "task": "street_view_geolocation",
                "image_path": image_path,
                "candidate_cities": candidate_cities,
                "rankings": [],
                "status": "fallback",
                "message": "VLM client not available"
            }
    
    def _parse_perception_scores(self, analysis: str, attributes: List[str]) -> Dict[str, float]:
        """Parse perception scores from VLM output"""
        scores = {}
        
        # Simple parsing - look for patterns like "Beautiful: 7" or "beautiful: 7/10"
        for attr in attributes:
            import re
            # Match patterns like "Beautiful: 7" or "beautiful: 7/10" or "Beautiful - 7"
            patterns = [
                rf"{attr}[:\s]+(\d+(?:\.\d+)?)",
                rf"{attr.capitalize()}[:\s]+(\d+(?:\.\d+)?)",
            ]
            
            for pattern in patterns:
                match = re.search(pattern, analysis, re.IGNORECASE)
                if match:
                    score = float(match.group(1))
                    # Normalize to 1-10 scale if needed
                    if score <= 1:
                        score *= 10
                    scores[attr] = min(10, max(1, score))
                    break
            
            if attr not in scores:
                scores[attr] = 5.0  # Default neutral score
        
        return scores
    
    def _parse_scene_graph(self, analysis: str) -> Dict:
        """Parse scene graph from VLM output"""
        # Simple parsing - extract objects and relationships
        objects = []
