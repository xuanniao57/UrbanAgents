"""
Configuration for Urban Analysis Agent
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import os

from .version import __version__


@dataclass
class MemoryConfig:
    """Memory module configuration"""
    short_term_max_items: int = 100
    vector_store: str = "chroma"
    embedding_model: str = "text-embedding-3-small"
    spatial_index_type: str = "rtree"


@dataclass
class LLMConfig:
    """LLM configuration"""
    provider: str = "openai"
    model: str = "gpt-4"
    api_key: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 2000
    base_url: Optional[str] = None
    
    def __post_init__(self):
        if self.api_key is None:
            self.api_key = os.getenv("OPENAI_API_KEY")


@dataclass
class VLMConfig:
    """VLM configuration"""
    provider: str = "openai"
    model: str = "gpt-4-vision-preview"
    api_key: Optional[str] = None
    
    def __post_init__(self):
        if self.api_key is None:
            self.api_key = os.getenv("OPENAI_API_KEY")


@dataclass
class MCPConfig:
    """MCP server configuration"""
    servers: List[Dict] = field(default_factory=list)


@dataclass
class DataConfig:
    """Data paths configuration"""
    citybench_path: str = "./third_party/CityBench-main"
    remote_sensing_path: str = "./data/remote_sensing"
    street_view_path: str = "./data/street_view"
    osm_path: str = "./data/osm"
    trajectory_path: str = "./data/trajectory"
    knowledge_graph_path: str = "./data/knowledge_graph.ttl"


@dataclass
class AgentConfig:
    """Main agent configuration"""
    name: str = "UrbanAnalysisAgent"
    version: str = __version__
    
    # Sub-configs
    llm: LLMConfig = field(default_factory=LLMConfig)
    vlm: VLMConfig = field(default_factory=VLMConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    data: DataConfig = field(default_factory=DataConfig)
    
    # Evaluation
    evaluation_metrics: List[str] = field(default_factory=lambda: [
        "state_perception",
        "decision_sequence", 
        "task_outcome"
    ])
    
    # Features
    enable_memory: bool = True
    enable_mcp: bool = True
    enable_evaluation: bool = True
