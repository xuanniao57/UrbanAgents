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

from ..capabilities import CapabilityRegistry, ToolBroker, get_default_capability_registry
from ..governance import (
    EvidenceManifest,
    GovernanceEvidence,
    PopulationEvidence,
    SpatialEvidence,
    TemporalEvidence,
)
from ..tools.geo_tools import discover_urban_data_sources
from ..tools.geo_small_tools import validate_source_extent_against_context
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
        capability_context = payload.get("capability_context") or task_data.get("capability_context", {})

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
                "capability_context": capability_context,
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

        path_context = discover_urban_data_sources({"task_data": task_data, "result": result})
        if path_context.get("paths"):
            result["accessible_paths"] = path_context["paths"]
            result["resource_catalog"] = path_context.get("resources", [])
            result["legend"] = path_context.get("legend", {})

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
            or path_context.get("bbox")
            or spatial_existing.get("bbox")
        )
        data_sources = self._unique_list(
            self._as_list(result.get("data_sources"))
            + self._as_list(task_data.get("required_data"))
            + self._as_list(existing_manifest.get("data_sources"))
            + self._as_list(path_context.get("data_sources"))
        )
        temporal_defaults = path_context.get("temporal", {})
        governance_defaults = path_context.get("governance", {})
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
                crs=spatial_existing.get("crs") or task_data.get("crs") or path_context.get("crs"),
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
                time_window=temporal_existing.get("time_window") or task_data.get("time_window") or temporal_defaults.get("time_window"),
                granularity=temporal_existing.get("granularity") or task_data.get("granularity") or temporal_defaults.get("granularity"),
                forecast_horizon=(
                    temporal_existing.get("forecast_horizon")
                    or task_data.get("forecast_horizon")
                ),
                freshness=temporal_existing.get("freshness") or task_data.get("freshness") or temporal_defaults.get("freshness"),
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
                    or governance_defaults.get("provenance")
                    or "+".join(data_sources)
                ),
                license=governance_existing.get("license") or task_data.get("license") or governance_defaults.get("license"),
                collection_method=(
                    governance_existing.get("collection_method")
                    or task_data.get("collection_method")
                    or governance_defaults.get("collection_method")
                ),
                uncertainty=(
                    governance_existing.get("uncertainty") or task_data.get("uncertainty")
                    or governance_defaults.get("uncertainty")
                ),
                missing_layers=self._as_list(
                    governance_existing.get("missing_layers") or task_data.get("missing_layers")
                ),
            ),
            tags=tags,
            data_sources=data_sources,
        ).to_dict()

        if path_context.get("resources"):
            manifest["resources"] = path_context["resources"]
        if path_context.get("legend"):
            manifest["legend"] = path_context["legend"]

        if path_context.get("paths", {}).get("boundary") and (path_context.get("paths", {}).get("roads") or path_context.get("paths", {}).get("buildings")):
            try:
                source_diag = validate_source_extent_against_context({"paths": path_context.get("paths", {})})
                result["input_spatial_diagnostics"] = source_diag
                if isinstance(source_diag, dict) and isinstance(source_diag.get("alignment_diagnostics"), dict):
                    result.setdefault("alignment_diagnostics", source_diag["alignment_diagnostics"])
            except Exception as error:
                result["input_spatial_diagnostics"] = {"status": "failed", "reason": str(error)}

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
        capability_registry: Optional[CapabilityRegistry] = None,
        disable_capabilities: bool = False,
        **kwargs,
    ):
        super().__init__(role=AgentRole.ANALYST, llm_client=llm_client, **kwargs)
        self.reasoning_module = reasoning_module
        self.capability_registry = capability_registry or get_default_capability_registry()
        self.tool_broker = ToolBroker(self.capability_registry)
        self.disable_capabilities = disable_capabilities

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
        capability_context = payload.get("capability_context") or task_data.get("capability_context", {})

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
                "candidate_capabilities": capability_context.get("selected_names", []),
            }

        quantitative = self._execute_quantitative_capabilities(task_data, perception_data, capability_context)
        if self.disable_capabilities:
            # True vanilla ablation: skip all quantitative capability execution
            quantitative = {}
        if quantitative.get("capability_results"):
            result.update({
                "status": "analysis_complete",
                "capability_results": quantitative["capability_results"],
                "metric_rows": quantitative["metric_rows"],
                "quantitative_summary": quantitative["summary"],
                "accessible_paths": quantitative.get("paths", {}),
                "resource_catalog": quantitative.get("resources", []),
                "evidence_manifest": quantitative.get("evidence_manifest", {}),
                "analysis": quantitative["analysis"],
                "answer": quantitative["answer"],
                "findings": quantitative["findings"],
                "limitations": quantitative["limitations"],
                "candidate_capabilities": quantitative["executed_capabilities"],
                "evidence_keys": list(perception_data.keys()),
            })

        needs_enrichment = (
            not result
            or result.get("reasoning") == "rule-based fallback"
            or str(result.get("conclusion", "")).lower() == "general reasoning completed"
            or not any(result.get(key) for key in ("answer", "analysis", "findings", "report", "llm_analysis"))
        )

        if self.llm_client is not None and needs_enrichment:
            try:
                question = task_data.get("question", str(task_data.get("objective", "")))
                llm_resp = await self.call_llm(
                    f"You are an urban analyst. Task: {question[:800]}\n"
                    f"Available capabilities: {capability_context.get('selected_names', [])}\n"
                    f"Perception data:\n{_safe_json(perception_data, 1800)}\n\n"
                    "Return strict JSON with keys: answer, analysis, findings, limitations, confidence. "
                    "The answer should state what can be computed from available data, what can only be proxied, "
                    "and what remains missing."
                )
                import json as _json
                response_text = llm_resp.strip()
                if response_text.startswith("```"):
                    response_text = response_text.strip("`")
                    if response_text.lower().startswith("json"):
                        response_text = response_text[4:].strip()
                start = response_text.find("{")
                end = response_text.rfind("}") + 1
                if start >= 0 and end > start:
                    llm_analysis = _json.loads(response_text[start:end])
                else:
                    llm_analysis = {"answer": response_text}
                result["llm_analysis"] = llm_analysis
                result["status"] = "analysis_complete"
                result["answer"] = str(llm_analysis.get("answer") or llm_analysis.get("summary") or "").strip()
                result["analysis"] = llm_analysis.get("analysis") or result["answer"]
                result["confidence"] = llm_analysis.get("confidence", result.get("confidence", 0.6))
                result.setdefault("findings", llm_analysis.get("findings", []))
                result.setdefault("limitations", llm_analysis.get("limitations", []))
                result["candidate_capabilities"] = capability_context.get("selected_names", [])
                result["evidence_keys"] = list(perception_data.keys())
            except Exception as error:
                logger.warning("LLM analyst enrichment failed: %s", error)
                result["status"] = "analysis_incomplete"
                result["llm_note"] = "LLM enrichment failed; no usable analysis was produced"
                result["limitations"] = [str(error)]

        return AgentMessage(
            sender=self.role,
            receiver=AgentRole.MANAGER,
            msg_type="result",
            payload=result,
            trace_id=message.trace_id,
        )

    def _execute_quantitative_capabilities(
        self,
        task_data: Dict[str, Any],
        perception_data: Dict[str, Any],
        capability_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        path_context = discover_urban_data_sources({"task_data": task_data, "perception_data": perception_data})
        capability_names = set(capability_context.get("selected_names", []) or [])
        paths = path_context.get("paths", {})
        task_text = _safe_json(task_data, 4000).lower()

        if paths.get("buildings"):
            capability_names.add("urban_density_morphology")
        if paths.get("function_counts") or paths.get("function_buildings") or paths.get("function_root") or "功能熵" in task_text or "poi" in task_text:
            capability_names.add("function_mix_entropy")
        if paths.get("streetview_dir") or "街景" in task_text or "streetview" in task_text:
            capability_names.add("streetview_visual_consistency")
            capability_names.add("streetview_semantic_segmentation")
        if any(token in task_text for token in ("mllm", "vlm", "多模态", "视觉语言", "街景评估")):
            capability_names.add("streetview_mllm_evaluation")

        executable_order = [
            "urban_density_morphology",
            "function_mix_entropy",
            "streetview_visual_consistency",
            "streetview_semantic_segmentation",
            "streetview_mllm_evaluation",
        ]
        capability_results: Dict[str, Any] = {}
        metric_rows = []
        limitations = []
        findings = []
        for capability_name in executable_order:
            if capability_name not in capability_names:
                continue
            try:
                output = self.tool_broker.execute(capability_name, {
                    "task_data": task_data,
                    "perception_data": perception_data,
                    "paths": paths,
                    "resources": path_context.get("resources", []),
                })
            except Exception as error:
                output = {"status": "failed", "capability": capability_name, "reason": str(error)}
            capability_results[capability_name] = output
            if isinstance(output, dict):
                metric_rows.extend(output.get("metric_rows", []) or [])
                limitations.extend(output.get("limitations", []) or [])
                summary = output.get("summary", {})
                if output.get("status") == "computed" and isinstance(summary, dict):
                    findings.append({"capability": capability_name, "summary": summary})

        if not capability_results:
            return {}

        answer = _format_quantitative_answer(capability_results, metric_rows, limitations)
        return {
            "capability_results": capability_results,
            "metric_rows": metric_rows,
            "summary": {key: value.get("summary", {}) for key, value in capability_results.items() if isinstance(value, dict)},
            "analysis": answer,
            "answer": answer,
            "findings": findings,
            "limitations": self._unique_strings(limitations),
            "executed_capabilities": list(capability_results.keys()),
            "paths": paths,
            "resources": path_context.get("resources", []),
            "evidence_manifest": _evidence_manifest_from_path_context(path_context),
        }

    @staticmethod
    def _unique_strings(values: list) -> list:
        unique = []
        for value in values:
            if value and value not in unique:
                unique.append(value)
        return unique


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
        capability_registry: Optional[CapabilityRegistry] = None,
        disable_capabilities: bool = False,
        **kwargs,
    ):
        super().__init__(role=AgentRole.CARTOGRAPHER, llm_client=llm_client, **kwargs)
        self.visualization_module = visualization_module
        self.capability_registry = capability_registry or get_default_capability_registry()
        self.tool_broker = ToolBroker(self.capability_registry)
        self.disable_capabilities = disable_capabilities

    @property
    def role_prompt(self) -> str:
        return (
            "You are the Cartographer Worker. You generate spatial visualizations:\n"
            "- SVG overlays with geospatial coordinates\n"
            "- GeoJSON Feature Collections for GIS compatibility\n"
            "- AOI-centered context-buffer layer stacks and AOI-clipped analysis layers\n"
            "- Spatialized metric/result layers for computed intermediate values\n"
            "- Map symbology and color scheme selection\n"
            "- Legend, scale bar, and annotation placement\n"
            "Output publication-quality cartographic products."
        )

    async def execute(self, message: AgentMessage) -> AgentMessage:
        self.log_message(message)
        payload = message.payload
        task_data = payload.get("input_data", {})
        dep_results = payload.get("dependency_results", {})

        analysis_data = {}
        for dep_data in dep_results.values():
            if isinstance(dep_data, dict):
                analysis_data.update(dep_data)

        if self.visualization_module is not None:
            result = self.visualization_module.render(analysis_data)
        elif self.disable_capabilities:
            result = {"status": "visualization_skipped", "reason": "capabilities disabled (vanilla ablation)", "outputs": []}
        else:
            try:
                result = self.tool_broker.execute("gis_layer_stack_export", {
                    "task_data": task_data,
                    "analysis_data": analysis_data,
                    "paths": analysis_data.get("accessible_paths", {}),
                    "resources": analysis_data.get("resource_catalog", []),
                    "metric_rows": analysis_data.get("metric_rows", []),
                    "artifact_dir": task_data.get("artifact_dir"),
                })
            except Exception as error:
                logger.warning("GIS artifact bundle generation failed: %s", error)
                result = {
                    "status": "visualization_incomplete",
                    "outputs": [],
                    "input_keys": list(analysis_data.keys()),
                    "error": str(error),
                }

            if not self.disable_capabilities and _requests_3d_visualization(task_data, analysis_data):
                result = self._attach_3d_artifacts(result, task_data, analysis_data)

        return AgentMessage(
            sender=self.role,
            receiver=AgentRole.MANAGER,
            msg_type="result",
            payload=result,
            trace_id=message.trace_id,
        )

    def _attach_3d_artifacts(self, result: Dict[str, Any], task_data: Dict[str, Any], analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(result, dict):
            result = {"status": "visualization_complete", "outputs": [], "artifacts": []}
        try:
            scene = self.tool_broker.execute("urban_3d_scene_generation", {
                "task_data": task_data,
                "analysis_data": analysis_data,
                "paths": analysis_data.get("accessible_paths", {}),
                "resources": analysis_data.get("resource_catalog", []),
                "artifact_dir": task_data.get("artifact_dir"),
            })
        except Exception as error:
            scene = {"status": "failed", "capability": "urban_3d_scene_generation", "reason": str(error)}
        try:
            rhino = self.tool_broker.execute("rhino_grasshopper_bridge", {"launch_rhino": False})
        except Exception as error:
            rhino = {"status": "failed", "capability": "rhino_grasshopper_bridge", "reason": str(error)}

        result["three_d_scene"] = scene
        result["rhino_grasshopper"] = rhino
        outputs = result.setdefault("outputs", [])
        artifacts = result.setdefault("artifacts", [])
        if isinstance(scene, dict):
            for artifact in scene.get("artifacts", []) or []:
                if artifact not in artifacts:
                    artifacts.append(artifact)
                if artifact.get("type") not in outputs:
                    outputs.append(artifact.get("type"))
        if "urban_3d_scene_generation" not in outputs:
            outputs.append("urban_3d_scene_generation")
        return result


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
                "Generate a concise Markdown report with explicit Methods, Results, Limitations, "
                "and Evidence Linkage sections. The Evidence Linkage section must name the data layers, "
                "computed metric rows, and GIS/chart artifacts used."
            )
            try:
                report_text = await self.call_llm(prompt)
                report_text = _ensure_evidence_linkage(report_text, all_results)
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


def _requests_3d_visualization(task_data: Dict[str, Any], analysis_data: Dict[str, Any]) -> bool:
    text = _safe_json({"task": task_data, "analysis": analysis_data}, 4000).lower()
    markers = ("3d", "qgis 3d", "三维", "3维", "rhino", "grasshopper", "草蜢", "参数化", "extrusion")
    return any(marker in text for marker in markers)


def _fallback_report(results: Dict) -> str:
    """LLM 不可用时的兜底报告"""
    lines = ["# Urban Analysis Report\n"]
    for key, val in results.items():
        lines.append(f"## {key}\n")
        lines.append(f"```\n{_safe_json(val, 500)}\n```\n")
    return "\n".join(lines)


def _ensure_evidence_linkage(report_text: str, results: Dict[str, Any]) -> str:
    text = report_text or ""
    lowered = text.lower()
    if "evidence" in lowered or "based on" in lowered:
        return text
    evidence_bits = []
    paths = results.get("accessible_paths") if isinstance(results.get("accessible_paths"), dict) else {}
    if paths:
        evidence_bits.append("Data layers: " + ", ".join(f"{key}={value}" for key, value in list(paths.items())[:8]))
    metric_rows = results.get("metric_rows") if isinstance(results.get("metric_rows"), list) else []
    if metric_rows:
        evidence_bits.append("Computed metrics: " + ", ".join(str(row.get("metric")) for row in metric_rows[:12]))
    artifacts = results.get("artifacts") if isinstance(results.get("artifacts"), list) else []
    if artifacts:
        evidence_bits.append("Artifacts: " + ", ".join(str(item.get("type")) for item in artifacts[:8]))
    if not evidence_bits:
        evidence_bits.append("Evidence linkage is recorded in upstream worker manifests and runtime artifacts.")
    return text.rstrip() + "\n\n## Evidence Linkage\n\n" + "\n".join(f"- {bit}" for bit in evidence_bits) + "\n"


def _format_quantitative_answer(capability_results: Dict[str, Any], metric_rows: list, limitations: list) -> str:
    lines = ["Quantitative capability execution completed with the following measured values:"]
    for row in metric_rows:
        value = row.get("value")
        if isinstance(value, float):
            value_text = f"{value:.4g}"
        else:
            value_text = str(value)
        lines.append(f"- {row.get('metric')}: {value_text} {row.get('unit', '')} ({row.get('method')})")
    unavailable = [name for name, payload in capability_results.items() if isinstance(payload, dict) and payload.get("status") != "computed"]
    if unavailable:
        lines.append("Unavailable capability outputs: " + ", ".join(unavailable))
    if limitations:
        lines.append("Limitations: " + " ".join(dict.fromkeys(str(item) for item in limitations)))
    return "\n".join(lines)


def _evidence_manifest_from_path_context(path_context: Dict[str, Any]) -> Dict[str, Any]:
    temporal = path_context.get("temporal", {}) or {}
    governance = path_context.get("governance", {}) or {}
    data_sources = path_context.get("data_sources", []) or []
    manifest = EvidenceManifest(
        spatial=SpatialEvidence(
            bbox=path_context.get("bbox"),
            crs=path_context.get("crs"),
            scale_band="district_or_corridor",
            spatial_relation_frame="AOI-clipped vector and street-view sample frame",
        ),
        temporal=TemporalEvidence(
            timestamp=datetime.now().isoformat(),
            time_window=temporal.get("time_window"),
            granularity=temporal.get("granularity"),
            freshness=temporal.get("freshness"),
        ),
        governance=GovernanceEvidence(
            provenance=governance.get("provenance"),
            license=governance.get("license"),
            collection_method=governance.get("collection_method"),
            uncertainty=governance.get("uncertainty"),
            missing_layers=[],
        ),
        tags=list(dict.fromkeys(["quantitative_analysis", "capability_execution"] + list(data_sources))),
        data_sources=list(data_sources),
    ).to_dict()
    if path_context.get("resources"):
        manifest["resources"] = path_context["resources"]
    if path_context.get("legend"):
        manifest["legend"] = path_context["legend"]
    return manifest
