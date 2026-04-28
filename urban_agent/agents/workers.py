"""
Worker Agents — Execution Layer Specialists
参考 GeoAgent 的三个专家 Agent (Analyst, Cartographer, Reporter)
加上 UrbanAgent 特有的 PerceptionWorker

每个 Worker：
- 只看到自己子任务的上下文（信息隔离）
- 复用现有 core 模块的实现
- 通过 AgentMessage 与 Manager 通信
"""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, Dict, Optional

from ..governance import (
    EvidenceManifest,
    GovernanceEvidence,
    PopulationEvidence,
    SpatialEvidence,
    TemporalEvidence,
)
from .base import AgentMessage, AgentRole, BaseAgent

logger = logging.getLogger(__name__)


class PerceptionWorker(BaseAgent):
    """
    感知 Worker — 多源数据获取与处理

    复用 urban_agent.core.perception.PerceptionModule
    """

    def __init__(
        self,
        perception_module: Optional[Any] = None,
        llm_client: Optional[Any] = None,
        **kwargs,
    ):
        super().__init__(role=AgentRole.PERCEPTION, llm_client=llm_client, **kwargs)
        self.perception_module = perception_module

    @property
    def role_prompt(self) -> str:
        return (
            "You are the Perception Worker. You acquire and pre-process multi-source urban data:\n"
            "- OpenStreetMap (roads, buildings, POIs, land use)\n"
            "- Remote sensing imagery (satellite, aerial)\n"
            "- Street-view imagery (scene classification)\n"
            "- Trajectory data (OD matrices, flow patterns)\n"
            "- GeoJSON/Shapefile (feature collections)\n"
            "Output structured perception data for downstream analysis."
        )

    async def execute(self, message: AgentMessage) -> AgentMessage:
        self.log_message(message)
        payload = message.payload
        task_data = payload.get("input_data", {})

        if self.perception_module is not None:
            result = await self.perception_module.process(
                task_data, task_data.get("city_data")
            )
        else:
            # 轻量兜底
            result = {
                "status": "perception_complete",
                "data_sources": task_data.get("required_data", ["osm"]),
                "features": task_data,
            }

        result = self._attach_evidence_manifest(task_data, result)

        return AgentMessage(
            sender=self.role,
            receiver=AgentRole.MANAGER,
            msg_type="result",
            payload=result,
            trace_id=message.trace_id,
        )

    def _attach_evidence_manifest(self, task_data: Dict[str, Any], result: Any) -> Dict[str, Any]:
        if not isinstance(result, dict):
            result = {
                "status": "perception_complete",
                "features": result,
            }

        existing_manifest = result.get("evidence_manifest")
        if not isinstance(existing_manifest, dict):
            existing_manifest = {}

        spatial_existing = existing_manifest.get("spatial", {})
        temporal_existing = existing_manifest.get("temporal", {})
        population_existing = existing_manifest.get("population", {})
        governance_existing = existing_manifest.get("governance", {})

        bounds = (
            result.get("bounds")
            or task_data.get("bounds")
            or task_data.get("bbox")
            or spatial_existing.get("bbox")
        )
        data_sources = self._unique_list(
            self._as_list(result.get("data_sources"))
            + self._as_list(task_data.get("required_data"))
            + self._as_list(existing_manifest.get("data_sources"))
        )
        task_type = task_data.get("task_type") or task_data.get("type") or result.get("type")
        tags = self._unique_list(
            self._as_list(existing_manifest.get("tags"))
            + self._as_list(task_data.get("tags"))
            + self._as_list(data_sources)
            + ([task_type] if task_type else [])
            + ([task_data.get("admin_level")] if task_data.get("admin_level") else [])
        )

        manifest = EvidenceManifest(
            spatial=SpatialEvidence(
                bbox=self._normalize_bbox(bounds),
                crs=spatial_existing.get("crs") or task_data.get("crs"),
                admin_level=spatial_existing.get("admin_level") or task_data.get("admin_level"),
                scale_band=spatial_existing.get("scale_band") or task_data.get("scale_band"),
                spatial_relation_frame=(
                    spatial_existing.get("spatial_relation_frame")
                    or task_data.get("spatial_relation_frame")
                ),
            ),
            temporal=TemporalEvidence(
                timestamp=self._coerce_timestamp(
                    temporal_existing.get("timestamp") or task_data.get("timestamp")
                ),
                time_window=temporal_existing.get("time_window") or task_data.get("time_window"),
                granularity=temporal_existing.get("granularity") or task_data.get("granularity"),
                forecast_horizon=(
                    temporal_existing.get("forecast_horizon")
                    or task_data.get("forecast_horizon")
                ),
                freshness=temporal_existing.get("freshness") or task_data.get("freshness"),
            ),
            population=PopulationEvidence(
                target_group=population_existing.get("target_group") or task_data.get("target_group"),
                observed_group=(
                    population_existing.get("observed_group") or task_data.get("observed_group")
                ),
                affected_group=(
                    population_existing.get("affected_group") or task_data.get("affected_group")
                ),
                sampling_bias=(
                    population_existing.get("sampling_bias") or task_data.get("sampling_bias")
                ),
                stakeholder_source=(
                    population_existing.get("stakeholder_source")
                    or task_data.get("stakeholder_source")
                ),
            ),
            governance=GovernanceEvidence(
                provenance=(
                    governance_existing.get("provenance")
                    or task_data.get("provenance")
                    or "+".join(data_sources)
                ),
                license=governance_existing.get("license") or task_data.get("license"),
                collection_method=(
                    governance_existing.get("collection_method")
                    or task_data.get("collection_method")
                ),
                uncertainty=(
                    governance_existing.get("uncertainty") or task_data.get("uncertainty")
                ),
                missing_layers=self._as_list(
                    governance_existing.get("missing_layers") or task_data.get("missing_layers")
                ),
            ),
            tags=tags,
            data_sources=data_sources,
        ).to_dict()

        result["data_sources"] = data_sources
        result["evidence_manifest"] = manifest
        return result

    def _normalize_bbox(self, bounds: Any):
        if isinstance(bounds, dict):
            keys = ("min_lon", "min_lat", "max_lon", "max_lat")
            if all(key in bounds for key in keys):
                return [bounds[key] for key in keys]
        if isinstance(bounds, (list, tuple)) and len(bounds) == 4:
            return list(bounds)
        return None

    def _coerce_timestamp(self, value: Any) -> str:
        if hasattr(value, "isoformat"):
            return value.isoformat()
        if isinstance(value, str) and value.strip():
            return value
        return datetime.now().isoformat()

    def _as_list(self, value: Any) -> list:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        return [value]

    def _unique_list(self, values: list) -> list:
        unique = []
        for value in values:
            if value in (None, ""):
                continue
            if value not in unique:
                unique.append(value)
        return unique


class AnalystWorker(BaseAgent):
    """
    分析 Worker — 空间推理与定量计算

    复用 urban_agent.core.reasoning.ReasoningModule
    参考 GeoAgent Analyst 的四阶段管线：
    data understanding → code generation → code inspection → debugging
    """

    def __init__(
        self,
        reasoning_module: Optional[Any] = None,
        llm_client: Optional[Any] = None,
        **kwargs,
    ):
        super().__init__(role=AgentRole.ANALYST, llm_client=llm_client, **kwargs)
        self.reasoning_module = reasoning_module

    @property
    def role_prompt(self) -> str:
        return (
            "You are the Analyst Worker. You perform spatial reasoning and quantitative analysis:\n"
            "- Dual-space cognition (topological graph + vector geometry)\n"
            "- Task-specific reasoning (population, mobility, traffic, navigation, etc.)\n"
            "- Pattern recognition (network metrics, urban fabric type)\n"
            "- Knowledge graph integration\n"
            "Output structured analysis results with confidence scores."
        )

    async def execute(self, message: AgentMessage) -> AgentMessage:
        self.log_message(message)
        payload = message.payload
        task_data = payload.get("input_data", {})
        dep_results = payload.get("dependency_results", {})

        # 合并上游感知数据
        perception_data = {}
        for dep_data in dep_results.values():
            if isinstance(dep_data, dict):
                perception_data.update(dep_data)

        if self.reasoning_module is not None:
            result = await self.reasoning_module.infer(
                perception_data, {}, task_data
            )
        else:
            result = {
                "status": "analysis_complete",
                "reasoning": "rule-based fallback",
                "input_summary": list(perception_data.keys()),
            }

        return AgentMessage(
            sender=self.role,
            receiver=AgentRole.MANAGER,
            msg_type="result",
            payload=result,
            trace_id=message.trace_id,
        )


class CartographerWorker(BaseAgent):
    """
    制图 Worker — 可视化输出生成

    复用 urban_agent.visualization 模块
    参考 GeoAgent Cartographer 的四阶段可视化管线
    """

    def __init__(
        self,
        visualization_module: Optional[Any] = None,
        llm_client: Optional[Any] = None,
        **kwargs,
    ):
        super().__init__(role=AgentRole.CARTOGRAPHER, llm_client=llm_client, **kwargs)
        self.visualization_module = visualization_module

    @property
    def role_prompt(self) -> str:
        return (
            "You are the Cartographer Worker. You generate spatial visualizations:\n"
            "- SVG overlays with geospatial coordinates\n"
            "- GeoJSON Feature Collections for GIS compatibility\n"
            "- Map symbology and color scheme selection\n"
            "- Legend, scale bar, and annotation placement\n"
            "Output publication-quality cartographic products."
        )

    async def execute(self, message: AgentMessage) -> AgentMessage:
        self.log_message(message)
        payload = message.payload
        dep_results = payload.get("dependency_results", {})

        analysis_data = {}
        for dep_data in dep_results.values():
            if isinstance(dep_data, dict):
                analysis_data.update(dep_data)

        if self.visualization_module is not None:
            result = self.visualization_module.render(analysis_data)
        else:
            result = {
                "status": "visualization_complete",
                "outputs": ["svg_overlay", "geojson"],
                "input_keys": list(analysis_data.keys()),
            }

        return AgentMessage(
            sender=self.role,
            receiver=AgentRole.MANAGER,
            msg_type="result",
            payload=result,
            trace_id=message.trace_id,
        )


class ReporterWorker(BaseAgent):
    """
    报告 Worker — 结果整合与叙事生成

    参考 GeoAgent Reporter 的单节点架构：
    将分析结果转化为专业的 Markdown 报告
    """

    def __init__(self, llm_client: Optional[Any] = None, **kwargs):
        super().__init__(role=AgentRole.REPORTER, llm_client=llm_client, **kwargs)

    @property
    def role_prompt(self) -> str:
        return (
            "You are the Reporter Worker. You synthesize analysis results into reports:\n"
            "- Executive summary of key findings\n"
            "- Structured sections (Background, Methods, Results, Discussion)\n"
            "- Quantitative metrics with interpretation\n"
            "- Spatial narrative and design recommendations\n"
            "Output professional Markdown reports."
        )

    async def execute(self, message: AgentMessage) -> AgentMessage:
        self.log_message(message)
        payload = message.payload
        dep_results = payload.get("dependency_results", {})
        objective = payload.get("objective", "Generate report")

        # 收集所有上游结果
        all_results = {}
        for dep_data in dep_results.values():
            if isinstance(dep_data, dict):
                all_results.update(dep_data)

        if self.llm_client is not None:
            prompt = (
                f"{self.role_prompt}\n\n"
                f"Task: {objective}\n"
                f"Analysis Results:\n{_safe_json(all_results)}\n\n"
                "Generate a concise Markdown report."
            )
            try:
                report_text = await self.call_llm(prompt)
                result = {"status": "report_complete", "report": report_text}
            except Exception as e:
                logger.warning(f"LLM report generation failed: {e}")
                result = {"status": "report_complete", "report": _fallback_report(all_results)}
        else:
            result = {"status": "report_complete", "report": _fallback_report(all_results)}

        return AgentMessage(
            sender=self.role,
            receiver=AgentRole.MANAGER,
            msg_type="result",
            payload=result,
            trace_id=message.trace_id,
        )


def _safe_json(data: Any, max_len: int = 2000) -> str:
    """安全序列化，截断过长内容"""
    import json

    try:
        text = json.dumps(data, ensure_ascii=False, default=str, indent=2)
    except Exception:
        text = str(data)
    return text[:max_len] if len(text) > max_len else text


def _fallback_report(results: Dict) -> str:
    """LLM 不可用时的兜底报告"""
    lines = ["# Urban Analysis Report\n"]
    for key, val in results.items():
        lines.append(f"## {key}\n")
        lines.append(f"```\n{_safe_json(val, 500)}\n```\n")
    return "\n".join(lines)
