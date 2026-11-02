#!/bin/bash
# PAB-RD 上的第二个尺寸复现：1.5B 与 7B × 有/无任务
set -x
cd /data/projects/guardrails || exit 1
source ~/anaconda3/etc/profile.d/conda.sh
conda activate /data/conda/envs/guard
export HF_HUB_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

D=data/pab_rd.jsonl
S=data/pab_rd_splits.json

echo "=== 1.5B zero-shot ==="
python scripts/run_guard.py --data $D --splits $S --split '' --part test --style pab \
  --tag b3_rd_15b

echo "=== 7B zero-shot ==="
python scripts/run_guard.py --data $D --splits $S --split '' --part test --style pab \
  --model /home/linux/.cache/huggingface/hub/models--Qwen--Qwen2.5-7B-Instruct/snapshots/a09a35458c702b33eeacc393d103063234e8bc28 \
  --bs 8 --tag b3_rd_7b

echo "=== 1.5B LoRA (task) ==="
python scripts/train_lora.py --data $D --splits $S --split pab --style pab \
  --epochs 4 --bs 2 --accum 8 --max-len 1280 --tag o1_rd_15b
python scripts/run_guard.py --data $D --splits $S --split '' --part test --style pab \
  --adapter guard/adapters/o1_rd_15b --tag o1_rd_15b

echo "=== 1.5B LoRA (task-blind) ==="
python scripts/train_lora.py --data $D --splits $S --split pab --style pab \
  --epochs 4 --bs 2 --accum 8 --max-len 1280 --no-task --tag o1_rd_15b_nt
python scripts/run_guard.py --data $D --splits $S --split '' --part test --style pab \
  --no-task --adapter guard/adapters/o1_rd_15b_nt --tag o1_rd_15b_nt

echo "=== 7B LoRA (task) ==="
python scripts/train_lora.py --data $D --splits $S --split pab --style pab \
  --model /home/linux/.cache/huggingface/hub/models--Qwen--Qwen2.5-7B-Instruct/snapshots/a09a35458c702b33eeacc393d103063234e8bc28 \
  --epochs 3 --bs 4 --accum 4 --max-len 1280 --lora-r 16 --tag o1_rd_7b
python scripts/run_guard.py --data $D --splits $S --split '' --part test --style pab \
  --model /home/linux/.cache/huggingface/hub/models--Qwen--Qwen2.5-7B-Instruct/snapshots/a09a35458c702b33eeacc393d103063234e8bc28 \
  --bs 8 --adapter guard/adapters/o1_rd_7b --tag o1_rd_7b

echo "=== 7B LoRA (task-blind) ==="
python scripts/train_lora.py --data $D --splits $S --split pab --style pab \
  --model /home/linux/.cache/huggingface/hub/models--Qwen--Qwen2.5-7B-Instruct/snapshots/a09a35458c702b33eeacc393d103063234e8bc28 \
  --epochs 3 --bs 4 --accum 4 --max-len 1280 --lora-r 16 --no-task --tag o1_rd_7b_nt
python scripts/run_guard.py --data $D --splits $S --split '' --part test --style pab \
  --model /home/linux/.cache/huggingface/hub/models--Qwen--Qwen2.5-7B-Instruct/snapshots/a09a35458c702b33eeacc393d103063234e8bc28 \
  --bs 8 --no-task --adapter guard/adapters/o1_rd_7b_nt --tag o1_rd_7b_nt

echo "=== ALL DONE ==="
