import json
from typing import List, Tuple
from ..utils.llm_utils import get_llm_response

class ImageryLayer:
    def select(self, visual_moods: List[str]) -> Tuple[List[str], float]:
        """
        Select a representative mood board and calculate Paradigm Diversity (PD).
        """
        prompt = f"""
        The following are visual mood descriptions from 12 heterogeneous design experts.
        Moods:
        {json.dumps(visual_moods, indent=2)}

        Tasks:
        1. Select 4-6 most representative and diverse descriptions to form a 'Collective Mood Board'.
        2. Calculate 'Paradigm Diversity' (PD) as a float between 0.0 and 1.0, representing how much diverse perspective survived the selection.

        Output in JSON:
        {{
            "mood_board": ["mood1", "mood2", ...],
            "pd_score": 0.0
        }}
        """
        
        response = get_llm_response(prompt, system_prompt="You are a visual curation expert.")
        if response:
            try:
                clean_response = response.strip().strip("```json").strip("```")
                data = json.loads(clean_response)
                return data.get("mood_board", []), data.get("pd_score", 0.0)
            except Exception as e:
                print(f"Error parsing imagery layer response: {e}")
        
        return [], 0.0
