"""
UrbanAgent Web Interface — FastAPI backend
Provides REST + WebSocket endpoints for the interactive urban analysis frontend.
"""

import asyncio
import json
import uuid
import sys
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

# Add parent directory to path so we can import urban_agent
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

app = FastAPI(title="UrbanAgent Interactive Interface", version="0.1.0")

# Serve static files
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── Data models ──────────────────────────────────────────────────────────
class AnalysisRequest(BaseModel):
    location: str = Field(..., description="地名或 lat,lon 坐标")
    task: str = Field(..., description="自然语言分析任务")
    radius: int = Field(500, ge=100, le=5000)
    mode: str = Field("guided", pattern="^(guided|supervisory|autonomous)$")


class CheckpointResponse(BaseModel):
    checkpoint_id: str
    action: str  # approve / modify / reject
    modifications: Optional[dict] = None


# ── In-memory session store (lightweight; no DB dependency) ──────────────
sessions: dict = {}


# ── Routes ───────────────────────────────────────────────────────────────
@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# ── WebSocket: real-time agent pipeline ──────────────────────────────────
@app.websocket("/ws/analysis")
async def analysis_ws(ws: WebSocket):
    """
    WebSocket endpoint that drives the agent pipeline with human-in-the-loop
    checkpoints.  Messages flow as JSON frames:

    Client → Server:
        { "type": "start", "location": "...", "task": "...", "radius": 500, "mode": "guided" }
        { "type": "checkpoint_response", "checkpoint_id": "...", "action": "approve" }

    Server → Client:
        { "type": "stage", "stage": "perception", "status": "running" }
        { "type": "checkpoint", "checkpoint_id": "dp-1", "title": "...", "data": {...} }
        { "type": "result", "stage": "perception", "data": {...} }
        { "type": "complete", "summary": {...} }
    """
    await ws.accept()
    session_id = str(uuid.uuid4())[:8]
    sessions[session_id] = {"status": "connected"}

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)

            if msg.get("type") == "start":
                await _run_pipeline(ws, session_id, msg)

            elif msg.get("type") == "checkpoint_response":
                # Store response so the pipeline coroutine can pick it up
                sessions[session_id]["checkpoint_result"] = msg

    except WebSocketDisconnect:
        sessions.pop(session_id, None)


async def _wait_for_checkpoint(ws: WebSocket, session_id: str,
                                checkpoint_id: str, title: str,
                                description: str, data: dict,
                                mode: str) -> dict:
    """Send a checkpoint to the client and wait for a response (guided mode)
    or auto-approve (supervisory/autonomous)."""
    payload = {
        "type": "checkpoint",
        "checkpoint_id": checkpoint_id,
        "title": title,
        "description": description,
        "data": data,
    }
    await ws.send_json(payload)

    if mode == "autonomous":
        return {"action": "approve"}

    if mode == "supervisory":
        # Auto-approve but still log
        return {"action": "approve"}

    # Guided mode: wait for user response
    while True:
        raw = await ws.receive_text()
        resp = json.loads(raw)
        if resp.get("type") == "checkpoint_response" and resp.get("checkpoint_id") == checkpoint_id:
            return resp
        # If it's some other message, keep waiting


async def _run_pipeline(ws: WebSocket, session_id: str, params: dict):
    """Execute the UrbanAgent pipeline with checkpoint pauses."""
    location = params.get("location", "Shanghai, China")
    task = params.get("task", "Analyze walkability")
    radius = params.get("radius", 500)
    mode = params.get("mode", "guided")

    # ── DP-1: Task Interpretation ────────────────────────────────────
    await ws.send_json({"type": "stage", "stage": "task_interpretation", "status": "running"})
    await asyncio.sleep(0.3)

    task_interpretation = {
        "task_type": _infer_task_type(task),
        "location": location,
        "radius": radius,
        "inferred_metrics": _infer_metrics(task),
        "data_sources": ["OpenStreetMap roads", "Building footprints", "POI"],
    }
    dp1 = await _wait_for_checkpoint(
        ws, session_id, "dp-1",
        "DP-1: 任务理解确认",
        "Agent 已解析您的分析意图，请确认或修改以下任务理解：",
        task_interpretation, mode,
    )
    if dp1.get("action") == "reject":
        await ws.send_json({"type": "cancelled", "reason": "用户取消任务"})
        return
    await ws.send_json({"type": "stage", "stage": "task_interpretation", "status": "done", "data": task_interpretation})

    # ── DP-2: Data Source Validation ─────────────────────────────────
    await ws.send_json({"type": "stage", "stage": "perception", "status": "running"})
    await asyncio.sleep(0.5)

    data_plan = {
        "osm_layers": ["highway", "building", "amenity"],
        "imagery": "Street-view panoramas (if available)",
        "trajectory": "None requested",
        "bbox_preview": {"center": location, "radius_m": radius},
    }
    dp2 = await _wait_for_checkpoint(
        ws, session_id, "dp-2",
        "DP-2: 数据源确认",
        "以下数据源将被获取，请确认或添加约束：",
        data_plan, mode,
    )
    await ws.send_json({"type": "stage", "stage": "perception", "status": "done", "data": data_plan})

    # ── Perception execution (simulated for demo) ────────────────────
    await ws.send_json({"type": "stage", "stage": "perception_exec", "status": "running",
                        "message": "正在从 OpenStreetMap 获取数据..."})
    perception_result = await _simulate_perception(location, radius)
    await ws.send_json({"type": "result", "stage": "perception", "data": perception_result})

    # ── DP-3: Spatial Representation Review ──────────────────────────
    await ws.send_json({"type": "stage", "stage": "cognition", "status": "running"})
    await asyncio.sleep(0.5)

    cognition_result = _simulate_cognition(perception_result)
    dp3 = await _wait_for_checkpoint(
        ws, session_id, "dp-3",
        "DP-3: 空间结构审查",
        "Agent 已构建拓扑图和向量表示，请审查空间结构是否合理：",
        cognition_result, mode,
    )
    await ws.send_json({"type": "stage", "stage": "cognition", "status": "done", "data": cognition_result})

    # ── DP-4: Intervention Proposal Selection ────────────────────────
    await ws.send_json({"type": "stage", "stage": "decision", "status": "running"})
    await asyncio.sleep(0.5)

    proposals = _simulate_proposals(cognition_result)
    dp4 = await _wait_for_checkpoint(
        ws, session_id, "dp-4",
        "DP-4: 干预方案选择",
        "Agent 生成了以下空间干预建议，请选择或修改：",
        {"proposals": proposals}, mode,
    )
    selected = proposals  # In full implementation, filter by user selection
    await ws.send_json({"type": "stage", "stage": "decision", "status": "done", "data": {"selected_proposals": selected}})

    # ── DP-5: Parameter Tuning ───────────────────────────────────────
    params_data = {
        "dbscan_eps": 50,
        "walkability_weights": {"intersection_density": 0.4, "poi_density": 0.3, "greenery": 0.3},
        "accessibility_threshold_m": 400,
    }
    dp5 = await _wait_for_checkpoint(
        ws, session_id, "dp-5",
        "DP-5: 参数调优",
        "以下分析参数可调整，修改后将重新计算结果：",
        params_data, mode,
    )
    await ws.send_json({"type": "stage", "stage": "parameters", "status": "done", "data": params_data})

    # ── Visualization ────────────────────────────────────────────────
    await ws.send_json({"type": "stage", "stage": "visualization", "status": "running"})
    await asyncio.sleep(0.3)

    viz = _simulate_visualization(perception_result, selected)
    await ws.send_json({"type": "result", "stage": "visualization", "data": viz})

    # ── DP-6: Result Interpretation ──────────────────────────────────
    summary = {
        "location": location,
        "task": task,
        "key_findings": [
            f"研究区域内共检测到 {perception_result['stats']['roads']} 条道路段和 {perception_result['stats']['buildings']} 栋建筑",
            f"识别出 {cognition_result['topology']['junction_nodes']} 个路口节点和 {cognition_result['topology']['barrier_relations']} 条障碍关系",
            f"生成 {len(selected)} 项空间干预建议",
        ],
        "metrics": cognition_result.get("metrics", {}),
        "narrative": f"对 {location} 的分析表明，该区域的整体步行友好度评分为 {cognition_result.get('metrics', {}).get('walkability_score', 0.65):.2f}。"
                     f"主要问题集中在南部边缘的连通性不足，建议增设人行横道和口袋公园。",
    }
    dp6 = await _wait_for_checkpoint(
        ws, session_id, "dp-6",
        "DP-6: 结果解读确认",
        "以下为分析结论摘要，请审阅并补充领域知识：",
        summary, mode,
    )
    await ws.send_json({"type": "stage", "stage": "interpretation", "status": "done"})

    # ── Complete ─────────────────────────────────────────────────────
    await ws.send_json({
        "type": "complete",
        "summary": summary,
        "geojson": viz.get("geojson"),
    })


# ── Simulation helpers (replace with real UrbanAgent calls) ──────────────

def _infer_task_type(task: str) -> str:
    task_lower = task.lower()
    if any(w in task_lower for w in ["walkability", "步行", "walk"]):
        return "walkability_assessment"
    if any(w in task_lower for w in ["connectivity", "连通", "网络"]):
        return "connectivity_analysis"
    if any(w in task_lower for w in ["explore", "探索", "exploration"]):
        return "urban_exploration"
    if any(w in task_lower for w in ["traffic", "交通", "signal"]):
        return "traffic_signal"
    return "general_analysis"


def _infer_metrics(task: str) -> list:
    metrics = ["connectivity_index", "poi_density"]
    task_lower = task.lower()
    if "walk" in task_lower or "步行" in task_lower:
        metrics += ["walkability_score", "intersection_density"]
    if "green" in task_lower or "绿" in task_lower:
        metrics.append("greenery_ratio")
    return metrics


async def _simulate_perception(location: str, radius: int) -> dict:
    await asyncio.sleep(1.0)  # Simulate processing time
    return {
        "stats": {"roads": 127, "buildings": 342, "pois": 89},
        "road_types": {"tertiary": 23, "residential": 45, "pedestrian": 18, "service": 41},
        "poi_categories": {"food": 32, "retail": 21, "cultural": 8, "residential": 15, "other": 13},
        "bbox": [121.4650, 31.2050, 121.4750, 31.2150],
        "center": [121.4700, 31.2100],
    }


def _simulate_cognition(perception: dict) -> dict:
    return {
        "topology": {
            "junction_nodes": 23, "plaza_nodes": 8, "cluster_nodes": 15,
            "landmark_nodes": 4, "barrier_nodes": 2,
            "total_relations": 47, "barrier_relations": 3,
        },
        "patterns": {
            "network_type": "organic",
            "clustering_coefficient": 0.12,
            "connected_components": 3,
            "bridge_edges": 4,
        },
        "metrics": {
            "global_connectivity": 0.67,
            "local_connectivity": 2.4,
            "walkability_score": 0.65,
            "intersection_density_per_km2": 42,
            "poi_density_per_km2": 156,
        },
        "nodes": [
            {"id": "j1", "type": "junction", "lat": 31.2100, "lng": 121.4700, "degree": 4},
            {"id": "j2", "type": "junction", "lat": 31.2085, "lng": 121.4720, "degree": 3},
            {"id": "j3", "type": "junction", "lat": 31.2115, "lng": 121.4680, "degree": 5},
            {"id": "p1", "type": "plaza", "lat": 31.2095, "lng": 121.4710, "name": "田子坊广场"},
            {"id": "l1", "type": "landmark", "lat": 31.2108, "lng": 121.4695, "name": "石库门建筑群"},
            {"id": "b1", "type": "barrier", "lat": 31.2060, "lng": 121.4700, "name": "建国中路"},
        ],
        "edges": [
            {"from": "j1", "to": "j2", "type": "connected", "distance_m": 180},
            {"from": "j1", "to": "j3", "type": "connected", "distance_m": 220},
            {"from": "j2", "to": "p1", "type": "adjacent", "distance_m": 85},
            {"from": "j3", "to": "l1", "type": "adjacent", "distance_m": 60},
            {"from": "j2", "to": "b1", "type": "separated", "distance_m": 300},
        ],
    }


def _simulate_proposals(cognition: dict) -> list:
    return [
        {
            "id": "prop-1",
            "type": "connectivity",
            "title": "建国中路人行横道改善",
            "description": "在建国中路增设平面人行横道，连接南北两侧被隔离的路口节点",
            "impact": "预计将南部边缘步行友好度提升 0.15",
            "geometry": {"type": "LineString", "coordinates": [[121.4695, 31.2060], [121.4705, 31.2060]]},
            "color": "#4CAF50",
        },
        {
            "id": "prop-2",
            "type": "open_space",
            "title": "高密度区域口袋公园",
            "description": "在高密度建筑群中央插入一处200㎡口袋公园，缓解开放空间不足",
            "impact": "覆盖半径200m内居民可达绿地需求",
            "geometry": {"type": "Polygon", "coordinates": [[[121.4705, 31.2090], [121.4715, 31.2090],
                                                              [121.4715, 31.2098], [121.4705, 31.2098],
                                                              [121.4705, 31.2090]]]},
            "color": "#2196F3",
        },
        {
            "id": "prop-3",
            "type": "activity_node",
            "title": "南北主通道活力节点",
            "description": "在主南北通道交叉口设置混合功能活力节点，增加停留空间与商业界面",
            "impact": "预计将该节点周边POI密度提升20%",
            "geometry": {"type": "Point", "coordinates": [121.4700, 31.2100]},
            "color": "#FF9800",
        },
    ]


def _simulate_visualization(perception: dict, proposals: list) -> dict:
    """Build a GeoJSON FeatureCollection for the map layer."""
    features = []
    for p in proposals:
        features.append({
            "type": "Feature",
            "properties": {"id": p["id"], "title": p["title"], "type": p["type"],
                           "description": p["description"], "color": p["color"]},
            "geometry": p["geometry"],
        })
    return {
        "geojson": {"type": "FeatureCollection", "features": features},
        "svg": "<svg><!-- placeholder --></svg>",
    }


# ── Entry point ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8765, reload=True)
