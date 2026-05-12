from urban_agent.capabilities import get_default_capability_registry, get_default_tool_broker


def test_registry_discloses_capabilities_progressively():
    registry = get_default_capability_registry()

    level0 = registry.disclose(["network_accessibility"], level=0)[0]
    level1 = registry.disclose(["network_accessibility"], level=1)[0]
    level2 = registry.disclose(["network_accessibility"], level=2)[0]

    assert "inputs" not in level0
    assert "inputs" in level1
    assert level2["invocation"]["mcp_tool"] == "measure_accessibility"


def test_registry_treats_ml_as_method_level_capability():
    registry = get_default_capability_registry()

    selected = registry.search("train a deep learning model with pytorch for land use classification")
    names = [capability.name for capability in selected]

    assert "urban_ml_modeling" in names


def test_registry_matches_chinese_mixed_method_task():
    registry = get_default_capability_registry()

    selected = registry.search("分析老城区步行可达性、开放空间短板，并用PyTorch训练一个土地利用分类模型")
    names = [capability.name for capability in selected]

    assert "network_accessibility" in names
    assert "urban_ml_modeling" in names


def test_registry_selects_3d_and_streetview_semantic_capabilities():
    registry = get_default_capability_registry()

    context = registry.select_for_task(
        "需要QGIS 3D三维视图、Rhino Grasshopper参数化，以及街景语义分割和MLLM视觉评估",
        limit=12,
    )
    names = context["selected_names"]

    assert "urban_3d_scene_generation" in names
    assert "rhino_grasshopper_bridge" in names
    assert "streetview_semantic_segmentation" in names
    assert "streetview_mllm_evaluation" in names


def test_registry_filters_dataset_provenance_false_positives():
    registry = get_default_capability_registry()

    context = registry.select_for_task({
        "stage": "single_district_single_indicator",
        "question": "Calculate one building density and urban morphology indicator from declared district data before scaling up.",
        "data_resources": {
            "predicted_building_function_poi": "machine-learning-predicted building function POI dataset",
            "osm_or_osm_cache": "OSM 道路和建筑轮廓数据",
        },
        "evaluation_focus": ["problem-data-method validation"],
    })

    assert "urban_density_morphology" in context["selected_names"]
    assert "urban_ml_modeling" not in context["selected_names"]


def test_tool_broker_executes_mcp_backed_capability():
    broker = get_default_tool_broker()

    result = broker.execute(
        "spatial_overlay_export",
        {"features": [], "crs": "EPSG:4326"},
    )

    assert result["success"] is True
    assert result["result"]["feature_count"] == 0
