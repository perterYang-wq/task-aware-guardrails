#!/bin/bash
# 后续自动化：确定性校验 -> slack 端到端 -> HB 两个 seed 训练与离线评分
set -u
cd /data/projects/guardrails
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
PY=/data/conda/envs/guard/bin/python
L=/data/projects/guardrails/results/chain4.log
say() { echo "[$(date +%H:%M:%S)] $*" >> "$L"; }

# 0) 等 REVALLOW 跑完
say "等 revallow 结束"
for i in $(seq 1 420); do
  pgrep -f 'scripts/ad_run3.py' > /dev/null || break
  sleep 15
done
say "revallow 结束"

# 1) 确定性校验：无守卫重跑 2 个任务，与基线逐场景比对
say "确定性校验开始"
rm -rf results/e2e/_det
"$PY" scripts/ad_run3.py --suite travel --mode both --only user_task_0,user_task_1 \
  --injections injection_task_0 --base-url http://127.0.0.1:8000/v1 --model qwen7b \
  --logdir results/e2e/_det/logs --trace results/e2e/_det/t.jsonl \
  --scen-out results/e2e/_det/s.jsonl --guard-adapter none --force >> "$L" 2>&1
"$PY" scripts/e2e_determinism.py --run results/e2e/_det/scen.jsonl \
  --baseline results/ad_v3/travel/scen_merged.jsonl >> "$L" 2>&1
say "确定性校验 rc=$?"

# 2) slack 端到端（in-distribution，基线效用 61.9%）
say "slack 端到端开始"
bash scripts/e2e_guard.sh slack m2_HB_s0 injection_task_1,injection_task_3 0.72 '' '' block >> "$L" 2>&1
say "slack 端到端 rc=$?"
"$PY" scripts/e2e_analyze.py --run results/e2e/slack/m2_HB_s0_inj1-3 \
  --baseline results/ad_v3/slack/scen_merged.jsonl --policy block >> "$L" 2>&1
say "slack 分析 rc=$?"

# 3) 关掉 vLLM，腾出显存训练两个 seed
pkill -f 'vllm.entrypoints' || true
sleep 10
for S in 42 123; do
  say "训练 HB seed=$S"
  "$PY" scripts/train_drift.py --tag "m2_HB_s$S" --epochs 4 --bs 4 --accum 4 \
    --max-len 1024 --lora-r 16 --lr 2e-4 --seed "$S" --style pab \
    --use-hardneg --hardneg data/hardneg_bal.jsonl >> "$L" 2>&1
  say "HB seed=$S rc=$?"
done
"$PY" scripts/diag_score.py --arms m2_HB_s42,m2_HB_s123 --views none,last3,full,noinj \
  --bs 32 >> "$L" 2>&1
say "seed 评分 rc=$?"
say "CHAIN4_DONE"
