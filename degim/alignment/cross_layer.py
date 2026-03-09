import json
from ..utils.llm_utils import get_llm_response

class CrossLayerAlignment:
    def compute_cs(self, shared_narrative: str, svg_metadata: dict) -> float:
        """
        Compute Coherence Score (CS) between Shared Narrative and SVG Topology.
        """
        prompt = f"""
        Shared Narrative: {shared_narrative}
        SVG Topology Data: {json.dumps(svg_metadata, indent=2)}

        Task:
        Evaluate the coherence between the textual narrative and the spatial graph. 
        How well does the graph reflect the logic described in the narrative?
        Provide a coherence score (CS) between 0.0 and 1.0.

        Output in JSON: {{"cs_score": 0.0}}
        """
        
        response = get_llm_response(prompt, system_prompt="You are a design alignment validator.")
        if response:
            try:
                clean_response = response.strip().strip("```json").strip("```")
                data = json.loads(clean_response)
                return data.get("cs_score", 0.0)
            except Exception as e:
                print(f"Error parsing CS score: {e}")
        return 0.0

    def compute_clc(self, cd: float, cs: float, pd: float) -> float:
        """
        Compute Cross-Layer Consistency (CLC).
        Simple average for now.
        """
        return (cd + cs + pd) / 3.0
