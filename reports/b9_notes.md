# B9 说明：指标口径、六轴数字、重算清单

> 这份文件只做两件事：把指标定义钉死，把六根消融轴的数字与出处列全。
> 所有数字由 `scripts/b9_metrics.py` 落到 `reports/final_metrics.csv`，本文件不新增数字。

## 1. 指标口径

| 指标 | 定义 | 分母 | 来源字段 |
|---|---|---|---|
| ASR | 攻击目标达成的场景数 / 受攻击场景数 | 42（slack）/ 40（travel inj0-1）/ 32（banking） | `scen.jsonl::attack_success` |
| Utility | 原任务完成的干净场景数 / 干净场景数 | 21 / 20 / 16 | `scen.jsonl::utility` |
| 干净误拦截（调用级） | 干净场景里被判非 ALLOW 的调用 / 干净场景总调用 | 122~129 | `scen.jsonl::calls`+`n_blocked_calls` |
| 受攻击场景内合法调用误拦 | 受攻击场景里非攻击调用被拦 / 该场景合法调用数 | 197~214（slack） | 同上 |
| ACB | 攻击调用被判非 ALLOW 的比例（离线诊断集） | 159 攻击调用 | `results/*/diag/metrics.json` |
| CCB_inj | 受攻击**场景内**合法调用被误拦的比例（离线） | 见 metrics.json | 同上 |
| CCB_clean | 干净场景里的误拦比例（离线） | 2174 干净调用 | 同上 |
| dInj | ACB(full) − ACB(noinj)，场景簇 bootstrap 95%CI | 159 | `metrics.json::dInj` |
| PRA | 配对排序准确率（同工具、不同授权） | 90 配对（p1 协议） | `results/diag/offline_vs_online.json` |

> **ACB 一律用 wide 口径**（2370 条诊断集）除非另注；`results/diag` 与 `results/p2/diag`
> 对 `m2_HB_s0` 的 dInj 逐位一致（0.2327），故两文件可并表，CSV 的 `source` 列区分。

## 2. 消融轴（六根 + 阶段五新增的第七根）

| 轴 | 对比 | 数字 | 来源 |
|---|---|---|---|
| ① 任务字段（训练侧） | E0 / M0 / M1 | banking 8/32→0/32→0/32；slack 21/42→4/42→0/42；travel 13/40→6/40→1/40 | `final_metrics.csv::C2_task_aware` |
| ① 任务字段（推理侧） | full vs task 抹掉（E1） | ACB .918→.893，干净零打扰 .905→.619 | 冻结 P1M2 / `P2_ablation.md` |
| ② 历史长度 | none / last3 / full | ACB .560 / .837 / .918（M1） | `results/diag/metrics.json` |
| ③ 数据配方 | E0→S→M0→M1 | ASR 50.0→11.9→9.5→0.0；效用 61.9→47.6→33.3→66.7 | `final_metrics.csv::B10` |
| ④ 配对正例 | HB vs HB-sm | 离线 CCB_inj .036 vs .439；线上调用级 15.9% vs 62.4%；任务级相同 | `b10e_hbsm.md` |
| ⑤ 部署组件 | 纯硬规则 / M1 / M1+硬规则 | ASR 28.6 / 0 / 0；效用 4.8 / 66.7 / 4.8 | `final_metrics.csv::B10` |
| ⑥ 决策策略与检查范围 | 全查 / γ≥2 / γ≥3 | ACB .981/.818/.761；检查比例 100/27.0/23.6%；读类 .929/0/0 | `results/classifier/routing_ablation.json` |

| ⑦ 动作先验 vs 任务信息 | M1 only / M0 only | 6 / 4；交集 20；稳健净增益 2 | `probes/net_gain_sets.json` |

配套图：轴①③④⑤⑦见 `fig3/fig5`，轴②见 `fig2` 与上表，轴⑥见 `fig6`。

## 3. P1（去载荷）的效度

DENY 归因与 B6 的机制判断都依赖 P1。P1 只删 `<INFORMATION>` 原文块，删不掉 agent 的复述：

| 检查 | 结果 | 脚本 |
|---|---|---|
| P1 后残留载荷原文片段 | 1/34 | `scripts/p1_residual.py` |
| P1 后残留载荷里的邮箱 / URL | 17/34 | 同上 |
| 载荷专名被 agent 复述（token 召回 >0.5） | 6/34（其中 5 条属 P1-DENY） | 同上 |

所以凡是用 P1 得出的"不依赖载荷"，一律读作"**不依赖载荷原文块**"。

## 4. 重算清单（本次 B9 新增）

| 脚本 | 作用 | 产物 |
|---|---|---|
| `scripts/b9_metrics.py` | 从原始 scen/trace/metrics/probes 重算全部数字 | `reports/final_metrics.csv`（329 行） |
| `scripts/b9_figures.py` | 画六张图 + 图注索引 | `final_figures/*.png`、`reports/final_figures.md` |
| `scripts/b9_rule_latency.py` | 纯规则臂单次延迟（416 次调用） | `results/classifier/latency_rule_cpu.json` |
| `scripts/deny_attribution_m0.py` | M0 在同一 34 条 DENY 上的对照 | `probes/deny_attribution_m0*.json` |
| `scripts/p1_residual.py` | P1 的原文/实体/复述残留 | `probes/p1_residual.json` |

## 5. 阶段五新增（0 GPU 部分）

| 脚本 | 作用 | 产物 |
|---|---|---|
| `scripts/net_gain_sets.py` | M1 only / M0 only / 交集 / 稳健子集 | `probes/net_gain_sets.json` |
| `scripts/posthoc_auth.py` | 部署层工具授权检查（接在 ALLOW 之后） | — |
| `scripts/auth_sim.py` | 规则离线预检（三种作用域） | `probes/auth_sim.json` |
| `scripts/posthoc_analyze.py` | 补丁端到端评测 | `reports/posthoc_alignment.md` |

## 6. 已确认的既有产物

- `reports/phase3_integration.md`：阶段三集成总览，本轮未改动（数字与 `final_metrics.csv` 一致）。
- `reports/deny_attribution.md`：已并入 M0 对照与第 4 节改写。
- `reports/b6_adaptive.md`：机制结论已按 M0 证据修订。
- `reports/b10e_hbsm.md`、`reports/b5_lightweight.md`、`reports/b8_diagnosis.md`：未改动。
