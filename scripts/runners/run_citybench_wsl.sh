#!/usr/bin/env bash
set -eo pipefail

PROJECT_ROOT="/mnt/d/GitHub_1/world_agent/urban-mobility-agent"
CITYBENCH_ROOT="$PROJECT_ROOT/paper4_urban_svgagent/third_party/CityBench-main"

if [[ ! -d "$CITYBENCH_ROOT" ]]; then
  echo "CityBench not found: $CITYBENCH_ROOT"
  exit 1
fi

cd "$PROJECT_ROOT"

if ! command -v conda >/dev/null 2>&1; then
  echo "conda not found in WSL. Please install Miniconda first."
  exit 1
fi

source "$(conda info --base)/etc/profile.d/conda.sh"

if ! conda env list | grep -q "urban-citybench-linux"; then
  conda create -n urban-citybench-linux python=3.10 -y
fi

conda activate urban-citybench-linux

echo "[1/6] Upgrading pip/setuptools/wheel..."
python -m pip install --upgrade pip setuptools wheel

# Avoid pip building GDAL from source (often fails due to toolchain/version mismatch).
# Install geospatial stack from conda-forge first, then install CityBench deps without pinned GDAL.
echo "[2/6] Checking geospatial stack in conda env..."
if ! conda list -n urban-citybench-linux | grep -Eq '^(gdal|geopandas|fiona|rasterio|shapely|pyproj)\s'; then
  echo "[2/6] Installing geospatial stack (this may take several minutes)..."
  conda install -n urban-citybench-linux -y -c conda-forge \
    gdal geopandas fiona rasterio shapely pyproj
else
  echo "[2/6] Geospatial stack already installed, skipping."
fi

if ! command -v g++ >/dev/null 2>&1; then
  echo "[3/6] Installing C/C++ compilers in conda env..."
  conda install -n urban-citybench-linux -y -c conda-forge compilers
else
  echo "[3/6] g++ found, skipping compiler install."
fi

echo "[4/6] Installing CityBench Python requirements..."
CITYBENCH_REQ_FILTERED="$(mktemp)"
grep -viE '^\s*GDAL(==|>=|<=|~=|>|<)' "$CITYBENCH_ROOT/requirements.txt" > "$CITYBENCH_REQ_FILTERED"
python -m pip install -r "$CITYBENCH_REQ_FILTERED"
python -m pip install pycitysim
rm -f "$CITYBENCH_REQ_FILTERED"

echo "[5/6] Installing project root requirements..."
python -m pip install -r "$PROJECT_ROOT/requirements.txt"

# Optional local hardcoded fallback (quick start).
# Fill these only on your private machine.
HARDCODED_QWEN_API_KEY=""
HARDCODED_QWEN_API_BASE="https://dashscope.aliyuncs.com/compatible-mode/v1"
HARDCODED_QWEN_MODEL="qwen-vl-plus"

export OPENAI_API_KEY="${OPENAI_API_KEY:-${QWEN_API_KEY:-${DASHSCOPE_API_KEY:-${HARDCODED_QWEN_API_KEY:-}}}}"
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-${QWEN_API_BASE:-${HARDCODED_QWEN_API_BASE:-https://dashscope.aliyuncs.com/compatible-mode/v1}}}"
export OPENAI_MODEL="${OPENAI_MODEL:-${QWEN_MODEL:-${HARDCODED_QWEN_MODEL:-qwen3-vl}}}"
export DASHSCOPE_API_KEY="${DASHSCOPE_API_KEY:-${QWEN_API_KEY:-${HARDCODED_QWEN_API_KEY:-}}}"

# By default, run tasks that do NOT require MongoDB.
# Override by setting CITYBENCH_TASKS in shell.
CITYBENCH_TASKS="${CITYBENCH_TASKS:-geoqa,mobility,population,objects,geoloc}"

echo "[6/6] Running CityBench benchmark..."
echo "Selected tasks: $CITYBENCH_TASKS"
python "$PROJECT_ROOT/paper4_urban_svgagent/run_citybench_benchmark.py" \
  --city Shanghai \
  --data-name mini \
  --text-model GPT4omini \
  --vision-model QwenVLPlus \
  --tasks "$CITYBENCH_TASKS" \
  --force

echo "Done. Summary file: $PROJECT_ROOT/paper4_urban_svgagent/outputs/citybench_run_summary.json"
