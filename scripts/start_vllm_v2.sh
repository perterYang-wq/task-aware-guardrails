#!/bin/bash
# vLLM for AgentDojo workspace v2 — 修复上下文上限（12288 -> 16384）
# 注：PATH 用单引号，避免被本地 shell 展开污染（上一版曾被 Windows PATH 覆盖）
export HF_HUB_OFFLINE=1
export PATH="/usr/local/cuda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
MODEL=/home/linux/.cache/huggingface/hub/models--Qwen--Qwen2.5-7B-Instruct/snapshots/a09a35458c702b33eeacc393d103063234e8bc28
exec /data/conda/envs/vllm12/bin/vllm serve "$MODEL" \
  --served-model-name qwen7b \
  --max-model-len 20480 \
  --gpu-memory-utilization 0.85 \
  --dtype float16 \
  --port 8000 \
  --disable-log-requests
