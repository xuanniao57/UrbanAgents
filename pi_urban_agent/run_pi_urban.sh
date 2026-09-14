#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "$ROOT/.." && pwd)"
RUN_DIR="${URBAN_PI_RUN_DIR:-${1:-}}"
PROVIDER="${URBAN_PI_PROVIDER:-local-vllm}"
MODEL="${URBAN_PI_MODEL:-Qwen3-30B-A3B-FP8}"
export URBAN_CONTEXT_PROFILE="${URBAN_CONTEXT_PROFILE:-auto}"

if [[ -z "$RUN_DIR" ]]; then
  echo "Set URBAN_PI_RUN_DIR or pass the run directory as the first argument." >&2
  exit 2
fi

export URBAN_PI_RUN_DIR="$(realpath -m "$RUN_DIR")"
export URBAN_PI_REPOSITORY_ROOT="$REPOSITORY_ROOT"
export PI_CODING_AGENT_DIR="$ROOT/.pi-agent"
export VLLM_BASE_URL="${VLLM_BASE_URL:-http://127.0.0.1:8000/v1}"
export VLLM_API_KEY="${VLLM_API_KEY:-local-vllm}"

RUNTIME_CONFIG="$URBAN_PI_RUN_DIR/.pi-agent-runtime"
mkdir -p "$RUNTIME_CONFIG"
CONFIG_ARGS=(
  "$ROOT/scripts/materialize-model-config.ts"
  --source "$ROOT/.pi-agent/models.json"
  --out-dir "$RUNTIME_CONFIG"
  --provider "$PROVIDER"
  --model "$MODEL"
)
[[ -n "${URBAN_CONTEXT_WINDOW:-}" ]] && CONFIG_ARGS+=(--context-window "$URBAN_CONTEXT_WINDOW")
[[ -n "${URBAN_MAX_OUTPUT_TOKENS:-}" ]] && CONFIG_ARGS+=(--max-output-tokens "$URBAN_MAX_OUTPUT_TOKENS")
"$ROOT/node_modules/.bin/tsx" "${CONFIG_ARGS[@]}"
export PI_CODING_AGENT_DIR="$RUNTIME_CONFIG"

exec "$ROOT/node_modules/.bin/pi" \
  -e "$ROOT/.pi/extensions/urban-agent.ts" \
  --no-builtin-tools \
  --provider "$PROVIDER" \
  --model "$MODEL"
