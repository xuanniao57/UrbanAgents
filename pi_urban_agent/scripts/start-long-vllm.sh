#!/usr/bin/env bash
set -euo pipefail
ROOT=/root/autodl-tmp/urban_agent_eval
MODEL=$ROOT/cache_qwen35_27b/models--Qwen--Qwen3.5-27B-FP8/snapshots/97f5941bf617e31c5e237364a8602ce3f03a551a
export VLLM_USE_FLASHINFER_SAMPLER=0
export VLLM_CACHE_ROOT=$ROOT/vllm_cache
export HF_HUB_OFFLINE=1
export OMP_NUM_THREADS=4
exec "$ROOT/envs/urban-agent/bin/vllm" serve "$MODEL" \
  --host 127.0.0.1 --port 8000 --served-model-name Qwen3.5-27B-FP8 \
  --max-model-len 8192 --gpu-memory-utilization 0.90 --max-num-seqs 4 \
  --enable-auto-tool-choice --tool-call-parser qwen3_coder \
  --reasoning-parser qwen3 --language-model-only
