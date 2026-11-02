# 制图前置核对（只读，未修改任何既有文件）

> 任务：图表制作（不写正文）。执行时间 2026-11-02 23:30–23:55，机器 `/data/projects/guardrails`。
> 结论：**4 项全部通过**，可进入制图。逐项证据如下；发现的 3 处规格书与现实不符，列在末尾「差异」。

---

## 1. 图 1(b) 列名核对：PRA 与 ACB **未对反** ✅

从 `results/diag/offline_vs_online.json` 取 5 个同协议 checkpoint，重算三个极值对：

| arm | PRA（离线） | ACB_full（线上，%） | 规格书要求 | 判定 |
|---|---|---|---|---|
| `p1_3b_task_s0` | 0.8833 | 16.98 | 0.883 → 17.0% | 一致 |
| `p1_15b_task_s0` | 0.8556 | 21.38 | 0.856 → 21.4% | 一致 |
| `p1_15b_nt_s0` | 0.7944 | 41.51 | 0.794 → 41.5% | 一致 |

三重交叉验证，排除「两组数字恰好各自成立但列名互换」的可能：

1. **数值交叉**：`ACB_full` 与 `results/diag/metrics.json` 中对应 arm 的 `full.ACB`
   逐位相同（0.1698 / 0.2138 / 0.4151）。`metrics.json` 的 ACB 只可能来自线上判定，
   故 `ACB_full` 列确实是线上指标 —— 列名未反。
2. **方向交叉**：PRA 最高（0.8833）对应 ACB 最低（16.98），PRA 最低（0.7944）对应
   ACB 最高（41.51）。若两列被互换，三个极值对不可能同时成立。
3. **量纲交叉**：PRA ∈ [0.79, 0.89] 无量纲，ACB ∈ [17, 42] 带 `%`；
   `final_metrics.csv` 的 `fig1` 行把 PRA 与 ACB 分列存储，两者不共享分母。

→ 图 1(b) 轴标签：x = `Offline PRA`，y = `Online ACB (%)`。此结论在图脚本里由
`ft_common.py` 直接读 JSON 保证，无手工转录。

## 2. 机制复现包状态：**文件已产出，但不能并入图 6** ⚠️

核对时刻 23:52：`results/mechanism_probe_v41flash/aggregate.json` **不存在**（只有 `scenario_selection.json`）。
23:55–00:06 之间**另一个进程**（`results/auto_mech2.log`）把该包跑完并写出 `aggregate.json`（7.9 KB，00:06）；
`runs/auto/state.json` 于 00:09 被同一进程追加 `mechanism_probe_v41flash` 记录（**不是本任务改的**）。

包已存在，但**无法按任务书 §1.2 给图 6 加第 4 条骨干**，理由三条：

| # | 事实 | 影响 |
|---|---|---|
| a | `aggregate.json` 的组织维度是 **A/B/C/D 四个场景组 × E0/M1 两臂**（36 episodes），**没有 P0–P4 变体矩阵**；`model_probe*.json`、`thinking_probe.json`、`dsml_probe.json` 里也检索不到任何 `P0`/`variant` 字段 | 图 6 的格子是「变体 × seed」，该包一个格子都对不上，无值可填 |
| b | `model_requested = deepseek-v4.1-flash`，但 `model_used = model_returned = deepseek-flash` | 即使有矩阵，也不是规格书要求的骨干 |
| c | `summary`: 14 个攻击 episode 里 **E0 与 M1 的 attack success 都是 0**，且 `per_arm` 的 `attack_calls = 0`、`deny_total_M1 = 0` | agent 从未发出被注入的调用，守卫没被触发；这 0/14 是「模型不上钩」，不是「守卫挡住了」 |

→ 按任务书「数字对不上标 blocked」：图 6 保持 **3 seed × 5 变体（15 格）**，第 4 条骨干记
`blocked (not commensurable)`；表 5 同样不加列；表 6 的「加 1 行」无法构造（该包无 DENY 归因）。
manifest 记 `mech_probe: file present / matrix absent`。

## 3. 协议一致性 ✅

**图 4 的 E0 / S / M0 / M1 四点同属 slack 63 场景协议：**

| 点 | 运行目录 | scen 行数 | 其中受攻击 | 判定 |
|---|---|---|---|---|
| E0 | `results/ad_v3/slack/scen_merged.jsonl`（取 inj1+inj3 子集） | 126 → 子集 63 | 42 | ✅ 21/42 与 CSV 一致 |
| S | `results/e2e/slack/m2_S_s0_b10_inj1-3` | 63 | 42 | ✅ |
| M0 | `results/e2e/slack/m2_HBnt_s0_b1_inj1-3` | 63 | 42 | ✅ |
| M1 | `results/e2e/slack/m2_HB_s0_inj1-3` | 63 | 42 | ✅ |

> E0 的原始合并文件含 **105 个受攻击场景**（inj1–3 全集，即 claim_status 里的「105 场景协议」），
> 本表只用 inj1+inj3 的 42 个，由 `b9_metrics.py` 子集化；未与 105/139 场景的数字混用。

**表 1 三套件场景数与规格书一致：** banking 32 攻击 / 16 干净、slack 42 / 21、travel 40 / 20。
CSV 分母逐行核对通过（banking 8/32、slack 21/42、travel 13/40 于 E0 行）。

## 4. DO-NOT-QUOTE 已确认 ✅

- `reports/probe_user_task_4.md` 结尾确有「说明」块，**只对 seed123 成立、且与同文件表格矛盾**
  （表格里 seed0 在 P3/P4 判 DENY、seed42 在 P0/P2/P3 判 DENY）。
- 图 6 与表 5 **只从 `probes/probe_user_task_4.json` 重算**（raw 与 parsed 字段），
  未引用该文字块任何一句；图注、表注均未复述其结论。

---

## 差异（规格书与现实不符，已按「可核实优先」处理）

| # | 规格书说法 | 实测 | 处理 |
|---|---|---|---|
| D-1 | §5.1 #1：banking 误拦「无 `calls` 字段，无法重算」，正文不报该格 | `results/e2e/banking/m2_HB_s0_inj5-7/scen.jsonl` 的 16 个干净场景**有** `guard_hits`，共 29 次调用：M1 **0/29**、M0 **1/29** | 表中填实测值（表 1 第三列），并在表注写明 29 次调用的分母；未用 slack 分母代替 |
| D-2 | §5.3：结尾「三行」说明 | 实际是 **4 行**（P1/P2/P3/P4 各一句）+ 一行括号备注 | 一律按 DO-NOT-QUOTE 处理，不影响结论 |
| D-3 | 表 10 为「7 行」 | `b9_notes.md` §2 是 **8 行**：轴①拆成「训练侧 / 推理侧」两行 | 保留 8 行（不自作合并），表注说明 |
| D-4 | §1.2「存在 → 图 6 加第 4 列、表 6 加 1 行」 | 包存在，但只有 A/B/C/D × E0/M1 的场景级结果，无 P0–P4 矩阵，且未用 v4.1-flash | 图 6 不加列；表 6 不加行；记 blocked 并说明（见 §2） |

> D-1 是本轮唯一影响数字的差异。若坚持规格书口径，把表 1 第三列 banking 两格改回 `--` 即可，
> 但那样会漏报一份已经存在的测量。
