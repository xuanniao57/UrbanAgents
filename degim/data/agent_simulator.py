import json
from typing import List, Dict
from ..utils.llm_utils import get_llm_response

class AgentOutput:
    def __init__(self, agent_id: int, paradigm: str, narrative: str, spatial_keywords: List[str], visual_mood: str):
        self.agent_id = agent_id
        self.paradigm = paradigm
        self.narrative = narrative
        self.spatial_keywords = spatial_keywords
        self.visual_mood = visual_mood

    def to_dict(self):
        return {
            "id": self.agent_id,
            "paradigm": self.paradigm,
            "narrative": self.narrative,
            "spatial_keywords": self.spatial_keywords,
            "visual_mood": self.visual_mood
        }

class AgentOutputSimulator:
    PARADIGMS = [
        "Phenomenology (Focus on human experience and perception)",
        "Typology (Focus on urban forms and architectural types)",
        "Parametricism (Focus on algorithmic and computational geometry)",
        "Ecological Urbanism (Focus on natural systems and sustainability)",
        "Social Justice (Focus on equity and community engagement)",
        "Metabolism (Focus on organic growth and modular systems)",
        "New Urbanism (Focus on walkability and traditional patterns)",
        "High-Tech Architecture (Focus on industrial technology and structure)",
        "Critical Regionalism (Focus on local context and climate)",
        "Post-Structuralism (Focus on complexity and fragmented narratives)",
        "Smart City (Focus on digital infrastructure and data)",
        "Landscape Urbanism (Focus on horizontal surfaces and systems)"
    ]

    def generate(self, task: str, n_agents: int = 12) -> List[AgentOutput]:
        outputs = []
        for i in range(min(n_agents, len(self.PARADIGMS))):
            paradigm = self.PARADIGMS[i]
            prompt = f"""
            Design Task: {task}
            You are a design expert with the following paradigm: {paradigm}.
            
            Provide your response in JSON format with the following keys:
            - narrative: A short design narrative (2-3 sentences).
            - spatial_keywords: A list of 5 keywords describing spatial constraints/elements.
            - visual_mood: A description of the visual atmosphere.
            """
            
            response = get_llm_response(prompt, system_prompt="You are a professional urban design expert.")
            if response:
                try:
                    # Strip markdown if any
                    clean_response = response.strip().strip("```json").strip("```")
                    data = json.loads(clean_response)
                    outputs.append(AgentOutput(
                        agent_id=i+1,
                        paradigm=paradigm,
                        narrative=data.get("narrative", ""),
                        spatial_keywords=data.get("spatial_keywords", []),
                        visual_mood=data.get("visual_mood", "")
                    ))
                except Exception as e:
                    print(f"Error parsing agent response: {e}, Response: {response}")
        return outputs
