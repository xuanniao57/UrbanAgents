"""
Memory Module
时空记忆管理模块
"""

import json
import logging
import re
from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import deque

logger = logging.getLogger(__name__)


def _json_dump_safe(value: Any) -> str:
    return json.dumps(value, default=str)


def _tokenize_text(value: Any) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", _json_dump_safe(value).lower()))


class MemoryModule:
    """
    记忆模块：管理时空记忆
    
    记忆层级：
    - 工作记忆（Working Memory）：当前任务上下文
    - 短期记忆（Short-term Memory）：近期任务历史
    - 长期记忆（Long-term Memory）：持久化知识
    
    记忆类型：
    - 空间记忆：地理位置、空间关系
    - 时间记忆：时序信息、历史数据
    - 语义记忆：城市知识、规则
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        
        # 记忆存储
        self.working_memory: Dict[str, Any] = {}
        self.short_term_memory: deque = deque(maxlen=self.config.get("short_term_size", 100))
        self.long_term_memory: Dict[str, Any] = {
            "spatial": {},
            "temporal": {},
            "semantic": {}
        }
        
        # 索引
        self.spatial_index: Dict[str, Any] = {}
        self.temporal_index: List[Dict] = []
        
    async def retrieve(self, query: Dict) -> Dict[str, Any]:
        """
        检索相关记忆
        
        Args:
            query: 查询条件
            
        Returns:
            相关记忆
        """
        context = {
            "working": self.working_memory,
            "relevant_short_term": [],
            "relevant_long_term": {}
        }
        
        # 从短期记忆中检索
        for memory in self.short_term_memory:
            if self._is_relevant(memory, query):
                context["relevant_short_term"].append(memory)
        
        # 从长期记忆中检索
        context["relevant_long_term"] = self._retrieve_from_long_term(query)
        
        return context
    
    async def store(self, experience: Dict):
        """
        存储经验到记忆
        
        Args:
            experience: 经验数据
        """
        # 添加到工作记忆
        self.working_memory = experience
        
        # 添加到短期记忆
        self.short_term_memory.append({
            **experience,
            "timestamp": datetime.now().isoformat()
        })
        
        # 更新长期记忆（选择性存储）
        await self._update_long_term(experience)
        
        logger.info("Experience stored in memory")
    
    def _is_relevant(self, memory: Dict, query: Dict) -> bool:
        """判断记忆是否与查询相关"""
        memory_tokens = _tokenize_text(memory)
        query_tokens = _tokenize_text(query)

        if not query_tokens:
            return False

        matches = len(memory_tokens & query_tokens)
        relevance_score = matches / len(query_tokens)

        return relevance_score > 0.3
    
    def _retrieve_from_long_term(self, query: Dict) -> Dict:
        """从长期记忆中检索"""
        results = {
            "spatial": [],
            "temporal": [],
            "semantic": []
        }
        
        # 空间检索
        if "location" in query:
            location = query["location"]
            for key, value in self.long_term_memory["spatial"].items():
                if location in key:
                    results["spatial"].append(value)
        
        # 时间检索
        if "time" in query:
            time_query = query["time"]
            for entry in self.temporal_index:
                if self._time_match(entry["time"], time_query):
                    results["temporal"].append(entry)
        
        # 语义检索
        query_type = query.get("type", "")
        if query_type in self.long_term_memory["semantic"]:
            results["semantic"] = self.long_term_memory["semantic"][query_type]
        
        return results
    
    async def _update_long_term(self, experience: Dict):
        """更新长期记忆"""
        # 提取空间信息
        perception = experience.get("perception", {})
        
        if "bounds" in perception:
            # 存储空间记忆
            bounds = perception["bounds"]
            location_key = f"{bounds.get('min_lon', 0)}_{bounds.get('min_lat', 0)}"
            self.long_term_memory["spatial"][location_key] = {
                "bounds": bounds,
                "experience": experience,
                "timestamp": datetime.now().isoformat()
            }
        
        # 更新时间索引
        self.temporal_index.append({
            "time": datetime.now(),
            "experience": experience
        })
        
        # 限制时间索引大小
        if len(self.temporal_index) > 1000:
            self.temporal_index = self.temporal_index[-1000:]
    
    def _time_match(self, time1, time2) -> bool:
        """判断时间是否匹配"""
        # 简化的时间匹配
        return True
    
    def clear_working_memory(self):
        """清空工作记忆"""
        self.working_memory = {}
        logger.info("Working memory cleared")
    
    def get_memory_stats(self) -> Dict:
        """获取记忆统计"""
        return {
            "working_memory_size": len(self.working_memory),
            "short_term_size": len(self.short_term_memory),
            "long_term_spatial": len(self.long_term_memory["spatial"]),
            "long_term_temporal": len(self.temporal_index),
            "long_term_semantic": len(self.long_term_memory["semantic"])
        }
