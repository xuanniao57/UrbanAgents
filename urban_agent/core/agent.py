"""
Urban Agent Core
城市分析智能体核心控制器
"""

import json
import logging
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
import asyncio

from .perception import PerceptionModule
from .reasoning import ReasoningModule
from .memory import MemoryModule
from .action import ActionModule

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class AgentState:
    """智能体状态"""
    task_id: str
    task_type: str
    current_step: int = 0
    perception_data: Dict = field(default_factory=dict)
    reasoning_results: Dict = field(default_factory=dict)
    action_history: List = field(default_factory=list)
    memory_context: Dict = field(default_factory=dict)
    status: str = "initialized"  # initialized, perceiving, reasoning, acting, completed, error


class UrbanAgent:
    """
    城市分析智能体
    
    核心能力：
    1. 多源数据感知（遥感、街景、OSM、GeoJSON、轨迹）
    2. 空间推理（场景图、知识图谱、拓扑关系）
    3. 记忆管理（时空记忆、工作记忆、长期记忆）
    4. 行动执行（MCP工具调用、API交互）
    """
    
    def __init__(
        self,
        llm_client: Optional[Any] = None,
        vlm_client: Optional[Any] = None,
        mcp_client: Optional[Any] = None,
        config: Optional[Dict] = None
    ):
        self.llm_client = llm_client
        self.vlm_client = vlm_client
        self.mcp_client = mcp_client
        self.config = config or {}
        
        # 初始化模块
        self.perception = PerceptionModule(
            llm_client=llm_client,
            vlm_client=vlm_client,
            config=self.config.get("perception", {})
        )
        self.reasoning = ReasoningModule(
            llm_client=llm_client,
            config=self.config.get("reasoning", {})
        )
        self.memory = MemoryModule(
            config=self.config.get("memory", {})
        )
        self.action = ActionModule(
            mcp_client=mcp_client,
            llm_client=llm_client,
            config=self.config.get("action", {})
        )
        
        self.current_state: Optional[AgentState] = None
        self.task_history: List[AgentState] = []
        
    async def execute_task(
        self,
        task: Dict[str, Any],
        task_type: str,
        city_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        执行城市分析任务
        
        Args:
            task: 任务定义
            task_type: 任务类型 (population_prediction, object_detection, geolocation, 
                     geoqa, mobility_prediction, traffic_signal, outdoor_navigation, urban_exploration)
            city_data: 城市数据
            
        Returns:
            任务执行结果
        """
        task_payload = dict(task)
        task_payload["task_type"] = task_type
        task_id = f"{task_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 初始化状态
        self.current_state = AgentState(
            task_id=task_id,
            task_type=task_type
        )
        
        logger.info(f"开始执行任务: {task_id}")
        
        try:
            # Step 1: 感知 - 处理多源数据
            self.current_state.status = "perceiving"
            perception_result = await self._perceive(task_payload, city_data)
            self.current_state.perception_data = perception_result
            
            # Step 2: 记忆检索 - 获取相关上下文
            memory_context = await self._retrieve_memory(perception_result)
            self.current_state.memory_context = memory_context
            
            # Step 3: 推理 - 空间推理和决策
            self.current_state.status = "reasoning"
            reasoning_result = await self._reason(
                perception_result, 
                memory_context,
                task_payload
            )
            self.current_state.reasoning_results = reasoning_result
            
            # Step 4: 行动 - 执行决策或生成回答
            self.current_state.status = "acting"
            action_result = await self._act(reasoning_result, task_payload)
            
            # Step 5: 记忆更新
            await self._update_memory(
                perception_result,
                reasoning_result,
                action_result
            )
            
            self.current_state.status = "completed"
            self.task_history.append(self.current_state)
            
            return {
                "task_id": task_id,
                "task_type": task_type,
                "status": "success",
                "input_task": task_payload,
                "perception": perception_result,
                "reasoning": reasoning_result,
                "action": action_result,
                "final_answer": action_result.get("answer", ""),
                "confidence": action_result.get("confidence", 0.0)
            }
            
        except Exception as e:
            logger.error(f"任务执行失败: {e}")
            self.current_state.status = "error"
            return {
                "task_id": task_id,
                "task_type": task_type,
                "status": "error",
                "error": str(e)
            }
    
    async def _perceive(
        self,
        task: Dict,
        city_data: Optional[Dict]
    ) -> Dict[str, Any]:
        """感知阶段：处理多源数据"""
        return await self.perception.process(task, city_data)
    
    async def _retrieve_memory(
        self,
        perception_data: Dict
    ) -> Dict[str, Any]:
        """检索相关记忆"""
        return await self.memory.retrieve(perception_data)
    
    async def _reason(
        self,
        perception_data: Dict,
        memory_context: Dict,
        task: Dict
    ) -> Dict[str, Any]:
        """推理阶段：空间推理和决策"""
        return await self.reasoning.infer(
            perception_data,
            memory_context,
            task
        )
    
    async def _act(
        self,
        reasoning_result: Dict,
        task: Dict
    ) -> Dict[str, Any]:
        """行动阶段：执行决策"""
        return await self.action.execute(reasoning_result, task)
    
    async def _update_memory(
        self,
        perception: Dict,
        reasoning: Dict,
        action: Dict
    ):
        """更新记忆"""
        await self.memory.store({
            "perception": perception,
            "reasoning": reasoning,
            "action": action,
            "timestamp": datetime.now().isoformat()
        })
    
    def get_state(self) -> Optional[AgentState]:
        """获取当前状态"""
        return self.current_state
    
    def reset(self):
        """重置智能体状态"""
        self.current_state = None
        self.memory.clear_working_memory()
