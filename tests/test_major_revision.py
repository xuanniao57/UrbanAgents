"""
Expanded test suite — covers new modules added during major revision.

Tests:
1. QualityController: confidence scoring, recommender/configurator modes
2. Governance: tool classification, access control, inventory table
3. Efficiency: tracking latency/tokens, summary, table export
4. Evaluator V2: complexity stratification
5. Orchestrator: ablation feature flags, QC gates
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# =========================================================================
# 1. QualityController
# =========================================================================

class TestQualityController:
    """Test RMDA-style quality control agent."""

    def test_import(self):
        from urban_agent.agents.quality_controller import QualityController, QualityReport
        assert QualityController is not None
        assert QualityReport is not None

    def test_default_weights(self):
        from urban_agent.agents.quality_controller import QualityController
        controller = QualityController()
        total = sum(controller.weights.values())
        assert abs(total - 1.0) < 1e-6, f"Weights must sum to 1.0, got {total}"

    def test_quality_report_dataclass(self):
        from urban_agent.agents.quality_controller import QualityReport
        report = QualityReport(
            agent_role="analyst",
            confidence_score=0.85,
            passed=True,
            dimension_scores={"semantic_relevance": 0.9},
            issues=[],
            recommendation="accept",
        )
        assert report.passed is True
        assert report.confidence_score == 0.85
        assert report.recommendation == "accept"

    def test_qc_role_in_enum(self):
        from urban_agent.agents.base import AgentRole
        assert hasattr(AgentRole, "QUALITY_CONTROLLER")
        assert AgentRole.QUALITY_CONTROLLER.value == "quality_controller"

    def test_qc_in_public_exports(self):
        from urban_agent.agents import QualityController
        assert QualityController is not None

    def test_recommender_qc_uses_targeted_reflection(self):
        from urban_agent.agents.quality_controller import QualityController

        class CapturingReflector:
            def __init__(self):
                self.calls = []

            async def reflect_quality(self, **kwargs):
                self.calls.append(kwargs)
                return {
                    "confidence": 0.91,
                    "passed": True,
                    "recommendation": "accept",
                    "issues": [],
                    "risks": ["data coverage should be stated"],
                    "reflection": "Output is contextually trustworthy with clear caveats.",
                    "source": "test_reflector",
                }

        reflector = CapturingReflector()
        controller = QualityController(reflector=reflector)
        report = asyncio.run(controller.assess(
            "analyst",
            {"status": "ok", "answer": "Walkability is constrained by arterial barriers."},
            {"required_fields": ["status", "answer"], "city": "Shanghai"},
        ))

        assert reflector.calls
        assert report.passed is True
        assert report.reflection["source"] == "test_reflector"
        assert report.dimension_scores["reflection_confidence"] == 0.91


# =========================================================================
# 2. Governance
# =========================================================================

class TestGovernance:
    """Test resource governance and tool classification."""

    def test_tool_category_enum(self):
        from urban_agent.governance import ToolCategory
        assert len(ToolCategory) == 3
        assert ToolCategory.SYSTEM_INTERACTION.value == "System Interaction"

    def test_tool_inventory_count(self):
        from urban_agent.governance import TOOL_INVENTORY
        assert len(TOOL_INVENTORY) == 8

    def test_tool_categories_distribution(self):
        from urban_agent.governance import TOOL_INVENTORY, ToolCategory
        by_cat = {}
        for t in TOOL_INVENTORY:
            by_cat[t.category] = by_cat.get(t.category, 0) + 1
        assert by_cat[ToolCategory.SYSTEM_INTERACTION] == 1
        assert by_cat[ToolCategory.DATA_UNDERSTANDING] == 5
        assert by_cat[ToolCategory.DOMAIN_KNOWLEDGE] == 2

    def test_governance_registry(self):
        from urban_agent.governance import GovernanceRegistry
        registry = GovernanceRegistry()
        assert registry.get_tool("fetch_osm_data") is not None
        assert registry.get_tool("nonexistent_tool") is None

    def test_access_control(self):
        from urban_agent.governance import GovernanceRegistry
        registry = GovernanceRegistry()
        # Perception should have read access to fetch_osm_data
        assert registry.check_access("perception", "fetch_osm_data", "R")
        # Reporter should not have write access to fetch_osm_data
        assert not registry.check_access("reporter", "fetch_osm_data", "W")

    def test_tool_inventory_table(self):
        from urban_agent.governance import GovernanceRegistry
        registry = GovernanceRegistry()
        table = registry.tool_inventory_table()
        assert len(table) == 8
        assert all("Category" in row and "Tool" in row for row in table)
        tools = {row["Tool"] for row in table}
        for name in ("fetch_osm_data", "calculate_density", "generate_measurement_report"):
            assert name in tools

    def test_data_resource(self):
        from urban_agent.governance import GovernanceRegistry, DataResource
        registry = GovernanceRegistry()
        resource = DataResource(
            resource_id="osm_paris",
            name="Paris OSM Data",
            description="OpenStreetMap data for Paris",
            source="OSM",
            format="GeoJSON",
            tags=["urban", "paris", "roads"],
        )
        registry.register_data(resource)
        assert registry.get_data("osm_paris") is not None
        assert len(registry.list_data_by_tags("urban")) == 1

    def test_access_matrix_completeness(self):
        from urban_agent.governance import ACCESS_MATRIX
        expected_roles = {"planner", "perception", "analyst", "cartographer",
                          "reporter", "spatial_reviewer", "quality_controller", "manager"}
        assert set(ACCESS_MATRIX.keys()) == expected_roles


# =========================================================================
# 3. Efficiency Tracker
# =========================================================================

class TestEfficiencyTracker:
    """Test per-layer efficiency tracking."""

    def test_basic_tracking(self):
        from urban_agent.agents.efficiency import EfficiencyTracker
        tracker = EfficiencyTracker()
        with tracker.track("planner") as rec:
            rec.input_tokens = 100
            rec.output_tokens = 50
        assert len(tracker.records) == 1
        assert tracker.records[0].layer == "planner"
        assert tracker.records[0].total_tokens == 150

    def test_cost_calculation(self):
        from urban_agent.agents.efficiency import StepRecord
        rec = StepRecord(layer="test", input_tokens=1000, output_tokens=500, model="gpt-4o")
        # gpt-4o: input=0.005/1K, output=0.015/1K
        expected = 1000 * 0.005 / 1000 + 500 * 0.015 / 1000
        assert abs(rec.cost_usd - expected) < 1e-6

    def test_summary(self):
        from urban_agent.agents.efficiency import EfficiencyTracker
        tracker = EfficiencyTracker()
        with tracker.track("planner") as rec:
            rec.input_tokens = 100
            rec.output_tokens = 50
        with tracker.track("analyst") as rec:
            rec.input_tokens = 200
            rec.output_tokens = 100
        summary = tracker.summarize()
        assert "per_layer" in summary
        assert "planner" in summary["per_layer"]
        assert "analyst" in summary["per_layer"]
        assert summary["total"]["total_tokens"] == 450

    def test_table_rows(self):
        from urban_agent.agents.efficiency import EfficiencyTracker
        tracker = EfficiencyTracker()
        with tracker.track("planner") as rec:
            rec.input_tokens = 100
        rows = tracker.to_table_rows()
        assert len(rows) == 2  # planner + TOTAL
        assert rows[-1]["Agent/Layer"] == "TOTAL"

    def test_reset(self):
        from urban_agent.agents.efficiency import EfficiencyTracker
        tracker = EfficiencyTracker()
        with tracker.track("test"):
            pass
        assert len(tracker.records) == 1
        tracker.reset()
        assert len(tracker.records) == 0


# =========================================================================
# 5. Orchestrator Feature Flags
# =========================================================================

class TestOrchestratorFlags:
    """Test ablation feature flags on orchestrator."""

    def test_full_config(self):
        from urban_agent.agents.orchestrator import MultiAgentOrchestrator
        orch = MultiAgentOrchestrator()
        assert orch.enable_planning is True
        assert orch.enable_review is True
        assert orch.enable_quality_control is True
        assert orch.enable_dual_space is True
        assert orch.enable_memory is True

    def test_disable_planning(self):
        from urban_agent.agents.orchestrator import MultiAgentOrchestrator
        orch = MultiAgentOrchestrator(enable_planning=False)
        assert orch.enable_planning is False

    def test_disable_qc(self):
        from urban_agent.agents.orchestrator import MultiAgentOrchestrator
        orch = MultiAgentOrchestrator(enable_quality_control=False)
        assert orch.quality_controller is None

    def test_enable_qc(self):
        from urban_agent.agents.orchestrator import MultiAgentOrchestrator
        orch = MultiAgentOrchestrator(enable_quality_control=True)
        assert orch.quality_controller is not None

    def test_disable_memory(self):
        from urban_agent.agents.orchestrator import MultiAgentOrchestrator
        orch = MultiAgentOrchestrator(enable_memory=False)
        assert orch.memory_module is None

    def test_vanilla_config(self):
        """All layers disabled = vanilla LLM (single-pass)."""
        from urban_agent.agents.orchestrator import MultiAgentOrchestrator
        orch = MultiAgentOrchestrator(
            enable_planning=False,
            enable_review=False,
            enable_quality_control=False,
            enable_dual_space=False,
            enable_memory=False,
        )
        assert orch.enable_planning is False
        assert orch.quality_controller is None

    def test_efficiency_report_empty(self):
        from urban_agent.agents.orchestrator import MultiAgentOrchestrator
        orch = MultiAgentOrchestrator()
        assert orch.get_efficiency_report() == []


# =========================================================================
# 6. Integration: public API exports
# =========================================================================

class TestPublicAPIExpanded:
    """Verify new modules are accessible from top-level package."""

    def test_qc_export(self):
        from urban_agent import QualityController
        assert QualityController is not None

    def test_no_experimental_label(self):
        import urban_agent.agents as agents_mod
        docstring = agents_mod.__doc__ or ""
        assert "EXPERIMENTAL" not in docstring
