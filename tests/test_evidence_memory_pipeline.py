import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from urban_agent.agents.base import AgentMessage, AgentRole
from urban_agent.agents.workers import PerceptionWorker
from urban_agent.core import MemoryModule


def test_perception_worker_attaches_typed_evidence_manifest():
    worker = PerceptionWorker()
    message = AgentMessage(
        sender=AgentRole.MANAGER,
        receiver=AgentRole.PERCEPTION,
        msg_type="subtask",
        payload={
            "input_data": {
                "task_type": "walkability_assessment",
                "required_data": ["osm", "survey"],
                "bounds": {
                    "min_lon": 121.40,
                    "min_lat": 31.20,
                    "max_lon": 121.50,
                    "max_lat": 31.30,
                },
                "crs": "EPSG:4326",
                "admin_level": "district",
                "scale_band": "street_block",
                "spatial_relation_frame": "network_topology",
                "time_window": "2026-04-23T08:00:00/2026-04-23T09:00:00",
                "granularity": "hourly",
                "forecast_horizon": "PT1H",
                "freshness": "current_day",
                "target_group": "pedestrians",
                "observed_group": "commuters",
                "affected_group": "pedestrians_and_elderly",
                "sampling_bias": "commute_peak",
                "stakeholder_source": "street_intercept_survey",
                "provenance": "osm+survey",
                "license": "ODbL + consented survey",
                "collection_method": "api_and_field_survey",
                "uncertainty": "moderate",
                "missing_layers": ["night_safety"],
            }
        },
    )

    result = asyncio.run(worker.execute(message))
    manifest = result.payload["evidence_manifest"]

    assert manifest["spatial"]["bbox"] == [121.4, 31.2, 121.5, 31.3]
    assert manifest["spatial"]["crs"] == "EPSG:4326"
    assert manifest["temporal"]["granularity"] == "hourly"
    assert manifest["population"]["target_group"] == "pedestrians"
    assert manifest["governance"]["provenance"] == "osm+survey"
    assert "walkability_assessment" in manifest["tags"]


def test_memory_module_surfaces_procedural_strategy_memory_after_reflection():
    async def _run():
        memory = MemoryModule(config={"short_term_size": 4})
        for idx in range(3):
            await memory.store(
                {
                    "task": {"task_type": "traffic_signal", "city": "Shanghai"},
                    "perception": {"type": "text", "location": "Shanghai"},
                    "action": {"answer": f"phase-plan-{idx}"},
                }
            )
        return memory.get_memory_stats(), await memory.retrieve({"task_type": "traffic_signal", "city": "Shanghai"})

    stats, context = asyncio.run(_run())

    assert stats["procedural_strategy_count"] >= 1
    assert context["relevant_long_term"]["procedural"]