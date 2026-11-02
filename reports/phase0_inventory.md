# 阶段 0 · 项目盘点报告

> 生成时间：2026-11-01 20:25 · 机器可读清单：`runs/experiment_manifest.json`
> 原则：不假定任何文件名存在；所有数字来自实地读取，不引用历史描述。

---

## 0. 结论摘要

| 判定 | 内容 |
|---|---|
| **可直接复用** | 诊断集（2370 调用 / 159 攻击 / 五档视图）、PAB-RD 与 hardneg 数据、HB 与 HB-nT 两组 LoRA 权重、端到端执行器 `ad_run3.py`、评测脚本 `e2e_analyze.py` / `diag_metrics.py`、travel+slack 的 4 臂端到端轨迹（含环境状态） |
| **需要修改** | 训练记录缺代码/数据哈希（追溯缺口）；banking 没有端到端基线，只有离线契约评估 |
| **缺失** | banking 端到端（E0/E1/E2 都没有）；跨 agent 验证；Task-Shield 式 7B judge 基线；M0/M1 的分类器级混淆矩阵与分攻击类型分解 |

**阶段 0 判定：通过（有保留）。** 代码/数据/模型哈希齐全且模型全部可加载；
但**历史的 `377 次调用` 只有调用级记录、不含环境状态**，不能用于端到端安全结论——这一点直接影响阶段 1 的做法。

---

## 1. 环境

| 项 | 值 |
|---|---|
| 主机 | ubuntu-20721（`/data` 数据盘 98G，已用 45G，余 49G） |
| GPU | RTX 3090 24G，驱动 550.107.02，当前占用 **11 MiB**（空闲） |
| Python / Torch | 3.10.22 / 2.6.0+cu124（`torch.cuda.is_available()=True`） |
| transformers / peft | 5.20.2 / 0.21.2 |
| AgentDojo | 源码在 `repos/agentdojo`，套件版本 **v1.2.2**（`ad_run3.py` 与 `contract_v4.py` 一致） |
| 运行中进程 | **无**（无训练、无评分、无 vLLM） |

## 2. 目录结构与入口

```
/data/projects/guardrails
├── scripts/          135 个 .py/.sh（下文列入口）
├── guard/            核心库：schema.py（渲染/解析）、router.py（γ 分级）、metrics.py
│   └── adapters/     46 个 LoRA（p1_* 旧阶段 + o1_* + m2_* 本阶段 + m2_HBnt_s0 为 P2 新增）
├── data/             13 个数据集/划分
├── results/          冻结版产物（diag/ e2e/ m2/ train_*.json 等）
│   ├── p2/           P2 工作区（任务消融，独立目录）
│   └── frozen/       P1/M2 冻结快照与清单
├── reports/          12 份文档
├── runs/             历史 trace + 本次新建的输出目录
└── STATUS.md         工程日志（顶部已标冻结状态）
```

主要入口：

| 用途 | 脚本 | 说明 |
|---|---|---|
| 打诊断分 | `scripts/diag_score.py` | 支持 `--views`、`--no-task`、`GUARD_DIAG_DIR` |
| 算指标 | `scripts/diag_metrics.py` | 唯一指标口径，输出 `metrics.json` |
| 训练守卫 | `scripts/train_drift.py` | LoRA + SFT/偏好项，`--no-task` 为 P2 新增 |
| 端到端 | `scripts/ad_run3.py` | 接 AgentDojo，执行边界挂 guard，落 `scen.jsonl`（**含 security/utility/guard_hits**） |
| 端到端分析 | `scripts/e2e_analyze.py` | 攻击链、效用 2×2、行为、分层 |
| 规则/PG2 守卫 | `scripts/rule_guard.py`、`pg2_guard.py` | 外部基线 |

## 3. 遗留文件核对（任务书点名三项）

| 名称 | 是否存在 | 实际路径 | 真实内容 |
|---|---|---|---|
| `ad_ws2_trace.jsonl` | ✅ | `runs/ad_ws2_trace.jsonl` | **643** 条调用 / **362** 个 (task,injection) 组合 / 14 个 injection task / suite=workspace |
| `ad_bank2_trace.jsonl` | ✅ | `runs/ad_bank2_trace.jsonl` | **377** 条调用 / **160** 个组合 / **9** 个 injection task / **16** 个 user task / suite=banking |
| `contract_v4.py` | ✅ | `scripts/contract_v4.py` | banking **离线**契约判定（P1/P2/P3 三档），读 AgentDojo v1.2.2 环境 |

**与历史描述的两处不一致，必须纠正：**

1. **"31 个攻击场景"对不上。** 实际是 160 个 (user_task, injection_task) 组合，覆盖 9 个 injection task × 16 个 user task。`377` 这个调用数是对的。
2. **两份 trace 都没有环境状态字段。** 字段只有
   `step / tool / args / current_action / history / history_full / instruction / user_task / injection_task / suite / ts`，
   **没有** `security`、`utility`、`executed`。所以它们只能回答"模型提出了什么调用"，
   不能回答"调用是否真的执行、环境是否被改变、攻击是否成功"。

## 4. 哈希（节选，完整 135 代码 + 13 数据 + 46 权重见 manifest）

| 文件 | 行数 | sha256 前 12 |
|---|---|---|
| `data/pab_rd.jsonl` | 1219 | `9af72b7559f5` |
| `data/pab_rd_splits.json` | — | `1a1a6323ef42` |
| `data/hardneg_bal.jsonl` | 254 | `5477cce29090` |
| `data/hardneg_sm.jsonl` | 254 | `39ba3e021b0b` |
| `data/tsbench_unified.jsonl` | 7182 | `da015a442720` |
| `results/diag/metrics.json`（冻结） | — | `368ca97a62a8` |
| `results/diag/steps.jsonl`（冻结） | 2370 | `2c20b4b913f1` |

冻结快照：`frozen/P1M2_20261101/`（归档 sha256 `d6c570a2…72bbf1e`，清单 329 行已校验）。

## 5. 模型可加载性（实测，非声明）

| 模型 | 结果 | 细节 |
|---|---|---|
| `pg2-86m`（`/data/hf_cache/pg2-86m`） | ✅ | **278.8M** 参数（不是名字暗示的 86M），标签 `BENIGN/MALICIOUS`；样例句子判 MALICIOUS 概率 0.9952；加载 2.2 s |
| `qwen1.5b` 基座 | ✅ | qwen2 架构，1.544B 参数，词表 151665；加载 1.3 s |
| `m2_HB_s0`（LoRA） | ✅ | 加载 + 生成成功（输出 `(4) Response` 格式） |
| `m2_HBnt_s0`（LoRA，P2 新增） | ✅ | 加载 + 生成成功（输出 `(无输入)`） |

## 6. 可追溯性审计

| 项 | 状态 | 说明 |
|---|---|---|
| 训练记录是否记录超参 | ✅ | `results/train_*.json` 含 `args`（lr/bs/seed/data 路径）、`best_epoch`、`best_val_macro_f1`、`hist` |
| 训练记录是否记录**代码哈希** | ❌ | 无。代码改动后无法证明某结果由哪版脚本产生 |
| 训练记录是否记录**数据哈希** | ❌ | 无（只记路径） |
| 端到端轨迹是否含环境状态 | ✅ | `results/e2e/*/scen.jsonl` 含 `security`/`utility`/`n_executed`/`guard_hits`，可按场景回溯 |
| 端到端轨迹是否可复现 | ⚠️ | 温度=0 贪心，确定性抽检 3/4 场景逐字段复现，1 例差异（基线缓存日志），已在冻结文档标注 |

**处理**：P2 起每次训练/评分写入 `code_sha`（脚本自身哈希）与 `data_sha`。本阶段先在报告里记下缺口，不追溯修改冻结产物。

## 7. 关键历史数字的来源核实

| 数字 | 来源 | 核实结果 |
|---|---|---|
| PG2 val Macro-F1 **0.537** | `results/train_pg2_l2_s0.json`（best ep3） | ✅ 找到；另有 `full/lr2e-4/lr5e-4/policy` 四个变体，0.5463 / 0.5463 / 0.5463 / 0.5476 |
| "377 次调用" | `runs/ad_bank2_trace.jsonl` | ✅ 377 |
| "31 个攻击场景" | 无对应文件 | ❌ 实际 160 个组合 / 9 个 injection task |
| banking 端到端基线 | 期望在 `results/ad_v3/banking/scen_merged.jsonl` | ❌ 不存在；该目录只有 `contract_eval_v2.json` 与 `labels_banking_v2.jsonl`（离线） |

## 8. 新建输出目录（按任务书）

```
runs/phase0/            runs/dataset_audit/     runs/baseline/
runs/classifier/        runs/guard_tests/
runs/agent/{e0_baseline,e1_non_task_aware,e2_task_aware}/
runs/ablation/{a0_full,a1_without_task}/
reports/final_figures/
```

## 9. 阶段 0 判定与下一步

**通过（有保留）**：

- 代码、数据、权重哈希齐全；四个模型/适配器全部实测可加载；无残留进程；冻结产物哈希未变。
- 保留项：训练记录缺代码/数据哈希；banking 无端到端基线；两份旧 trace 无环境状态。

**对阶段 1 的三个直接约束：**

1. **不能拿 `ad_bank2_trace.jsonl` 当端到端安全证据**——它没有环境状态，只能做数据审计与离线统计。
2. **banking 必须真跑 E0 基线**（约 1 小时），否则"攻击是否成功"无从验证。
3. **M0/M1 已有现成模型**：`m2_HBnt_s0`（训练时无任务字段）就是任务书里的 M0/A1，
   `m2_HB_s0` 是 M1/A0，两者骨干、数据、预算、划分完全相同——这是本阶段最省力也最干净的一组对照。

**建议进入阶段 1**，先做数据审计（复用 `steps.jsonl` 与两份旧 trace），再跑 banking E0 基线。
