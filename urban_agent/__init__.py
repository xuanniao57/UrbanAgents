"""Top-level public API for the UrbanAgent package."""

import logging

logging.getLogger("numexpr").setLevel(logging.WARNING)

from .task_agent import AgentState, UrbanTaskAgent
from .config import AgentConfig
from .core import CorrectionModuleRegistry, CorrectionModuleSpec
from .capabilities import CapabilityRegistry, ToolBroker, get_default_capability_registry, get_default_tool_broker
from .version import __version__

# Multi-agent architecture
from .agents import MultiAgentOrchestrator, QualityController, RuntimeLedger

UrbanAgent = UrbanTaskAgent
AsyncUrbanAgent = UrbanTaskAgent

__all__ = [
	"__version__",
	"AgentConfig",
	"AgentState",
	"AsyncUrbanAgent",
	"CapabilityRegistry",
	"CorrectionModuleRegistry",
	"CorrectionModuleSpec",
	"MultiAgentOrchestrator",
	"QualityController",
	"RuntimeLedger",
	"ToolBroker",
	"UrbanAgent",
	"UrbanTaskAgent",
	"get_default_capability_registry",
	"get_default_tool_broker",
]
