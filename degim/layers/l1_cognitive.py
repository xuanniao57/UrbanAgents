import json
from typing import List, Tuple
from ..utils.llm_utils import get_llm_response

class CognitiveLayer:
    def process(self, narratives: List[dict]) -> Tuple[str, float, List[dict], List[str]]:
        """
        DeGIM L1: Cognitive Deliberation Loop
        1. Synthesis: Group Proposes Shared Narrative.
        2. Inspection: Consensus Facilitator critiques for unresolved conflicts.
        3. Refinement: Final synthesis.
        """
        print("   [Cognitive Skill] Phase A: Initial Synthesis")
        shared_narrative, cd_score, deliberation_log = self._synthesize(narratives)
        
        print("   [Cognitive Skill] Phase B: Consensus Inspection")
        facilitator_critique = self._inspect_consensus(deliberation_log, cd_score)
        
        print("   [Cognitive Skill] Phase C: Refined Co-value Statement")
        final_narrative, final_cd, final_log = self._refine_synthesis(narratives, facilitator_critique)
        
        return final_narrative, final_cd, final_log, [facilitator_critique]

    def _synthesize(self, narratives_data: List[dict]) -> Tuple[str, float, List[dict]]:
        prompt = f"""
        [Role] You are the Deliberation Engine for DeGIM. 
        [Task] Synthesize design narratives from 12 experts into a Shared Narrative.
        [Experts' Inputs] {json.dumps(narratives_data, indent=2)}

        [Requirements]
        1. Identify key Debate Points where paradigms conflict.
        2. Propose Resolutions that move toward a Co-value.
        3. Draft a Shared Narrative.
        
        Return JSON with "deliberation_log", "shared_narrative", and "cd_score".
        """
        response = get_llm_response(prompt, system_prompt="Synthesize urban design consensus.")
        return self._parse_synthesis(response)

    def _inspect_consensus(self, log: List[dict], cd: float) -> str:
        prompt = f"""
        [Role] You are the Consensus Facilitator.
        [Input] CD Score: {cd}, Deliberation Log: {json.dumps(log, indent=2)}
        [Task] Critique the current consensus. Are there any superficial resolutions or ignored minority viewpoints?
        [Output] Provide a sharp critique (max 3 sentences) focusing on unresolved tensions.
        """
        return get_llm_response(prompt, system_prompt="Critique the quality of group consensus.")

    def _refine_synthesis(self, narratives_data: List[dict], critique: str) -> Tuple[str, float, List[dict]]:
        prompt = f"""
        [Role] Refine the Shared Narrative and Deliberation Log based on the Facilitator's critique.
        [Experts] {json.dumps(narratives_data, indent=2)}
        [Critique] {critique}
        
        [Requirement]
        Return a JSON object with:
        - "shared_narrative": string
        - "deliberation_log": list of {{"topic", "conflict", "resolution"}}
        - "cd_score": float (0.0 to 1.0)
        """
        response = get_llm_response(prompt, system_prompt="Finalize urban design co-value.")
        return self._parse_synthesis(response)

    def _parse_synthesis(self, response: str) -> Tuple[str, float, List[dict]]:
        if not response: return "Error", 0.0, []
        try:
            clean = response.strip().strip("```json").strip("```")
            data = json.loads(clean)
            
            # Robust key checking for CD
            cd = data.get("cd_score") or data.get("consensus_degree") or data.get("CD") or 0.0
            if isinstance(cd, str):
                try: cd = float(cd)
                except: cd = 0.5
                
            return (
                data.get("shared_narrative", ""), 
                float(cd), 
                data.get("deliberation_log", [])
            )
        except Exception as e:
            print(f"Parsing error in Cognitive Layer: {e}")
            return "Parsing Error", 0.0, []
