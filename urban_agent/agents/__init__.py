"""
Multi-Agent Architecture for UrbanAgent  [EXPERIMENTAL]
多智能体架构 — 参考 GeoAgent (三层) + AutoBEE (信息隔离)

⚠️ Status: EXPERIMENTAL — 框架结构与论文对齐，但尚未经过完整端到端验证。
   Worker 内部复用 core/ 模块实现，编排逻辑需要在真实任务上进一步测试。

Architecture:
  Planning Layer  → PlannerAgent: 任务解析 + 子任务拆分
  Execution Layer → ManagerAgent + 4 Worker Agents (Perception, Analyst, Cartographer, Reporter)
  Review Layer    → SpatialReviewerAgent + HumanCheckpointAgent
"""

from .base import BaseAgent, AgentMessage, AgentRole
from .planner import PlannerAgent
from .manager import ManagerAgent
from .workers import PerceptionWorker, AnalystWorker, CartographerWorker, ReporterWorker
from .reviewers import SpatialReviewerAgent, HumanCheckpointAgent
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
