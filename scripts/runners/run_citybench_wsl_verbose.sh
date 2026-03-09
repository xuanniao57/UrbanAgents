#!/usr/bin/env bash
set -eo pipefail

PROJECT_ROOT="/mnt/d/GitHub_1/world_agent/urban-mobility-agent"
CITYBENCH_ROOT="$PROJECT_ROOT/paper4_urban_svgagent/third_party/CityBench-main"
LOG_DIR="$PROJECT_ROOT/paper4_urban_svgagent/outputs/citybench_verbose_logs"

CITYBENCH_TASKS="${CITYBENCH_TASKS:-geoqa,mobility,population,objects,geoloc}"
CITY_NAME="${CITY_NAME:-Shanghai}"
DATA_NAME="${DATA_NAME:-mini}"
TEXT_MODEL="${TEXT_MODEL:-GPT4omini}"
VISION_MODEL="${VISION_MODEL:-QwenVLPlus}"

HARDCODED_QWEN_API_KEY=""
HARDCODED_QWEN_API_BASE="https://dashscope.aliyuncs.com/compatible-mode/v1"
HARDCODED_QWEN_MODEL="qwen-vl-plus"

if [[ ! -d "$CITYBENCH_ROOT" ]]; then
  echo "CityBench not found: $CITYBENCH_ROOT"
  exit 1
fi

mkdir -p "$LOG_DIR"
RUN_TS="$(date +%Y%m%d_%H%M%S)"
RUN_LOG="$LOG_DIR/run_${RUN_TS}.log"

cd "$PROJECT_ROOT"

if ! command -v conda >/dev/null 2>&1; then
  echo "conda not found in WSL. Please install Miniconda first."
  exit 1
fi

source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate urban-citybench-linux

export OPENAI_API_KEY="${OPENAI_API_KEY:-${QWEN_API_KEY:-${DASHSCOPE_API_KEY:-${HARDCODED_QWEN_API_KEY:-}}}}"
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-${QWEN_API_BASE:-${HARDCODED_QWEN_API_BASE:-https://dashscope.aliyuncs.com/compatible-mode/v1}}}"
export OPENAI_MODEL="${OPENAI_MODEL:-${QWEN_MODEL:-${HARDCODED_QWEN_MODEL:-qwen-vl-plus}}}"
export DASHSCOPE_API_KEY="${DASHSCOPE_API_KEY:-${QWEN_API_KEY:-${HARDCODED_QWEN_API_KEY:-}}}"

KEY_LEN=0
if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  KEY_LEN=${#OPENAI_API_KEY}
fi

echo "========== CityBench Verbose Run ==========" | tee "$RUN_LOG"
echo "time: $(date '+%F %T')" | tee -a "$RUN_LOG"
echo "env: urban-citybench-linux" | tee -a "$RUN_LOG"
echo "city: $CITY_NAME | data: $DATA_NAME" | tee -a "$RUN_LOG"
echo "text_model: $TEXT_MODEL | vision_model: $VISION_MODEL" | tee -a "$RUN_LOG"
echo "OPENAI_BASE_URL: ${OPENAI_BASE_URL}" | tee -a "$RUN_LOG"
echo "OPENAI_MODEL: ${OPENAI_MODEL}" | tee -a "$RUN_LOG"
echo "OPENAI_API_KEY length: ${KEY_LEN}" | tee -a "$RUN_LOG"
echo "tasks: $CITYBENCH_TASKS" | tee -a "$RUN_LOG"
echo "===========================================" | tee -a "$RUN_LOG"

set -x
python "$PROJECT_ROOT/paper4_urban_svgagent/run_citybench_benchmark.py" \
  --city "$CITY_NAME" \
  --data-name "$DATA_NAME" \
  --text-model "$TEXT_MODEL" \
  --vision-model "$VISION_MODEL" \
  --tasks "$CITYBENCH_TASKS" \
  --force 2>&1 | tee -a "$RUN_LOG"
set +x

SUMMARY="$PROJECT_ROOT/paper4_urban_svgagent/outputs/citybench_run_summary.json"
if [[ -f "$SUMMARY" ]]; then
  echo "" | tee -a "$RUN_LOG"
  echo "========== Summary ==========" | tee -a "$RUN_LOG"
  cat "$SUMMARY" | tee -a "$RUN_LOG"
  echo "=============================" | tee -a "$RUN_LOG"

  python - <<'PY'
import json
from pathlib import Path
summary = Path('/mnt/d/GitHub_1/world_agent/urban-mobility-agent/paper4_urban_svgagent/outputs/citybench_run_summary.json')
if summary.exists():
    data = json.loads(summary.read_text(encoding='utf-8'))
    failed = [t for t in data.get('tasks', []) if t.get('status') != 'ok']
    print(f"failed_tasks={len(failed)}")
    for item in failed:
        print(f"- {item.get('task')} => {item.get('log')}")
PY

  echo "" | tee -a "$RUN_LOG"
  echo "Failed task log tails:" | tee -a "$RUN_LOG"
  python - <<'PY'
import json
from pathlib import Path
summary = Path('/mnt/d/GitHub_1/world_agent/urban-mobility-agent/paper4_urban_svgagent/outputs/citybench_run_summary.json')
if summary.exists():
    data = json.loads(summary.read_text(encoding='utf-8'))
    failed = [t for t in data.get('tasks', []) if t.get('status') != 'ok']
    for item in failed:
        log = Path(item.get('log', ''))
        print(f"\n--- {item.get('task')} | {log} ---")
        if log.exists():
            text = log.read_text(encoding='utf-8', errors='replace').splitlines()
            tail = text[-80:] if len(text) > 80 else text
            for line in tail:
                print(line)
        else:
            print('log file missing')
PY
fi

echo "Done. Verbose run log: $RUN_LOG"
