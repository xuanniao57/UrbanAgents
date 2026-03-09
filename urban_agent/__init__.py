"""Top-level public API for the UrbanAgent package."""

from .legacy_agent import SpatialContext, UrbanAgent
from .task_agent import AgentState, UrbanTaskAgent
from .config import AgentConfig
from .perception import OSMProcessor
from .cognition import SpatialCognition
from .decision import SpatialDecision
from .version import __version__

AsyncUrbanAgent = UrbanTaskAgent
LegacyUrbanAgent = UrbanAgent

__all__ = [
	"__version__",
	"AgentConfig",
	"AgentState",
	"AsyncUrbanAgent",
	"LegacyUrbanAgent",
	"OSMProcessor",
	"SpatialCognition",
	"SpatialContext",
	"SpatialDecision",
	"UrbanAgent",
	"UrbanTaskAgent",
]
