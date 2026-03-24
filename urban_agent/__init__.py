"""Top-level public API for the UrbanAgent package."""

from .legacy_agent import SpatialContext, UrbanAgent
from .task_agent import AgentState, UrbanTaskAgent
from .config import AgentConfig
from .perception import OSMProcessor
from .cognition import SpatialCognition
from .decision import SpatialDecision
from .version import __version__

# Multi-agent architecture (v0.3+)
from .agents import MultiAgentOrchestrator

AsyncUrbanAgent = UrbanTaskAgent
LegacyUrbanAgent = UrbanAgent

__all__ = [
	"__version__",
	"AgentConfig",
	"AgentState",
	"AsyncUrbanAgent",
	"LegacyUrbanAgent",
	"MultiAgentOrchestrator",
	"OSMProcessor",
	"SpatialCognition",
	"SpatialContext",
	"SpatialDecision",
	"UrbanAgent",
	"UrbanTaskAgent",
]
