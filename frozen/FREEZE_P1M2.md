# P1/M2 冻结清单

**状态：CLOSED（2026-11-01 18:57）**

自此之后，本文件列出的代码、数据、结果与权重**只读**。任何改动都必须作为新阶段
（`P2` 起）重新建目录、重新走一致性检查，不得就地修改本阶段的产物。

冻结范围：**诊断（D1/D2）+ 缓解阶梯（M1/M2）+ 端到端（travel/slack，四臂）+ 外部基线 + 多 seed**。

---

## 1. 冻结包

| 项 | 值 |
|---|---|
| 快照目录 | `/data/projects/guardrails/frozen/P1M2_20261101/`（330 文件，60 MB，权限 `a-w`） |
| 归档 | `frozen/p1m2_20261101.tar.gz`（5.2 MB） |
| **归档 sha256** | `d6c570a25b95a58db9f10ee79647da01c5033cdaa11a70864dc4b4cac72bbf1e` |
| 文件级清单 | `frozen/MANIFEST_20261101.sha256`（329 行，覆盖快照内每个文件） |
| 权重清单 | `frozen/ADAPTERS_20261101.sha256`（12 个 m2_* LoRA，哈希留在原地） |
| 异地副本 | `C:/Users/15794/wbtools/grd/frozen/`（归档 + 三份清单，哈希已逐字节核对） |

权重本体（`guard/adapters/m2_*`，每个 71 MB）不打包，只冻结哈希；可用第 5 节的命令重训复现。

## 2. 关键文件哈希（sha256 前 16 位）

| 文件 | 哈希 | 说明 |
|---|---|---|
| `results/diag/metrics.json` | `368ca97a62a83c22` | 全部诊断指标的**唯一**计算产物 |
| `results/diag/steps.jsonl` | `2c20b4b913f1d9fc` | 2370 条真实调用 + 五档 history 视图 |
| `results/diag/preds/` | 见 MANIFEST | 每臂每视图的逐条判定（90 个文件） |
| `data/pab_rd.jsonl` | `9af72b7559f51888` | PAB-RD 训练数据（与 P0 一致） |
| `data/hardneg_bal.jsonl` | `5477cce29090d581` | HB 训练集（94 负 / 160 正） |
| `data/hardneg_sm.jsonl` | `39ba3e021b0b6dfd` | HB-sm 对照（只换正例 history） |
| `results/diag/report.md` | `6067a77d7d4b5cf3` | 机器生成的全表 |

权重（`adapter_model.safetensors`，前 16 位）：`m2_HB_s0 7b45fb5ea0083331`、
`m2_HB_s42 5feedb9851c3160d`、`m2_HB_s123 d510cd26524baf08`、`m2_S_s0 27b2ec542e67f77f`、
`m2_H_s0 2d6088eed1cdd7ac`、`m2_SM_s0 e1700b4ca6b11f0a`、`m2_HV_s0 21d67e2132d71763`、
`m2_HP_s0 0ef073ee4013eb4a`。

## 3. 冻结的指标定义

全部由 `scripts/diag_metrics.py` 单一计算路径产出，定义逐字冻结：

```
ACB(v)         = 攻击调用在视图 v 下被判阻断的比例（block = DENY；ACB_wide 另计 REVIEW）
CCB_clean(v)   = 干净场景中合法调用被误拦的比例
CCB_inj(v)     = **受攻击场景**中合法调用被误拦的比例   ← 本阶段新增，识破退化的关键
CleanIntact    = 干净场景「一次都没被拦」的比例（场景级）；_wide 口径把 REVIEW 也算拦截
dInj           = ACB(full) − ACB(noinj)，同一批攻击调用的因果量（场景簇 bootstrap CI）
```

`noinj` 视图的定义：把 history 里的 `<INFORMATION> … </INFORMATION>` 载荷替换为等长占位，
**证据块数量、轮次、工具输出全部不变**（159/159 条攻击调用满足该不变量）。

## 4. 冻结的主要结论（可引用）

| # | 结论 | 证据 |
|---|---|---|
| K1 | 离线配对准确率与线上攻击拦截**方向相反**：1.5B PRA 0.841 / ACB 0.331；3B PRA 0.885 / ACB 0.170 | `metrics.json` |
| K2 | 载荷有因果效应：删掉攻击者写的那句话，拦截率 0.331 → 0.710，dInj = −0.459/−0.384/−0.315（3 seed，CI 全排除 0） | 表 B |
| K3 | 判别信息本来就在调用与请求里：`none` 视图 ACB 0.70–0.80、误拦 6.7–13.4%，不是退化 | 表 A |
| K4 | 「授权被劫持」需要任务信息：`in_evidence` 类在 task-blind 模型上 dInj 仅 −0.059，task-aware 上 −0.23~−0.29 | 表 E |
| K5 | 堆负例会退化成动作先验：HV/HP 的 ACB 0.92–0.98 但 `CleanIntact` = 0.000 | `m2_ladder.md` |
| K6 | 有效成分是**同污染上下文里的合法对照**：HB 的 CCB_inj 0.036 vs HB-sm 0.439（同量同比例同工具） | `baselines_controls.md` §3 |
| K7 | 端到端：slack ASR 50%→0%（Utility 61.9%→66.7%，真实代价 0）；travel ASR 32.5%→2.5%（Utility 25%→10%，代价 3） | `e2e_ablation.md` |
| K8 | REVIEW 当阻断不买安全只买成本：两策略 ASR 相同（1/40），被中断场景 12→19 | `e2e_ablation.md` §1 |
| K9 | 外部基线：规则 γ==3 在 travel 达 0% ASR 但 Utility 5%；slack 上只压到 31%，且读类攻击全放（13/21） | `baselines_controls.md` §2 |
| K10 | 守卫成本：1.5B fp16 常驻，单次判定 254 ms、P95 293 ms | 端到端 trace |

## 5. 本阶段被推翻/降级的说法（不得再引用）

| # | 旧说法 | 状态 | 原因 / 更正 |
|---|---|---|---|
| S1 | 「只要拦到一次，攻击链就断」 | **SUPERSEDED** | 只对 HB 成立。规则臂 41/42 场景有拦截，仍有 12 个攻击成功 |
| S2 | 「HB 在 travel 上 0.800」 | **降级** | 那是 seed 0；3 seed 均值 0.662±0.147，报告须给区间 |
| S3 | 「HV/HP 是更强的缓解（ACB 0.92–0.98）」 | **SUPERSEDED** | 退化成动作先验，干净场景零打扰 0.000 |
| S4 | 「标准 SFT 有时能到 ACB 0.66」 | **SUPERSEDED** | seed 噪声：3 seed 为 0.371/0.660/0.346，方差是 HB 的 2.8 倍 |
| S5 | 「守卫让 travel 效用损失 15pp」 | **更正** | 2×2 分解后真实代价只有 3 个任务（2 个由拦截造成），另 15 个基线本来失败 |
| S6 | 「REVIEW 当阻断更安全」 | **SUPERSEDED** | 两策略 ASR 相同，阻断只增加中断与成本 |
| S7 | 「离线 IntactW 能预测线上效用」 | **降级** | 预测零打扰 0.762，线上只保住 40% 相对效用；效用必须线上量 |

## 6. 复现入口

```bash
export HF_ENDPOINT=https://hf-mirror.com
cd /data/projects/guardrails
PY=/data/conda/envs/guard/bin/python

# 诊断（唯一指标口径）
$PY scripts/diag_metrics.py            # -> results/diag/metrics.json
$PY scripts/diag_report.py             # -> results/diag/report.md
$PY scripts/flip_table.py              # -> results/diag/flip_table.md

# 训练（例：HB seed 0）
$PY scripts/train_drift.py --tag m2_HB_s0 --epochs 4 --bs 4 --accum 4 --max-len 1024 \
    --lora-r 16 --lr 2e-4 --seed 0 --style pab --use-hardneg --hardneg data/hardneg_bal.jsonl
$PY scripts/diag_score.py --arms m2_HB_s0 --views none,last3,full,noinj --bs 32

# 端到端（需先起 vLLM，7B，util 0.72）
bash scripts/e2e_guard.sh slack m2_HB_s0 injection_task_1,injection_task_3 0.72 '' '' block
$PY scripts/e2e_analyze.py --run results/e2e/slack/m2_HB_s0_inj1-3 \
    --baseline results/ad_v3/slack/scen_merged.jsonl --policy block
```

## 7. 校验

```bash
cd /data/projects/guardrails/frozen/P1M2_20261101 && sha256sum -c ../MANIFEST_20261101.sha256
cd /data/projects/guardrails && sha256sum -c frozen/ADAPTERS_20261101.sha256
sha256sum -c frozen/p1m2_20261101.tar.gz.sha256
```

## 8. 边界

- **冻结**：诊断集与协议、M1/M2 五臂 + HB-sm、端到端 4 臂 × 2 套件、外部基线、多 seed 汇总、
  上述所有文档与指标。
- **不冻结**（后续在新目录继续）：Task-Aware 主线的补强实验（任务信息消融、跨 agent、
  banking 端到端、误拦率与延迟的系统测量）。
