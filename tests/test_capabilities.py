import json

from urban_agent.capabilities import (
    get_default_capability_registry,
    get_default_tool_broker,
    load_external_capability_cards,
)


def test_registry_discloses_capabilities_progressively():
    registry = get_default_capability_registry()

    level0 = registry.disclose(["urban_density_morphology"], level=0)[0]
    level1 = registry.disclose(["urban_density_morphology"], level=1)[0]
    level2 = registry.disclose(["urban_density_morphology"], level=2)[0]

    assert "inputs" not in level0
    assert "inputs" in level1
    assert level2["invocation"]["python_function"].endswith("compute_built_form_metrics")


def test_registry_matches_grounding_metric_and_export_tasks():
    registry = get_default_capability_registry()

    context = registry.select_for_task(
        "先声明数据集卡片，再计算建筑密度、功能混合度、街景一致性，并导出GIS图层栈",
        limit=8,
    )
    names = context["selected_names"]

    assert "input_grounding_artifacts" in names
    assert "urban_density_morphology" in names
    assert "function_mix_entropy" in names
    assert "streetview_visual_consistency" in names
    assert "gis_layer_stack_export" in names


def test_default_registry_excludes_case_benchmark_and_plugin_surfaces():
    registry = get_default_capability_registry()
    names = set(registry.names())

    forbidden = {
        "urban_ml_modeling",
        "urban_3d_scene_generation",
        "rhino_grasshopper_bridge",
        "qgis_project_and_render",
        "agentic_web_research",
        "agentic_terminal_process_control",
        "citybench_traffic_signal_control",
    }
    assert names.isdisjoint(forbidden)


def test_tool_broker_executes_python_backed_grounding_capability():
    broker = get_default_tool_broker()

    result = broker.execute(
        "input_grounding_artifacts",
        {
            "task_data": {
                "task": "analyze a district",
                "location": "test district",
                "indicators": [{"indicator": "building_density", "required_data": ["building_footprints"]}],
            },
            "path_context": {"paths": {"building_footprints": "buildings.geojson"}},
        },
    )

    assert result["dataset_cards"]
    assert result["indicator_computability_matrix"]


def test_external_capability_cards_are_loaded_explicitly(tmp_path):
    card_path = tmp_path / "capability.json"
    card_path.write_text(
        json.dumps(
            {
                "name": "agentic_web_research",
                "description": "Optional external web research tool surface.",
                "category": "plugin",
                "inputs": ["query"],
                "outputs": ["sources"],
                "tags": ["web", "research"],
                "backends": [
                    {
                        "name": "browser_plugin",
                        "kind": "external_plugin",
                        "target": "plugins.web:search",
                        "description": "External browser plugin.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    loaded = load_external_capability_cards([card_path])

    assert len(loaded) == 1
    assert loaded[0].name == "agentic_web_research"


def test_mcp_tools_expose_hermes_only_when_requested():
    from plugins.hermes import HERMES_CORE_TOOL_NAMES
    from plugins.mcp import get_mcp_tools

    default_tools = get_mcp_tools()
    assert set(default_tools.tools).isdisjoint(HERMES_CORE_TOOL_NAMES)

    hermes_tools = get_mcp_tools(include_hermes=True)
    for name in HERMES_CORE_TOOL_NAMES:
        assert name in hermes_tools.tools

    result = hermes_tools.execute_tool("todo", {"action": "add", "title": "Check AOI data"})
    assert result["success"] is True
    assert result["result"]["todo"]["title"] == "Check AOI data"


def test_agent_tools_live_in_core_tools_and_are_toolset_gated():
    from plugins.mcp import get_mcp_tools
    from urban_agent.tools import AGENT_TOOLSETS, get_agent_tool_specs

    assert "planning_memory" in AGENT_TOOLSETS
    assert len(get_agent_tool_specs(["planning_memory"])) == 4

    tools = get_mcp_tools(include_agent_tools=True, agent_toolsets=["planning_memory"])
    assert {"todo", "memory", "session_search", "clarify"}.issubset(tools.tools)
    assert "terminal" not in tools.tools
