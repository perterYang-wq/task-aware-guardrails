#!/bin/bash
# 一条链跑完：诊断打分 -> 四臂训练 -> 新臂打分。单卡串行，避免 GPU 争抢。
# 日志: /data/projects/guardrails/results/chain.log
set -u
cd /data/projects/guardrails
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
PY=/data/conda/envs/guard/bin/python
L=/data/projects/guardrails/results/chain.log

say() { echo "[$(date +%H:%M:%S)] $*" >> "$L"; }

say "=== P1 诊断打分（现有 checkpoint）==="
"$PY" scripts/diag_score.py \
  --arms p1_15b_task_s0,p1_15b_task_s42,p1_15b_task_s123,p1_15b_nt_s0,p1_3b_task_s0 \
  --views none,last3,full,noinj --bs 32 --bs-3b 12 >> "$L" 2>&1
say "diag pass A rc=$?"
"$PY" scripts/diag_score.py --arms p1_15b_task_s0 --views last1 --bs 32 >> "$L" 2>&1
say "diag last1 rc=$?"

say "=== M1/M2 四臂训练 ==="
bash scripts/run_train_m2.sh 0 >> "$L" 2>&1
say "train rc=$?"

say "=== 新臂诊断打分 ==="
"$PY" scripts/diag_score.py --arms m2_S_s0,m2_H_s0,m2_HV_s0,m2_HP_s0 \
  --views none,last3,full,noinj --bs 32 >> "$L" 2>&1
say "diag pass B rc=$?"

say "CHAIN_DONE"
