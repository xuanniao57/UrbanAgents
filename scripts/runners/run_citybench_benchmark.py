import argparse
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from urllib.request import urlretrieve
import platform

from dotenv import load_dotenv


CITYDATA_URL = "https://huggingface.co/datasets/Tianhui-Liu/CityBench-CityData/resolve/main/citydata.zip?download=true"


def run_cmd(args, cwd, env, log_path):
    start = time.time()
    proc = subprocess.run(
        args,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    elapsed = time.time() - start
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(proc.stdout, encoding="utf-8")
    return proc.returncode, elapsed


def ensure_citydata(citybench_root: Path):
    citydata_dir = citybench_root / "citydata"
    if citydata_dir.exists():
        return

    zip_path = citybench_root / "citydata.zip"
    for attempt in range(1, 4):
        try:
            print(f"[citydata] downloading attempt {attempt}/3 ...")
            urlretrieve(CITYDATA_URL, str(zip_path))
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(citybench_root)
            if not citydata_dir.exists():
                raise RuntimeError("citydata folder not found after unzip")
            print("[citydata] ready")
            return
        except Exception as exc:
            print(f"[citydata] download failed: {exc}")
            if attempt == 3:
                raise
            time.sleep(5)


def prepare_env(workspace_root: Path):
    env = os.environ.copy()
    load_dotenv(workspace_root / ".env")
    load_dotenv(override=False)

    qwen_key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    qwen_base = os.getenv("QWEN_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    qwen_model = os.getenv("QWEN_MODEL", "qwen-vl-plus")

    if qwen_key and not os.getenv("DASHSCOPE_API_KEY"):
        env["DASHSCOPE_API_KEY"] = qwen_key

    if qwen_key and not os.getenv("OpenAI_API_KEY"):
        env["OpenAI_API_KEY"] = qwen_key
    if qwen_base and not os.getenv("OPENAI_BASE_URL"):
        env["OPENAI_BASE_URL"] = qwen_base
    if qwen_model and not os.getenv("OPENAI_MODEL"):
        env["OPENAI_MODEL"] = qwen_model

    for key in [
        "OpenAI_API_KEY",
        "DASHSCOPE_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "QWEN_MODEL",
        "QWEN_API_BASE",
    ]:
        if key in os.environ:
            env[key] = os.environ[key]

    return env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", default="Shanghai")
    parser.add_argument("--data-name", default="mini", choices=["mini", "all"])
    parser.add_argument("--text-model", default="GPT4omini")
    parser.add_argument("--vision-model", default="QwenVLPlus")
    parser.add_argument("--tasks", default="traffic,geoqa,mobility,exploration,population,objects,geoloc,navigation")
    parser.add_argument("--skip-incompatible", action="store_true", default=True)
    parser.add_argument("--workspace", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--citybench-dir", default=str(Path(__file__).resolve().parent / "third_party" / "CityBench-main"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    workspace_root = Path(args.workspace).resolve()
    citybench_root = Path(args.citybench_dir).resolve()

    if not citybench_root.exists():
        raise FileNotFoundError(f"CityBench not found: {citybench_root}")

    ensure_citydata(citybench_root)
    env = prepare_env(workspace_root)

    results_root = citybench_root / "results"
    logs_root = workspace_root / "paper4_urban_svgagent" / "outputs" / "citybench_run_logs"
    logs_root.mkdir(parents=True, exist_ok=True)

    tasks = [
        {
            "name": "traffic",
            "cmd": [sys.executable, "-m", "citybench.traffic_signal.run_eval", "--city_name", args.city, "--model_name", args.text_model, "--data_name", args.data_name],
            "result": results_root / "signal_results" / f"{args.city}_results.json",
        },
        {
            "name": "geoqa",
            "cmd": [sys.executable, "-m", "citybench.geoqa.run_eval", "--city_name", args.city, "--model_name", args.text_model, "--data_name", args.data_name],
            "result": results_root / "geo_knowledge_result" / f"geoqa_{args.city}_{args.text_model}.csv",
        },
        {
            "name": "mobility",
            "cmd": [sys.executable, "-m", "citybench.mobility_prediction.run_eval", "--city_name", args.city, "--model_name", args.text_model, "--data_name", args.data_name],
            "result": results_root / "prediction_results" / f"mobility_prediction_{args.city}_{args.text_model}.csv",
        },
        {
            "name": "exploration",
            "cmd": [sys.executable, "-m", "citybench.urban_exploration.eval", "--city_name", args.city, "--model_name", args.text_model, "--mode", "eval", "--data_name", args.data_name],
            "result": results_root / "exploration_results" / f"{args.city}_result.csv",
        },
        {
            "name": "population",
            "cmd": [sys.executable, "-m", "citybench.remote_sensing.eval_inference", "--city_name", args.city, "--model_name", args.vision_model, "--task_name", "population", "--data_name", args.data_name],
            "result": results_root / "remote_sensing" / f"{args.city}_{args.vision_model}_population.jsonl",
        },
        {
            "name": "objects",
            "cmd": [sys.executable, "-m", "citybench.remote_sensing.eval_inference", "--city_name", args.city, "--model_name", args.vision_model, "--task_name", "objects", "--data_name", args.data_name],
            "result": results_root / "remote_sensing" / f"{args.city}_{args.vision_model}_objects.jsonl",
        },
        {
            "name": "geoloc",
            "cmd": [sys.executable, "-m", "citybench.street_view.eval_inference", "--city_name", args.city, "--model_name", args.vision_model, "--task_name", "geoloc", "--data_name", args.data_name],
            "result": results_root / "street_view" / f"{args.city}_{args.vision_model}_geoloc.jsonl",
        },
        {
            "name": "navigation",
            "cmd": [sys.executable, "-m", "citybench.outdoor_navigation.eval", "--city_name", args.city, "--model_name", args.vision_model, "--mode", "eval", "--data_name", args.data_name],
            "result": results_root / "outdoor_navigation_results" / f"{args.city}_results.csv",
        },
    ]

    selected_tasks = [task.strip() for task in args.tasks.split(",") if task.strip()]
    tasks = [task for task in tasks if task["name"] in selected_tasks]

    if args.skip_incompatible and platform.system().lower().startswith("win"):
        incompatible = {"traffic", "exploration", "navigation"}
        tasks = [task for task in tasks if task["name"] not in incompatible]
        print(f"[info] Windows detected, skipped incompatible tasks: {sorted(incompatible)}")

    summary = {
        "city": args.city,
        "data_name": args.data_name,
        "text_model": args.text_model,
        "vision_model": args.vision_model,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tasks": [],
    }

    for task in tasks:
        log_path = logs_root / f"{task['name']}.log"
        if task["result"].exists() and not args.force:
            summary["tasks"].append({
                "task": task["name"],
                "status": "skipped",
                "reason": "result_exists",
                "result": str(task["result"]),
                "log": str(log_path),
            })
            print(f"[skip] {task['name']} (result exists)")
            continue

        print(f"[run] {task['name']}")
        code, elapsed = run_cmd(task["cmd"], citybench_root, env, log_path)
        status = "ok" if code == 0 else "failed"
        summary["tasks"].append({
            "task": task["name"],
            "status": status,
            "exit_code": code,
            "elapsed_sec": round(elapsed, 2),
            "result": str(task["result"]),
            "log": str(log_path),
        })
        print(f"[{status}] {task['name']} ({elapsed:.1f}s)")

    summary["ended_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    out_json = workspace_root / "paper4_urban_svgagent" / "outputs" / "citybench_run_summary.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"summary saved: {out_json}")


if __name__ == "__main__":
    main()
