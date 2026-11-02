# 种子清单（PAB-RD，2026-10-30 定稿）

## 结论

**3B 和 1.5B 用的种子都是 `0`。** 不是"各有一个不同的种子"，而是全部臂共享同一个 0——
`scripts/train_lora.py` 的 `--seed` 默认值为 0，而 `run_sizes.sh` / `run_rd_chain.sh` /
`run_lr_check.sh` / `run_7b.sh` 都没有传 `--seed`。

## 种子控制的四条随机链

| 环节 | 值 | 位置 |
|---|---|---|
| `torch.manual_seed` | **0** | `train_lora.py:114`（影响 LoRA dropout=0.05、CUDA 初始化） |
| `random.seed` | **0** | `train_lora.py:115` |
| 每轮 shuffle | `random.Random(0 + epoch)` | `train_lora.py:162`，独立的生成器，与上面两个互不影响 |
| 数据构建（PAB-RD） | **0** | `build_pab_rd.py:238,247` |
| 训练/验证/测试划分 | **0** | `make_splits_generic.py:12,19` |
| 评测生成 | **无种子** | `run_guard.py:102` 用 `do_sample=False` 贪心解码，因此**评测是确定性的**，改种子不影响已训模型的结果 |
| 聚类 bootstrap / 置换 | **0** | `final_stats.py:SEED = 0` |

所以换种子只会改变两件事：dropout 掩码、每轮样本顺序。评测数字的变化完全来自训练。

## 逐臂配置（3B 与 1.5B）

| tag | 模型 | epochs | bs×accum | max_len | lr | LoRA r/α | best epoch | val macro-F1 |
|---|---|---|---|---|---|---|---|---|
| `o1_rd_3b` | Qwen2.5-3B | 3 | 4×4 | 1024 | 2e-4 | 16/32 | **1** | 0.8897 |
| `o1_rd_3b_nt` | Qwen2.5-3B | 3 | 4×4 | 1024 | 2e-4 | 16/32 | **2** | 0.8444 |
| `o1_rd_15b` | Qwen2.5-1.5B | 4 | 2×8 | 1280 | 2e-4 | 16/32 | **1** | 0.8910 |
| `o1_rd_15b_nt` | Qwen2.5-1.5B | 4 | 2×8 | 1280 | 2e-4 | 16/32 | **4** | 0.8546 |
| `o1_rd_15b_lr4` | Qwen2.5-1.5B | 4 | 2×8 | 1280 | **1e-4** | 16/32 | **3** | 0.9024 |
| `o1_rd_15b_nt_lr4` | Qwen2.5-1.5B | 4 | 2×8 | 1280 | **1e-4** | 16/32 | **2** | 0.8472 |

（`_nt` = task-blind，prompt 中把用户请求替换为 `(not provided)`；其余完全同配置。）

可训练参数：3B 29.9M（0.96%）、1.5B 18.5M（1.18%）。

## 复现命令（3B task 臂为例）

```bash
cd /data/projects/guardrails
source ~/anaconda3/etc/profile.d/conda.sh && conda activate /data/conda/envs/guard
export HF_HUB_OFFLINE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

python scripts/train_lora.py \
  --data data/pab_rd.jsonl --splits data/pab_rd_splits.json \
  --split pab --style pab --model /data/hf_cache/qwen3b \
  --epochs 3 --bs 4 --accum 4 --max-len 1024 --lora-r 16 \
  --seed 0 --tag o1_rd_3b

python scripts/run_guard.py \
  --data data/pab_rd.jsonl --splits data/pab_rd_splits.json \
  --split '' --part test --style pab --model /data/hf_cache/qwen3b \
  --bs 12 --adapter guard/adapters/o1_rd_3b --tag o1_rd_3b
```

## 换种子跑重复实验

只改一个参数，其余保持不变：

```bash
--seed 1   # 然后 --tag o1_rd_3b_s1，评测也用同一个新 tag
```

注意三件事：

1. **`--tag` 必须一起换**，否则会覆盖 `guard/adapters/o1_rd_3b`。
2. **划分和数据集不要换种子**。`--split pab` 读的是固定的 `pab_rd_splits.json`（种子 0），
   如果重新生成划分，测试集就变了，跨种子的数字不可比。
3. 3B 的 best epoch 是第 1 轮（`o1_rd_3b`）和第 2 轮（`o1_rd_3b_nt`），说明 3B 在 lr=2e-4
   下**一轮就接近收敛、之后轻微过拟合**。跑多种子时若某些种子在第 1 轮就抖动，
   这个"按 val macro-F1 选 best epoch"的做法本身会引入选择偏差，应改为固定轮次或
   用嵌套验证。
