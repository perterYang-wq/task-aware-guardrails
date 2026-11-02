#!/bin/bash
# 端到端评测：7B agent + 可插拔 1.5B guard，跑 AgentDojo 真实攻击场景。
# 用法: bash scripts/e2e_guard.sh <SUITE> <ADAPTER|none> [INJECTIONS] [GPU_UTIL] \
#                                  [ONLY_TASKS] [SUFFIX] [REVIEW_POLICY block|allow] [MODE both|attack|utility]
set -u
SUITE="${1:?suite}"
ADAPTER="${2:-none}"
INJ="${3:-}"
UTIL="${4:-0.72}"
ONLY="${5:-}"
SUF="${6:-}"
REV="${7:-block}"
MODE="${8:-both}"
HARD="${9:-0}"
ROOT=/data/projects/guardrails
PY=/data/conda/envs/guard/bin/python
VPY=/data/conda/envs/vllm12/bin/python
M7=/data/hf_cache/qwen3b

[ -n "$INJ" ] && SUF="${SUF}_inj$(echo "$INJ" | sed 's/injection_task_//g; s/,/-/g')"
[ -n "$ONLY" ] && SUF="${SUF}_pre"
[ "$REV" = "allow" ] && SUF="${SUF}_revallow"
SAFE=$(echo "$ADAPTER" | tr ": " "--")
OUT="$ROOT/results/e2e/$SUITE/$SAFE$SUF"
LOG="$OUT.run.log"
mkdir -p "$OUT"

if ! curl -s --max-time 3 http://127.0.0.1:8000/v1/models | grep -q qwen3b; then
  echo "[vllm] starting ..."
  cd "$ROOT"
  HF_HUB_OFFLINE=1 setsid "$VPY" -m vllm.entrypoints.openai.api_server \
    --model "$M7" --served-model-name qwen3b --host 127.0.0.1 --port 8000 \
    --dtype float16 --max-model-len 12288 --gpu-memory-utilization "$UTIL" \
    > /tmp/vllm_e2e.log 2>&1 < /dev/null &
  for i in $(seq 1 90); do
    sleep 2
    curl -s --max-time 2 http://127.0.0.1:8000/v1/models | grep -q qwen3b && break
  done
  curl -s --max-time 3 http://127.0.0.1:8000/v1/models | grep -q qwen3b \
    || { echo "[vllm] FAILED, see /tmp/vllm_e2e.log"; exit 2; }
  echo "[vllm] ready"
fi

cd "$ROOT"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_ENDPOINT=https://hf-mirror.com
INJARG=""; [ -n "$INJ" ] && INJARG="--injections $INJ"
ONLYARG=""; [ -n "$ONLY" ] && ONLYARG="--only $ONLY"
echo "[run] suite=$SUITE adapter=$ADAPTER inj=${INJ:-all} only=${ONLY:-all} review=$REV mode=$MODE -> $OUT"
"$PY" scripts/ad_run3.py --suite "$SUITE" --mode "$MODE" $INJARG $ONLYARG \
  --base-url http://127.0.0.1:8000/v1 --model qwen3b \
  --logdir "$OUT/logs" --trace "$OUT/trace.jsonl" --scen-out "$OUT/scen.jsonl" \
  --guard-adapter "$ADAPTER" --guard-view full --review-policy "$REV" \
  $([ "$HARD" = "1" ] && echo "--hard-rule") --force \
  > "$LOG" 2>&1
rc=$?
echo "[done] rc=$rc scen=$(wc -l < "$OUT/scen.jsonl" 2>/dev/null || echo 0)"
