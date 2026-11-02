#!/bin/bash
# PAB-RD 上的尺寸阶梯：3B 先跑，跑完再跑 0.5B（各含 task / task-blind）
set -x
cd /data/projects/guardrails || exit 1
source ~/anaconda3/etc/profile.d/conda.sh
conda activate /data/conda/envs/guard
export HF_HUB_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

D=data/pab_rd.jsonl
S=data/pab_rd_splits.json

echo "############ 3B ############"
M3=/data/hf_cache/qwen3b
python scripts/run_guard.py --data $D --splits $S --split '' --part test --style pab \
  --model $M3 --bs 12 --tag b3_rd_3b

echo "=== 3B LoRA (task) ==="
python scripts/train_lora.py --data $D --splits $S --split pab --style pab --model $M3 \
  --epochs 3 --bs 4 --accum 4 --max-len 1024 --lora-r 16 --tag o1_rd_3b
python scripts/run_guard.py --data $D --splits $S --split '' --part test --style pab \
  --model $M3 --bs 12 --adapter guard/adapters/o1_rd_3b --tag o1_rd_3b

echo "=== 3B LoRA (task-blind) ==="
python scripts/train_lora.py --data $D --splits $S --split pab --style pab --model $M3 \
  --epochs 3 --bs 4 --accum 4 --max-len 1024 --lora-r 16 --no-task --tag o1_rd_3b_nt
python scripts/run_guard.py --data $D --splits $S --split '' --part test --style pab \
  --model $M3 --bs 12 --no-task --adapter guard/adapters/o1_rd_3b_nt --tag o1_rd_3b_nt

echo "############ 0.5B ############"
M05=/data/hf_cache/qwen0.5b
python scripts/run_guard.py --data $D --splits $S --split '' --part test --style pab \
  --model $M05 --bs 16 --tag b3_rd_05b

echo "=== 0.5B LoRA (task) ==="
python scripts/train_lora.py --data $D --splits $S --split pab --style pab --model $M05 \
  --epochs 4 --bs 8 --accum 2 --max-len 1024 --lora-r 16 --tag o1_rd_05b
python scripts/run_guard.py --data $D --splits $S --split '' --part test --style pab \
  --model $M05 --bs 16 --adapter guard/adapters/o1_rd_05b --tag o1_rd_05b

echo "=== 0.5B LoRA (task-blind) ==="
python scripts/train_lora.py --data $D --splits $S --split pab --style pab --model $M05 \
  --epochs 4 --bs 8 --accum 2 --max-len 1024 --lora-r 16 --no-task --tag o1_rd_05b_nt
python scripts/run_guard.py --data $D --splits $S --split '' --part test --style pab \
  --model $M05 --bs 16 --no-task --adapter guard/adapters/o1_rd_05b_nt --tag o1_rd_05b_nt

echo "=== SIZE_LADDER_DONE ==="
