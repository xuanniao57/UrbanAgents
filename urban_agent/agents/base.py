"""
Base Agent Protocol — 所有 Agent 的统一接口

每个 Agent 遵循 GeoAgent 的统一结构：
  role_prompt + workflow + tools

信息隔离（AutoBEE）：
  AgentMessage 是 Agent 间唯一通信方式，
  Worker 不共享全局状态。
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


DEFAULT_LLM_PROMPT_CHAR_LIMIT = 90000


def _compact_text_for_llm(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    head_len = max(1, int(limit * 0.7))
    tail_len = max(1, int(limit * 0.2))
    omitted = len(text) - head_len - tail_len
    return text[:head_len] + f"\n\n[... {omitted} characters omitted for LLM input budget ...]\n\n" + text[-tail_len:]


def _compact_message_content(content: Any, limit: int) -> Any:
    if isinstance(content, str):
        return _compact_text_for_llm(content, limit)
    if isinstance(content, list):
        remaining = limit
        compacted = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                item = dict(part)
                item["text"] = _compact_text_for_llm(item["text"], max(1, remaining))
                remaining -= len(item["text"])
                compacted.append(item)
            else:
                compacted.append(part)
        return compacted
    return content


def _compact_messages_for_llm(messages: Any, limit: int) -> Any:
    if not isinstance(messages, list) or limit <= 0:
        return messages
    remaining = limit
    compacted = []
    for message in messages:
        if not isinstance(message, dict):
            compacted.append(message)
            continue
        item = dict(message)
        content = item.get("content")
        item["content"] = _compact_message_content(content, max(1, remaining))
        if isinstance(item["content"], str):
            remaining -= len(item["content"])
        compacted.append(item)
    return compacted


class AgentRole(Enum):
    """Agent 角色类型"""
    MAIN = "main"
    PLANNER = "planner"
    MANAGER = "manager"
    PERCEPTION = "perception"
    ANALYST = "analyst"
    CARTOGRAPHER = "cartographer"
    REPORTER = "reporter"
    SPATIAL_REVIEWER = "spatial_reviewer"
    HUMAN_CHECKPOINT = "human_checkpoint"
    QUALITY_CONTROLLER = "quality_controller"


@dataclass
class AgentMessage:
    """
    Agent 间通信消息 — 信息隔离的唯一通道

    设计要点 (AutoBEE):
    - Agent 间仅通过 AgentMessage 传递数据
    - 每条消息有明确的 sender/receiver，不广播
    - payload 只包含该 Agent 需要的上下文（信息隔离）
    """
    sender: AgentRole
    receiver: AgentRole
    msg_type: str  # "task_plan", "subtask", "result", "review", "feedback"
    payload: Dict[str, Any]
    trace_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SubTask:
    """子任务定义 — PlannerAgent 产出"""
    subtask_id: str
    objective: str
    assigned_role: AgentRole
    input_data: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)  # subtask_ids
    expected_output: str = ""
    status: str = "pending"  # pending, running, completed, failed, under_review
    result: Optional[Dict[str, Any]] = None
    review_feedback: Optional[str] = None
    revision_count: int = 0
    max_revisions: int = 1  # GeoAgent: 最多1次修正


@dataclass
class ExecutionPlan:
    """执行计划 — PlannerAgent 输出给 ManagerAgent"""
    plan_id: str
    original_task: Dict[str, Any]
    complexity: str  # "basic", "intermediate", "advanced"
    workflow_profile: str
    subtasks: List[SubTask] = field(default_factory=list)
    execution_order: List[str] = field(default_factory=list)  # ordered subtask_ids


class BaseAgent(ABC):
    """
    Agent 基类

    所有 Agent 统一实现：
    1. role_prompt: 角色提示词，定义 Agent 身份与行为
    2. workflow: 执行工作流
    3. tools: 可使用的工具集
    """

    def __init__(
        self,
        role: AgentRole,
        llm_client: Optional[Any] = None,
        tools: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.role = role
        self.llm_client = llm_client
        self.tools = tools or {}
        self.config = config or {}
        self._message_log: List[AgentMessage] = []
        self.system_prompt: Optional[str] = None
        self.tool_surface: List[str] = []

    @property
    @abstractmethod
    def role_prompt(self) -> str:
        """角色提示词"""
        ...

    @abstractmethod
    async def execute(self, message: AgentMessage) -> AgentMessage:
        """
        执行入口 — 接收消息、处理、返回结果消息

        Args:
            message: 输入消息（来自上游 Agent 或 Manager）
        Returns:
            输出消息（发往下游 Agent 或 Manager）
        """
        ...

    def log_message(self, msg: AgentMessage):
        """记录通信日志"""
        self._message_log.append(msg)
        logger.info(
            f"[{msg.sender.value}→{msg.receiver.value}] "
            f"{msg.msg_type}: {list(msg.payload.keys())}"
        )

    async def call_llm(self, prompt: Any, **kwargs) -> str:
        """调用 LLM 的统一接口"""
        if self.llm_client is None:
            raise RuntimeError(f"{self.role.value} agent: llm_client not configured")
        prompt_limit = int(os.getenv("URBAN_AGENT_LLM_PROMPT_CHAR_LIMIT", self.config.get("llm_prompt_char_limit", DEFAULT_LLM_PROMPT_CHAR_LIMIT)))
        # 适配不同 LLM 客户端
        if hasattr(self.llm_client, "chat"):
            messages = prompt
            if isinstance(prompt, str):
                messages = []
                if self.system_prompt:
                    messages.append({"role": "system", "content": self.system_prompt})
                messages.append({"role": "user", "content": prompt})
            messages = _compact_messages_for_llm(messages, prompt_limit)
            return await self.llm_client.chat(messages, **kwargs)
        if hasattr(self.llm_client, "generate"):
            if isinstance(prompt, str):
                prompt = _compact_text_for_llm(prompt, prompt_limit)
            return await self.llm_client.generate(prompt, **kwargs)
        raise RuntimeError(f"Unsupported LLM client type: {type(self.llm_client)}")

    def set_prompt_context(self, system_prompt: str, tool_surface: Optional[List[str]] = None) -> None:
        self.system_prompt = system_prompt
        self.tool_surface = list(tool_surface or [])

    def stable_role_prompt(self) -> str:
        return self.system_prompt or self.role_prompt

    async def call_tool(self, tool_name: str, **kwargs) -> Any:
        """调用工具的统一接口"""
        if tool_name not in self.tools:
            raise ValueError(
                f"{self.role.value} agent: tool '{tool_name}' not available. "
                f"Available: {list(self.tools.keys())}"
            )
        handler = self.tools[tool_name]
        if callable(handler):
            return await handler(**kwargs) if asyncio.iscoroutinefunction(handler) else handler(**kwargs)
        raise TypeError(f"Tool '{tool_name}' is not callable")


import asyncio  # noqa: E402 — needed for iscoroutinefunction above
