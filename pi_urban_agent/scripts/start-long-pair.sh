#!/usr/bin/env bash
set -euo pipefail
ROOT=${1:-/root/urban-long-20260831/paper4_urban_svgagent/pi_urban_agent}
RUN_ID=${2:-long27_20260831}
export PATH=/root/urban-agent-runtime/node/bin:$PATH
export URBAN_PI_PYTHON=/root/autodl-tmp/urban_agent_eval/envs/urban-agent/bin/python
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
cd "$ROOT"
nohup node --import tsx scripts/long-workflow-session.ts --out "$ROOT/evaluation/$RUN_ID/A" --condition urban_full --data-root "$ROOT/long_case/data" --model Qwen3.5-27B-FP8 --base-url http://127.0.0.1:8000/v1 --window 8192 --output-tokens 2048 > "$ROOT/evaluation/$RUN_ID/A_runner.log" 2>&1 < /dev/null &
nohup node --import tsx scripts/long-workflow-session.ts --out "$ROOT/evaluation/$RUN_ID/B" --condition pi_default_compaction --data-root "$ROOT/long_case/data" --model Qwen3.5-27B-FP8 --base-url http://127.0.0.1:8000/v1 --window 8192 --output-tokens 2048 > "$ROOT/evaluation/$RUN_ID/B_runner.log" 2>&1 < /dev/null &
echo "Two fresh sessions launched; waiting for human input."
