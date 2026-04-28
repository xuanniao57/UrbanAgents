"""
Multi-Agent Architecture for UrbanAgent
多智能体架构 — 参考 GeoAgent (三层) + AutoBEE (信息隔离) + RMDA (质量控制)

Architecture:
  Planning Layer  → PlannerAgent: 任务解析 + 子任务拆分
  Execution Layer → ManagerAgent + 4 Worker Agents (Perception, Analyst, Cartographer, Reporter)
  Review Layer    → SpatialReviewerAgent + HumanCheckpointAgent
  Quality Control → QualityController: 跨层置信度评估 + 可靠性保障
"""

from .base import BaseAgent, AgentMessage, AgentRole
from .planner import PlannerAgent
from .manager import ManagerAgent
from .workers import PerceptionWorker, AnalystWorker, CartographerWorker, ReporterWorker
from .reviewers import SpatialReviewerAgent, HumanCheckpointAgent
from .quality_controller import QualityController, QualityReport
from .orchestrator import MultiAgentOrchestrator

__all__ = [
    "BaseAgent",
    "AgentMessage",
    "AgentRole",
    "PlannerAgent",
    "ManagerAgent",
    "PerceptionWorker",
    "AnalystWorker",
    "CartographerWorker",
    "ReporterWorker",
    "SpatialReviewerAgent",
    "HumanCheckpointAgent",
    "MultiAgentOrchestrator",
]
