import asyncio

from case_studies.runtime_observatory import ObservableUrbanRunner, RunArtifactStore, probe_qgis, qgis_commands_for_layer_stack, resolve_local_case


def test_observable_runner_streams_todos_and_artifacts(tmp_path):
    store = RunArtifactStore(tmp_path)
    runner = ObservableUrbanRunner(store)

    async def collect():
        frames = []
        async for frame in runner.run({
            "task": "Analyze walkability and public-space accessibility around the old bund",
            "location": "Ningbo Old Bund",
            "radius": 600,
            "mode": "supervisory",
        }):
            frames.append(frame)
        return frames

    frames = asyncio.run(collect())
    events = [frame["event"] for frame in frames if frame.get("type") == "event"]
    event_types = [event["type"] for event in events]

    assert "todo_created" in event_types
    assert "reasoning_step" in event_types
    assert "artifact_created" in event_types
    assert "run_completed" in event_types

    completed = next(frame for frame in frames if frame.get("type") == "complete")
    manifest = store.read_manifest(completed["run_id"])
    artifact_ids = {artifact["id"] for artifact in manifest["artifacts"]}

    assert {"measurement_report", "urban_layers_geojson", "feature_fields", "qgis_live_commands", "runtime_report"} <= artifact_ids

    measurement_record, measurement_path = store.resolve_artifact(completed["run_id"], "measurement_report")
    layer_record, layer_path = store.resolve_artifact(completed["run_id"], "urban_layers_geojson")

    assert measurement_record.type == "measurement_report"
    assert measurement_path.exists()
    assert layer_record.mime_type == "application/geo+json"
    assert layer_path.read_text(encoding="utf-8").startswith("{")


def test_qgis_probe_is_safe_without_qgis():
    status = probe_qgis()

    assert "available" in status
    assert "message" in status


def test_local_case_routing_does_not_hijack_generic_heritage_request():
    assert resolve_local_case({"task": "分析一个历史街区的空间形态指标", "location": "广州"}) is None


def test_qgis_commands_for_layer_stack_use_exported_geojson(tmp_path):
    geojson_path = tmp_path / "urban_layers.geojson"
    geojson_path.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    layer_metadata = {
        "layers": [
            {"id": "study_area", "name": "Study Area", "geometry": "Polygon"},
            {"id": "roads", "name": "Road Network", "geometry": "LineString"},
        ]
    }

    commands = qgis_commands_for_layer_stack(layer_metadata, geojson_path, title="UrbanAgent Test")
    actions = [command["action"] for command in commands]

    assert actions == ["set_project_title", "add_vector_layer", "zoom_to_full_extent", "refresh_canvas"]
    assert commands[1]["payload"]["path"] == geojson_path.as_posix()
    assert commands[1]["payload"]["name"] == "UrbanAgent GIS layer stack"