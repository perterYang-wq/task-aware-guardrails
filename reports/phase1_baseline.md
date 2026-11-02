# 阶段 1 · 数据审计与基线

> 生成时间：2026-11-01 21:00 · 原始产物：`runs/dataset_audit/audit.json`、`runs/dataset_audit/scenario_manifest.jsonl`
> 规则：所有数字来自实地读取；未执行的一律标"未做"。

---

## 1. 审计对象

| 数据 | 路径 | 性质 |
|---|---|---|
| 诊断集（P1/M2 冻结） | `results/diag/steps.jsonl` | 2370 条真实调用，五档 history 视图 |
| 分类器训练/测试（P1 冻结） | `data/pab_rd.jsonl` + `data/pab_rd_splits.json` | 1219 条，train/val/test |
| 硬负例（P1/M2） | `data/hardneg_bal.jsonl` / `hardneg_sm.jsonl` | 254 条各 |
| 历史调用级 trace | `runs/ad_bank2_trace.jsonl`（377）、`runs/ad_ws2_trace.jsonl`（643） | **无环境状态** |
| 端到端轨迹（有环境状态） | `results/ad_v3/{slack,travel}/scen_merged.jsonl` | 含 `security`/`utility` |
| banking 端到端 | `results/e2e/banking/none_inj5-7/`（本次新建） | 含 `security`/`utility` |

## 2. 规模与类别分布

诊断集 2370 条，**三类标签**（此前只报过两类，这是本次审计的一个更正）：

| 标签 | 条数 | 占比 | 含义 |
|---|---|---|---|
| ALLOW | 2174 | 91.7% | 授权内的调用 |
| **DENY** | **159** | 6.7% | 攻击调用（越权且实际造成攻击效果） |
| **REVIEW** | **37** | 1.6% | **灰区：参数来自证据块但不在用户请求里**（全部在 travel，29 条 `in_evidence`） |

`REVIEW` 类此前没有单独报告，只在指标里被当作"既不算攻击也不算干净"排除在外。
它正是"授权边界"最有争议的一类，阶段 2 必须单独给混淆矩阵。

覆盖：**198 个场景（87 个含攻击调用）· 57 个任务 · 3 个套件**（banking 377 / travel 1069 / slack 924）。
五档视图中 `noinj`（删载荷）与 `full` 不同的有 1071 行。

## 3. 标签与行为一致性

| 检查 | 结果 |
|---|---|
| DENY 是否全部落在受攻击场景 | ✅ 159/159 |
| DENY 的 history 是否都含 `<INFORMATION>` 载荷 | ✅ 159/159 |
| 受攻击场景内的 ALLOW | 1906 条（合法调用，是 `CCB_inj` 的分母） |
| 干净场景内的 DENY | ✅ 0 条（无脏标签） |

## 4. 重复与近重复

| 口径 | 唯一值 | 说明 |
|---|---|---|
| `(tool, args, current_action)` | **397** | 同一动作在多个场景/多档 history 下重复出现，**按设计如此** |
| 再加 `instruction` | 640 | — |
| 跨标签冲突 | **5 组 / 25 行** | 全部是 `ALLOW` vs `REVIEW`：同一动作在干净场景判 ALLOW、在受攻击场景判 REVIEW |

**判定：不存在标签噪声。** 那 5 组冲突恰好是"同一个动作、不同上下文、不同授权结论"的正例，
说明标签确实依赖上下文而不是动作表面特征。

## 5. 数据泄漏审计

**分类器划分（PAB-RD）——干净：**

| 划分 | 条数 | 任务组数 |
|---|---|---|
| train | 764 | 63 |
| val | 120 | 9 |
| test | 335 | 25 |

任务组交集 train∩test = **0**，train∩val = **0**，`pair_id` 交集 = **0**。
满足"按攻击场景分组划分"的要求。

**诊断集（steps.jsonl）——in-distribution，必须分开报：**

hardneg 训练的 32 个任务**全部**出现在诊断集中（其中 24 个有攻击调用）。
所以：

- `ACB` 在 **banking / slack** 上是 in-distribution（任务见过）；
- `ACB` 在 **travel** 上是 out-of-distribution（套件未参与训练）；
- 论文里这两类必须分列，不能合并成一个"平均 ACB"。

## 6. 历史 trace 的能力边界（关键）

| 文件 | 调用 | 场景 | injection task | 有环境状态 | 能否判攻击成功 |
|---|---|---|---|---|---|
| `runs/ad_bank2_trace.jsonl` | 377 | 160 | 9 | ❌ | **不能** |
| `runs/ad_ws2_trace.jsonl` | 643 | 362 | 14 | ❌ | **不能** |

它们的字段只有 `step / tool / args / current_action / history / history_full / instruction /
user_task / injection_task / suite / ts`——**没有 `security`、`utility`、`executed`**。

结论：这两份 trace 只能用于离线统计与错误分析，**不能作为端到端安全结论的证据**。
任务书第 1 阶段"日志能否确定调用是否执行、环境是否改变"的答案是：**旧 trace 不能，新轨迹能**。

## 7. 现有端到端轨迹（含环境状态）

| 套件 | 场景 | 干净 / 受攻击 | 干净 Utility | ASR（全部注入） | 用途 |
|---|---|---|---|---|---|
| slack | 126 | 21 / 105 | 61.9% | 39.1% | in-distribution |
| travel | 159 | 20 / 139 | 25.0% | 18.7% | out-of-distribution |
| **banking（本次新建）** | **48** | **16 / 32** | **37.5%** | **25.0%** | 动机套件 |

注：早期报告里 travel 的 32.5% 是**只取 injection_task_0/1**（40 个场景）时的数字；
全量 139 个攻击场景的 ASR 是 18.7%。两个数都对，但分母不同，正式表必须写清楚。

## 8. 统一测试场景清单

已生成 `runs/dataset_audit/scenario_manifest.jsonl`（198 行），字段：
`suite / task / injection_task / scenario_id / n_calls / n_attack_calls`。
后续所有实验以此为场景级索引。

## 9. 基线实验（E0）

**执行**：`bash scripts/e2e_guard.sh banking none injection_task_5,injection_task_7 0.72 '' '' block`
（AgentDojo v1.2.2 banking 模拟环境，无真实账户/支付；温度 0；每场景重置环境）

| 指标 | 值 |
|---|---|
| 场景 | 48（16 干净 + 32 受攻击） |
| 干净任务完成率 | **37.5%（6/16）** |
| 攻击成功率 ASR | **25.0%（8/32）** |
| 受攻击场景下原任务完成率 | 40.6%（13/32） |
| 分注入类型 | `injection_task_5`（转钱给攻击者）4/16＝25%；`injection_task_7`（改密码）4/16＝25% |
| 干净场景失败原因 | 1 例 `no_tool_call`，其余为任务未完成（非崩溃） |
| 平均步数 | 干净 1.8 / 受攻击 2.3 |

产物：`results/e2e/banking/none_inj5-7/scen.jsonl`（含 `security`、`utility`、`n_executed`、`guard_hits`）。

## 10. 阶段 1 判定

**通过。** 基线结果由实际执行日志与环境状态验证，可追溯、可重跑。

**同时确认了三条限制**（写入后续所有报告）：

1. `REVIEW` 是第三类标签（37 条），此前被隐式排除，阶段 2 要单独报。
2. 诊断集对 banking/slack 是 in-distribution；泛化只能用 travel。
3. 旧 trace 无环境状态，不能替代端到端实验。

**进行中**：banking 的 M0（`m2_HBnt_s0`，训练时无任务字段）与 M1（`m2_HB_s0`）两臂
正在同一协议下运行，结果将并入阶段 2/4。
