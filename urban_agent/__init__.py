"""Top-level public API for the UrbanAgent package."""

from .legacy_agent import SpatialContext, UrbanAgent
from .task_agent import AgentState, UrbanTaskAgent
from .config import AgentConfig
from .perception import OSMProcessor
from .cognition import SpatialCognition
from .decision import SpatialDecision
from .core import CorrectionModuleRegistry, CorrectionModuleSpec
from .version import __version__

# Multi-agent architecture
from .agents import MultiAgentOrchestrator, QualityController

AsyncUrbanAgent = UrbanTaskAgent
LegacyUrbanAgent = UrbanAgent

__all__ = [
	"__version__",
	"AgentConfig",
	"AgentState",
	"AsyncUrbanAgent",
	"CorrectionModuleRegistry",
	"CorrectionModuleSpec",
	"LegacyUrbanAgent",
	"MultiAgentOrchestrator",
	"OSMProcessor",
	"QualityController",
	"SpatialCognition",
	"SpatialContext",
	"SpatialDecision",
	"UrbanAgent",
	"UrbanTaskAgent",
]
