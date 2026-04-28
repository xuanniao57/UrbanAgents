import asyncio

from urban_agent.runtime_observatory import ObservableUrbanRunner, RunArtifactStore, probe_qgis


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

    assert {"measurement_report", "urban_layers_geojson", "feature_fields", "runtime_report"} <= artifact_ids

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