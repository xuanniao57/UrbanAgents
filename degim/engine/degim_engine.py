from typing import List, Dict
from ..data.agent_simulator import AgentOutputSimulator
from ..layers.l1_cognitive import CognitiveLayer
from ..layers.l2_spatial import SpatialLayer
from ..layers.l3_imagery import ImageryLayer
from ..alignment.cross_layer import CrossLayerAlignment

class DeGIMEngine:
    def __init__(self):
        self.simulator = AgentOutputSimulator()
        self.l1 = CognitiveLayer()
        self.l2 = SpatialLayer()
        self.l3 = ImageryLayer()
        self.alignment = CrossLayerAlignment()

    def run(self, task: str, address: str = "Tianzifang, Shanghai") -> Dict:
        print(f"Starting DeGIM Engine for task: {task}")
        
        # Step 0: Simulate Heterogeneous Agents
        print("Step 0: Simulating 12 heterogeneous experts...")
        agent_outputs = self.simulator.generate(task, n_agents=12)
        
        # Step 1: Cognitive Layer (Shared Narrative + CD + Deliberation Log)
        print("Step 1: Processing Cognitive Layer with Text-Space Gen-Inspect Loop...")
        agent_inputs = [{"id": o.agent_id, "paradigm": o.paradigm, "narrative": o.narrative} for o in agent_outputs]
        shared_narrative, cd_score, deliberation_log, cog_critiques = self.l1.process(agent_inputs)
        
        # Step 2: Spatial Layer (Topological -> Vector)
        print("Step 2: Processing Spatial Layer with Multi-Space Hierarchical Loops...")
        keywords = [o.spatial_keywords for o in agent_outputs]
        svg_xml, spatial_metadata = self.l2.translate(shared_narrative, keywords, address=address)
        
        # Step 3: Imagery Layer (Mood Board + PD)
        print("Step 3: Processing Imagery Layer...")
        moods = [o.visual_mood for o in agent_outputs]
        mood_board, pd_score = self.l3.select(moods)
        
        # Step 4: Cross-Layer Alignment (CS + CLC)
        print("Step 4: Aligning layers...")
        cs_score = self.alignment.compute_cs(shared_narrative, spatial_metadata)
        clc_score = self.alignment.compute_clc(cd_score, cs_score, pd_score)
        
        result = {
            "task": task,
            "address": address,
            "deliberation_log": deliberation_log,
            "cognitive_critiques": cog_critiques,
            "shared_narrative": shared_narrative,
            "svg_xml": svg_xml,
            "spatial_metadata": spatial_metadata,
            "mood_board": mood_board,
            "metrics": {
                "CD": cd_score,
                "CS": cs_score,
                "PD": pd_score,
                "CLC": clc_score
            },
            "agents": [o.to_dict() for o in agent_outputs]
        }
        
        print("DeGIM Engine run completed.")
        return result
