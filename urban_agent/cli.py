"""
UrbanAgent CLI — 供 .agent.md 中的 LLM 通过终端调用的入口

Usage:
    python -m urban_agent.cli perceive --data-type osm --bbox "121.4,31.2,121.5,31.3"
    python -m urban_agent.cli cognize --input perception_result.json
    python -m urban_agent.cli reason --task-type geoqa --input cognition_result.json --question "..."
    python -m urban_agent.cli visualize --input analysis_result.json --format svg
    python -m urban_agent.cli review --input results.json
    python -m urban_agent.cli run --task-type geoqa --question "分析同济大学周边步行可达性"
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        prog="urban_agent",
        description="UrbanAgent CLI — 城市空间分析智能体命令行工具",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- perceive ---
    p_perceive = subparsers.add_parser("perceive", help="多源数据感知")
    p_perceive.add_argument("--data-type", required=True,
                            choices=["osm", "remote_sensing", "street_view", "trajectory", "geojson", "text", "mixed"],
                            help="数据类型")
    p_perceive.add_argument("--bbox", help="边界框: min_lon,min_lat,max_lon,max_lat")
    p_perceive.add_argument("--input", help="输入文件路径 (JSON)")
    p_perceive.add_argument("--output", help="输出文件路径 (JSON)", default="perception_result.json")

    # --- cognize ---
    p_cognize = subparsers.add_parser("cognize", help="双空间认知 (拓扑+矢量)")
    p_cognize.add_argument("--input", required=True, help="感知结果 JSON 文件")
    p_cognize.add_argument("--task", default="", help="任务描述")
    p_cognize.add_argument("--output", help="输出文件路径", default="cognition_result.json")

    # --- reason ---
    p_reason = subparsers.add_parser("reason", help="空间推理")
    p_reason.add_argument("--task-type", required=True,
                          choices=["population_prediction", "object_detection", "geolocation",
                                   "geoqa", "mobility_prediction", "traffic_signal",
                                   "outdoor_navigation", "urban_exploration"],
                          help="任务类型")
    p_reason.add_argument("--input", required=True, help="认知结果 JSON 文件")
    p_reason.add_argument("--question", default="", help="用户问题")
    p_reason.add_argument("--output", help="输出文件路径", default="reasoning_result.json")

    # --- visualize ---
    p_viz = subparsers.add_parser("visualize", help="可视化输出")
    p_viz.add_argument("--input", required=True, help="分析结果 JSON 文件")
    p_viz.add_argument("--format", choices=["svg", "geojson", "both"], default="svg", help="输出格式")
    p_viz.add_argument("--output", help="输出文件路径", default="visualization_output")

    # --- review ---
    p_review = subparsers.add_parser("review", help="空间质量审查")
    p_review.add_argument("--input", required=True, help="结果 JSON 文件")
    p_review.add_argument("--output", help="审查报告输出路径", default="review_report.json")

    # --- run ---
    p_run = subparsers.add_parser("run", help="端到端运行完整分析流水线")
    p_run.add_argument("--task-type", required=True, help="任务类型")
    p_run.add_argument("--question", required=True, help="分析问题")
    p_run.add_argument("--bbox", help="边界框: min_lon,min_lat,max_lon,max_lat")
    p_run.add_argument("--input", help="输入数据文件")
    p_run.add_argument("--output-dir", help="输出目录", default="./outputs")
    p_run.add_argument("--interaction-mode", choices=["autonomous", "supervisory", "guided"], 
                        default="autonomous", help="人机交互模式")

    args = parser.parse_args()

    if args.command == "perceive":
        asyncio.run(_cmd_perceive(args))
    elif args.command == "cognize":
        _cmd_cognize(args)
    elif args.command == "reason":
        asyncio.run(_cmd_reason(args))
    elif args.command == "visualize":
        _cmd_visualize(args)
    elif args.command == "review":
        _cmd_review(args)
    elif args.command == "run":
        asyncio.run(_cmd_run(args))


# ── Command implementations ──────────────────────────────────────

async def _cmd_perceive(args):
    """执行感知"""
    from .core.perception import PerceptionModule

    task = {"data_type": args.data_type}
    if args.bbox:
        parts = [float(x) for x in args.bbox.split(",")]
        task["bbox"] = {"min_lon": parts[0], "min_lat": parts[1], "max_lon": parts[2], "max_lat": parts[3]}
    if args.input:
        with open(args.input, encoding="utf-8") as f:
            task.update(json.load(f))

    module = PerceptionModule()
    result = await module.process(task)
    _write_json(result, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2)[:3000])


def _cmd_cognize(args):
    """执行双空间认知"""
    from .cognition import SpatialCognition

    with open(args.input, encoding="utf-8") as f:
        perception_data = json.load(f)

    # SpatialCognition.understand() expects a context object with raw_features
    # We create a lightweight adapter
    class _Context:
        def __init__(self, data):
            self.raw_features = data
            self.buildings = data.get("buildings", [])
            self.roads = data.get("roads", data.get("road_network", []))
            self.pois = data.get("pois", [])
            self.features = data

    cognition = SpatialCognition()
    result = cognition.understand(_Context(perception_data), args.task)
    _write_json(result, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str)[:3000])


async def _cmd_reason(args):
    """执行空间推理"""
    from .core.reasoning import ReasoningModule

    with open(args.input, encoding="utf-8") as f:
        input_data = json.load(f)

    task = {"task_type": args.task_type, "question": args.question}
    module = ReasoningModule()
    result = await module.infer(input_data, {}, task)
    _write_json(result, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str)[:3000])


def _cmd_visualize(args):
    """执行可视化"""
    from .visualization import SpatialVisualizer

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    viz = SpatialVisualizer()

    # 从数据中提取所需字段
    raw_features = data.get("raw_features", data.get("features", data))
    intervention_areas = data.get("intervention_areas", data.get("proposals", []))
    bbox = data.get("bbox", (0, 0, 1, 1))
    if isinstance(bbox, dict):
        bbox = (bbox.get("min_lon", 0), bbox.get("min_lat", 0),
                bbox.get("max_lon", 1), bbox.get("max_lat", 1))
    elif isinstance(bbox, list):
        bbox = tuple(bbox)

    if args.format in ("svg", "both"):
        svg_result = viz.create_svg_overlay(raw_features, intervention_areas, bbox)
        svg_path = f"{args.output}.svg"
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(svg_result if isinstance(svg_result, str) else str(svg_result))
        print(f"SVG written to {svg_path}")

    if args.format in ("geojson", "both"):
        geojson_result = viz.create_geojson_collection(intervention_areas, raw_features)
        geojson_path = f"{args.output}.geojson"
        with open(geojson_path, "w", encoding="utf-8") as f:
            json.dump(geojson_result, f, ensure_ascii=False, indent=2) if isinstance(geojson_result, dict) else f.write(str(geojson_result))
        print(f"GeoJSON written to {geojson_path}")


def _cmd_review(args):
    """执行空间质量审查"""
    with open(args.input, encoding="utf-8") as f:
        results = json.load(f)

    # Rule-based review (same logic as SpatialReviewerAgent)
    issues = []
    
    def _check_recursive(data, path=""):
        if isinstance(data, dict):
            for key in ("latitude", "lat"):
                val = data.get(key)
                if val is not None:
                    try:
                        if not (-90 <= float(val) <= 90):
                            issues.append(f"{path}.{key}={val}: latitude out of range [-90,90]")
                    except (ValueError, TypeError):
                        pass
            for key in ("longitude", "lon", "lng"):
                val = data.get(key)
                if val is not None:
                    try:
                        if not (-180 <= float(val) <= 180):
                            issues.append(f"{path}.{key}={val}: longitude out of range [-180,180]")
                    except (ValueError, TypeError):
                        pass
            for k, v in data.items():
                _check_recursive(v, f"{path}.{k}")
        elif isinstance(data, list):
            for i, item in enumerate(data):
                _check_recursive(item, f"{path}[{i}]")

    _check_recursive(results)
    quality_score = max(0.0, 1.0 - len(issues) * 0.15)
    report = {
        "quality_score": quality_score,
        "passed": quality_score >= 0.6,
        "issues": issues,
        "recommendation": "accept" if quality_score >= 0.6 else "revise",
    }
    _write_json(report, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))


async def _cmd_run(args):
    """端到端流水线"""
    from .agents.orchestrator import MultiAgentOrchestrator

    task = {"question": args.question, "task_type": args.task_type}
    if args.bbox:
        parts = [float(x) for x in args.bbox.split(",")]
        task["bbox"] = {"min_lon": parts[0], "min_lat": parts[1], "max_lon": parts[2], "max_lat": parts[3]}
    if args.input:
        with open(args.input, encoding="utf-8") as f:
            task.update(json.load(f))

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    orchestrator = MultiAgentOrchestrator(interaction_mode=args.interaction_mode)
    result = await orchestrator.run(task, task_type=args.task_type)

    output_path = output_dir / "run_result.json"
    _write_json(result, str(output_path))
    print(f"Result written to {output_path}")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str)[:5000])


def _write_json(data, path):
    """写 JSON 文件"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


if __name__ == "__main__":
    main()
