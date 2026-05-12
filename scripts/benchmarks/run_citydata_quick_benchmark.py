"""
CityData-direct quick benchmark for UrbanAgent.

This runner avoids CityBench's full task runtime for the decouplable tasks and
uses a transparent proxy for traffic signal control.
"""

import asyncio
import argparse
import json
import logging
import math
import os
import pickle
import random
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from urban_agent.llm.qwen_client import QwenClient
from urban_agent.llm.kimi_client import KimiClient
from benchmarks.citybench import TrafficSignalAdapter
from urban_agent.task_agent import UrbanTaskAgent


UrbanAgent = UrbanTaskAgent


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

CITYBENCH_ROOT = ROOT / "third_party" / "CityBench-main"
CITYDATA_ROOT = CITYBENCH_ROOT / "citydata"
RESULTS_DIR = ROOT / "artifacts" / "benchmarks"
RANDOM_SEED = 42
SAMPLE_COUNT = 10
TRAFFIC_ADAPTER = TrafficSignalAdapter()


def to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): to_jsonable(val) for key, val in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return value


def load_env_file() -> None:
    env_candidates = [
        ROOT / ".env",
        Path(__file__).with_name(".env"),
    ]
    for env_path in env_candidates:
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


class CityDataQuickSampler:
    def __init__(self, citydata_root: Path, seed: int = RANDOM_SEED):
        self.citydata_root = citydata_root
        self.random = random.Random(seed)
        self.remote_root = citydata_root / "remote_sensing"
        self.street_root = citydata_root / "street_view"
        self.geoqa_root = citydata_root / "task_Geo_knowledge"
        self.mobility_root = citydata_root / "mobility"
        self.navigation_root = citydata_root / "outdoor_navigation_tasks"
        self.exploration_root = citydata_root / "exploration_tasks"
        self.object_labels = json.loads((self.remote_root / "all_city_img_object_set.json").read_text(encoding="utf-8"))

    def _sample_rows(self, rows: List[Dict[str, Any]], n: int) -> List[Dict[str, Any]]:
        if len(rows) <= n:
            return rows
        return self.random.sample(rows, n)

    def population_tasks(self, n: int) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for csv_file in sorted(self.remote_root.glob("*_img_indicators.csv")):
            city = csv_file.stem.replace("_img_indicators", "")
            df = pd.read_csv(csv_file)
            df = df[pd.notna(df["worldpop"])]
            for _, row in df.iterrows():
                ground_truth = float(row["worldpop"])
                if math.isnan(ground_truth):
                    continue
                image_path = self.remote_root / city / f"{row['img_name']}.png"
                if not image_path.exists():
                    continue
                choices = self._numeric_choices(ground_truth)
                answer = min(choices.items(), key=lambda item: abs(item[1] - ground_truth))[0]
                rows.append({
                    "task_type": "population_prediction",
                    "data_type": "remote_sensing",
                    "image_path": str(image_path),
                    "question": "Choose the closest population estimate for this grid.",
                    "choices": choices,
                    "indicator_values": {
                        "nightlight": float(row.get("nightlight") or 0),
                        "carbon": float(row.get("carbon") or 0),
                    },
                    "ground_truth": ground_truth,
                    "ground_truth_option": answer,
                    "city": city,
                })
        return self._sample_rows(rows, n)

    def object_detection_tasks(self, n: int) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for city_dir in sorted(self.remote_root.iterdir()):
            if not city_dir.is_dir():
                continue
            city = city_dir.name
            for image_path in city_dir.glob("*.png"):
                image_id = image_path.stem
                if image_id not in self.object_labels:
                    continue
                positives = sorted([
                    name for name, present in self.object_labels[image_id].items()
                    if int(present) == 1
                ])
                if not positives:
                    continue
                rows.append({
                    "task_type": "object_detection",
                    "data_type": "remote_sensing",
                    "image_path": str(image_path),
                    "ground_truth": positives,
                    "city": city,
                })
        return self._sample_rows(rows, n)

    def geolocation_tasks(self, n: int) -> List[Dict[str, Any]]:
        city_options = sorted([
            path.name.replace("_CUT", "")
            for path in self.street_root.glob("*_CUT")
            if path.is_dir()
        ])
        rows: List[Dict[str, Any]] = []
        for city in city_options:
            city_dir = self.street_root / f"{city}_CUT"
            images = list(city_dir.glob("*.jpg"))
            if not images:
                continue
            for image_path in self.random.sample(images, min(len(images), 3)):
                rows.append({
                    "task_type": "geolocation",
                    "data_type": "street_view",
                    "image_path": str(image_path),
                    "city_options": city_options,
                    "ground_truth": city,
                })
        return self._sample_rows(rows, n)

    def geoqa_tasks(self, n: int) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for csv_file in self.geoqa_root.glob("*/*/eval_*.csv"):
            df = pd.read_csv(csv_file)
            required = {"question", "answer", "A", "B", "C", "D", "E"}
            if not required.issubset(df.columns):
                continue
            for _, row in df.iterrows():
                choices = {key: row[key] for key in ["A", "B", "C", "D", "E"]}
                rows.append({
                    "task_type": "geoqa",
                    "data_type": "text",
                    "question": row["question"],
                    "choices": choices,
                    "ground_truth": str(row["answer"]).strip().upper(),
                    "context_text": row.to_dict(),
                })
        return self._sample_rows(rows, n)

    def mobility_tasks(self, n: int) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for city_file in sorted((self.mobility_root / "checkin_test_pk").glob("*_fin.pk")):
            city = city_file.stem.replace("_fin", "")
            train_df = pd.read_csv(self.mobility_root / "checkin_split" / f"{city}_train.csv")
            valid_df = pd.read_csv(self.mobility_root / "checkin_split" / f"{city}_val.csv")
            history_df = pd.concat([train_df, valid_df], ignore_index=True)
            history_df.sort_values(["user_id", "start_day", "start_min"], inplace=True)
            with open(city_file, "rb") as handle:
                test_rows = pickle.load(handle)
            selected = self.random.sample(test_rows, min(len(test_rows), 2))
            for sample in selected:
                user_id = int(sample["user_X"])
                user_history = history_df[history_df["user_id"] == user_id].tail(40)
                historical_data = [
                    (self._minutes_to_clock(int(row["start_min"])), row["week_day"], int(row["location_id"]))
                    for _, row in user_history.iterrows()
                ]
                context_stay = [
                    (self._minutes_to_clock(int(start_min)), weekday, int(location_id))
                    for start_min, weekday, location_id in zip(
                        sample["start_min_X"], sample["weekday_X"], sample["X"]
                    )
                ]
                target_stay = (
                    self._minutes_to_clock(int(sample["start_min_Y"])),
                    str(sample["weekday_Y"]),
                    None,
                )
                rows.append({
                    "task_type": "mobility_prediction",
                    "data_type": "trajectory",
                    "historical_data": historical_data,
                    "context_stay": context_stay,
                    "target_stay": target_stay,
                    "ground_truth": int(sample["Y"]),
                    "city": city,
                })
        return self._sample_rows(rows, n)

    def traffic_signal_proxy_tasks(self, n: int) -> List[Dict[str, Any]]:
        cities = [path.stem.replace("_img_indicators", "") for path in self.remote_root.glob("*_img_indicators.csv")]
        phases = ["north_south", "east_west", "left_turn", "pedestrian_scramble"]
        rows: List[Dict[str, Any]] = []
        for city in sorted(cities):
            for offset in range(2):
                base = abs(hash((city, offset))) % 9 + 2
                queue_lengths = {
                    phases[0]: base + 3,
                    phases[1]: base - 1,
                    phases[2]: base + (offset % 3),
                    phases[3]: base - 2,
                }
                selected_phase = max(queue_lengths.items(), key=lambda item: item[1])[0]
                task = TRAFFIC_ADAPTER.build_task_from_queue_lengths(city=city, queue_lengths=queue_lengths)
                task.update({
                    "ground_truth": selected_phase,
                    "ground_truth_option": TRAFFIC_ADAPTER.pick_default_option(task),
                    "is_proxy": True,
                })
                rows.append(task)
        return self._sample_rows(rows, n)

    def navigation_tasks(self, n: int) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for jsonl_file in sorted(self.navigation_root.glob("*_navigation_instructions_validate.jsonl")):
            city = jsonl_file.stem.replace("_navigation_instructions_validate", "")
            for line in jsonl_file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                steps = record.get("steps", [])
                if not steps:
                    continue
                rows.append({
                    "task_type": "outdoor_navigation",
                    "data_type": "text",
                    "steps": steps,
                    "start": f"{city} route start",
                    "end": f"{city} route destination",
                    "ground_truth": [step.get("action", "") for step in steps],
                    "city": city,
                })
        return self._sample_rows(rows, n)

    def exploration_tasks(self, n: int) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for csv_file in sorted(self.exploration_root.glob("case_*.csv")):
            city = csv_file.stem.replace("case_", "")
            df = pd.read_csv(csv_file)
            grouped = df.groupby("start_name")
            for start_name, group in grouped:
                if len(group) < 3:
                    continue
                sampled = group.sort_values(["completion", "average_step", "success_time"], ascending=[False, True, True]).head(3)
                candidates = []
                for option, (_, row) in zip(["A", "B", "C"], sampled.iterrows()):
                    candidates.append({
                        "option": option,
                        "des_name": row["des_name"],
                        "completion": float(row["completion"]),
                        "average_step": float(row["average_step"]),
                        "success_time": float(row["success_time"]),
                    })
                best = max(candidates, key=lambda item: (item["completion"], -item["average_step"], -item["success_time"]))
                rows.append({
                    "task_type": "urban_exploration",
                    "data_type": "text",
                    "question": f"From {start_name}, which destination is the best next exploration target?",
                    "candidates": candidates,
                    "ground_truth": best["option"],
                    "ground_truth_destination": best["des_name"],
                    "city": city,
                })
        return self._sample_rows(rows, n)

    def build_suite(self, n: int) -> Dict[str, List[Dict[str, Any]]]:
        return {
            "population_prediction": self.population_tasks(n),
            "object_detection": self.object_detection_tasks(n),
            "geolocation": self.geolocation_tasks(n),
            "geoqa": self.geoqa_tasks(n),
            "mobility_prediction": self.mobility_tasks(n),
            "traffic_signal": self.traffic_signal_proxy_tasks(n),
            "outdoor_navigation": self.navigation_tasks(n),
            "urban_exploration": self.exploration_tasks(n),
        }

    def _numeric_choices(self, ground_truth: float) -> Dict[str, float]:
        base = max(1.0, ground_truth)
        values = [
            base * 0.5,
            base * 0.75,
            base,
            base * 1.25,
            base * 1.5,
        ]
        labels = ["A", "B", "C", "D", "E"]
        return {label: round(value, 2) for label, value in zip(labels, values)}

    def _minutes_to_clock(self, minutes: int) -> str:
        hour = (minutes // 60) % 24
        minute = minutes % 60
        period = "AM"
        display_hour = hour
        if hour == 0:
            display_hour = 12
        elif hour == 12:
            period = "PM"
            display_hour = 12
        elif hour > 12:
            display_hour = hour - 12
            period = "PM"
        return f"{display_hour:02d}:{minute:02d} {period}"


class QuickBenchmarkRunner:
    def __init__(self, suite: Dict[str, List[Dict[str, Any]]]):
        self.suite = suite

    async def run(self, label: str, agent: UrbanAgent) -> Dict[str, Any]:
        task_results: Dict[str, Any] = {}
        for task_type, tasks in self.suite.items():
            logger.info("Running %s for %s (%s tasks)", label, task_type, len(tasks))
            samples = []
            scores = []
            for index, task in enumerate(tasks, start=1):
                result = await agent.execute_task(task=task, task_type=task_type)
                score, detail = self.evaluate(task_type, task, result)
                scores.append(score)
                samples.append({
                    "index": index,
                    "task_meta": to_jsonable({key: value for key, value in task.items() if key not in {"historical_data", "context_stay", "steps"}}),
                    "result": to_jsonable(result),
                    "score": score,
                    "detail": to_jsonable(detail),
                })
            task_results[task_type] = {
                "count": len(tasks),
                "avg_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
                "samples": samples,
            }
        task_results["overall"] = {
            "avg_score": round(statistics.mean([
                value["avg_score"] for key, value in task_results.items() if key != "overall"
            ]), 4)
        }
        return {"label": label, "results": task_results}

    def evaluate(self, task_type: str, task: Dict[str, Any], result: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        action = result.get("action", {})
        if task_type == "population_prediction":
            predicted_option = action.get("selected_option")
            if predicted_option:
                score = 1.0 if predicted_option == task["ground_truth_option"] else 0.0
                return score, {"predicted_option": predicted_option, "ground_truth_option": task["ground_truth_option"]}
            predicted = action.get("numerical_answer")
            if predicted is None:
                return 0.0, {"error": "missing numerical prediction"}
            relative_error = abs(float(predicted) - float(task["ground_truth"])) / max(float(task["ground_truth"]), 1.0)
            return max(0.0, 1.0 - relative_error), {"predicted": predicted, "ground_truth": task["ground_truth"]}
        if task_type == "object_detection":
            predicted = {str(item).lower() for item in action.get("objects", [])}
            ground_truth = {str(item).lower() for item in task["ground_truth"]}
            if not predicted:
                return 0.0, {"predicted": [], "ground_truth": list(ground_truth)}
            precision = len(predicted & ground_truth) / len(predicted)
            recall = len(predicted & ground_truth) / len(ground_truth)
            if precision + recall == 0:
                return 0.0, {"predicted": list(predicted), "ground_truth": list(ground_truth)}
            f1 = 2 * precision * recall / (precision + recall)
            return round(f1, 4), {"predicted": list(predicted), "ground_truth": list(ground_truth)}
        if task_type == "geolocation":
            predicted = action.get("identified_city") or result.get("final_answer", "")
            return (1.0 if str(predicted).strip().lower() == str(task["ground_truth"]).strip().lower() else 0.0,
                    {"predicted": predicted, "ground_truth": task["ground_truth"]})
        if task_type == "geoqa":
            predicted = action.get("selected_option")
            if not predicted:
                predicted = self._extract_choice(result.get("final_answer", ""))
            return (1.0 if predicted == task["ground_truth"] else 0.0,
                    {"predicted": predicted, "ground_truth": task["ground_truth"]})
        if task_type == "mobility_prediction":
            predicted = action.get("predicted_location")
            try:
                predicted_value = int(predicted)
            except Exception:
                predicted_value = predicted
            return (1.0 if predicted_value == task["ground_truth"] else 0.0,
                    {"predicted": predicted_value, "ground_truth": task["ground_truth"]})
        if task_type == "traffic_signal":
            predicted_option = action.get("selected_option")
            predicted = action.get("selected_phase")
            return (1.0 if predicted == task["ground_truth"] else 0.0,
                    {
                        "predicted": predicted,
                        "ground_truth": task["ground_truth"],
                        "predicted_option": predicted_option,
                        "ground_truth_option": task.get("ground_truth_option"),
                        "proxy": True,
                    })
        if task_type == "outdoor_navigation":
            predicted = [str(item).lower() for item in action.get("route_actions", [])]
            ground_truth = [str(item).lower() for item in task["ground_truth"]]
            score = 1.0 if predicted == ground_truth else 0.0
            return score, {"predicted": predicted, "ground_truth": ground_truth}
        if task_type == "urban_exploration":
            predicted = action.get("selected_option")
            return (1.0 if predicted == task["ground_truth"] else 0.0,
                    {"predicted": predicted, "ground_truth": task["ground_truth"], "destination": action.get("selected_destination")})
        return 0.0, {"error": "unsupported task type"}

    def _extract_choice(self, text: str) -> Optional[str]:
        for letter in ["A", "B", "C", "D", "E"]:
            if f" {letter} " in f" {text.upper()} ":
                return letter
        return None


async def build_agent(provider: str, config: Dict[str, Any]) -> UrbanAgent:
    load_env_file()
    llm_client = None
    vlm_client = None
    try:
        if provider == "qwen":
            model_client = QwenClient()
        elif provider == "kimi":
            model_client = KimiClient(client_type="standard")
        else:
            raise ValueError(f"Unsupported provider: {provider}")
        llm_client = model_client
        vlm_client = model_client
        logger.info("%s client initialized for benchmark run", provider)
    except Exception as exc:
        logger.warning("%s client unavailable, falling back to heuristic-only mode: %s", provider, exc)
    return UrbanAgent(llm_client=llm_client, vlm_client=vlm_client, config=config)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["qwen", "kimi", "all"], default="all")
    parser.add_argument("--sample-count", type=int, default=SAMPLE_COUNT)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    sampler = CityDataQuickSampler(CITYDATA_ROOT, seed=RANDOM_SEED)
    suite = sampler.build_suite(args.sample_count)
    runner = QuickBenchmarkRunner(suite)

    providers = ["qwen", "kimi"] if args.provider == "all" else [args.provider]
    all_runs: List[Dict[str, Any]] = []
    summary_rows: Dict[str, Any] = {}

    for provider in providers:
        baseline_agent = await build_agent(provider, {
            "reasoning": {"mode": "legacy"},
            "action": {"tool_runtime": "legacy"},
        })
        enhanced_agent = await build_agent(provider, {
            "reasoning": {"mode": "enhanced"},
            "action": {"tool_runtime": "mcp"},
        })

        baseline = await runner.run(f"{provider}_baseline", baseline_agent)
        enhanced = await runner.run(f"{provider}_enhanced", enhanced_agent)
        all_runs.extend([baseline, enhanced])
        summary_rows[provider] = {
            "baseline_overall": baseline["results"]["overall"]["avg_score"],
            "enhanced_overall": enhanced["results"]["overall"]["avg_score"],
            "task_scores": {
                task_type: {
                    "baseline": baseline["results"][task_type]["avg_score"],
                    "enhanced": enhanced["results"][task_type]["avg_score"],
                }
                for task_type in suite.keys()
            }
        }

    summary = {
        "timestamp": datetime.now().isoformat(),
        "benchmark": "citydata_direct_quick",
        "sample_count_per_task": args.sample_count,
        "notes": [
            "GeoQA, population, mobility, exploration, navigation are run directly from CityData artifacts.",
            "Traffic signal uses a reusable adapter layer; this benchmark still runs in proxy mode unless CitySim state is wired in.",
        ],
        "runs": all_runs,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RESULTS_DIR / f"citydata_quick_benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "output_path": str(output_path),
        "providers": summary_rows,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())