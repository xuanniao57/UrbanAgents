"""Top-level public API for the UrbanAgent package."""

import logging

logging.getLogger("numexpr").setLevel(logging.WARNING)

from .task_agent import AgentState, UrbanTaskAgent
from .config import AgentConfig
from .core import CorrectionModuleRegistry, CorrectionModuleSpec
from .capabilities import CapabilityRegistry, ToolBroker, get_default_capability_registry, get_default_tool_broker
from .version import __version__

_LAZY_AGENT_EXPORTS = {"MultiAgentOrchestrator", "QualityController", "RuntimeLedger"}


def __getattr__(name: str):
	if name in _LAZY_AGENT_EXPORTS:
		from .agents import MultiAgentOrchestrator, QualityController, RuntimeLedger

		value = {
			"MultiAgentOrchestrator": MultiAgentOrchestrator,
			"QualityController": QualityController,
			"RuntimeLedger": RuntimeLedger,
		}[name]
		globals()[name] = value
		return value
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

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
