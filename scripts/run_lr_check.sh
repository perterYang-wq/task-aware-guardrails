#!/bin/bash
# 1.5B 异常核查：aware 臂第 1 轮就到峰值后下降，怀疑 lr 过大。
# 两臂同时用 lr=1e-4 重训，保证比较公平。
set -x
cd /data/projects/guardrails || exit 1
source ~/anaconda3/etc/profile.d/conda.sh
conda activate /data/conda/envs/guard
export HF_HUB_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
D=data/pab_rd.jsonl
S=data/pab_rd_splits.json
M=/data/hf_cache/qwen1.5b

echo "=== 1.5B lr=1e-4 (task) ==="
python scripts/train_lora.py --data $D --splits $S --split pab --style pab --model $M \
  --epochs 4 --bs 2 --accum 8 --max-len 1280 --lr 1e-4 --tag o1_rd_15b_lr4
python scripts/run_guard.py --data $D --splits $S --split '' --part test --style pab \
  --model $M --adapter guard/adapters/o1_rd_15b_lr4 --tag o1_rd_15b_lr4

echo "=== 1.5B lr=1e-4 (task-blind) ==="
python scripts/train_lora.py --data $D --splits $S --split pab --style pab --model $M \
  --epochs 4 --bs 2 --accum 8 --max-len 1280 --lr 1e-4 --no-task --tag o1_rd_15b_nt_lr4
python scripts/run_guard.py --data $D --splits $S --split '' --part test --style pab \
  --model $M --no-task --adapter guard/adapters/o1_rd_15b_nt_lr4 --tag o1_rd_15b_nt_lr4

echo "=== LR_CHECK_DONE ==="
