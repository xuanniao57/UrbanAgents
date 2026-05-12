"""Top-level public API for the UrbanAgent package."""

import logging

logging.getLogger("numexpr").setLevel(logging.WARNING)

from .legacy_agent import SpatialContext, UrbanAgent
from .task_agent import AgentState, UrbanTaskAgent
from .config import AgentConfig
from .perception import OSMProcessor
from .cognition import SpatialCognition
from .decision import SpatialDecision
from .core import CorrectionModuleRegistry, CorrectionModuleSpec
from .capabilities import CapabilityRegistry, ToolBroker, get_default_capability_registry, get_default_tool_broker
from .version import __version__

# Multi-agent architecture
from .agents import MultiAgentOrchestrator, QualityController, RuntimeLedger

AsyncUrbanAgent = UrbanTaskAgent
LegacyUrbanAgent = UrbanAgent

__all__ = [
	"__version__",
	"AgentConfig",
	"AgentState",
	"AsyncUrbanAgent",
	"CapabilityRegistry",
	"CorrectionModuleRegistry",
	"CorrectionModuleSpec",
	"LegacyUrbanAgent",
	"MultiAgentOrchestrator",
	"OSMProcessor",
	"QualityController",
	"RuntimeLedger",
	"SpatialCognition",
	"SpatialContext",
	"SpatialDecision",
	"ToolBroker",
	"UrbanAgent",
	"UrbanTaskAgent",
	"get_default_capability_registry",
	"get_default_tool_broker",
]
