# Claim 与判据状态表（C1–C8）

> 状态取自 `runs/auto/state.json`；scope 与禁用表述由本表维护（`scripts/claim_table.py`）。

| # | claim | status | claim_scope（能说到哪） | 禁止表述 | 证据文件 |
|---|---|---|---|---|---|
| C1 | 载荷污染是可测量的因果量 | `done` | **仅 p1 系列（标准授权 SFT）**：dInj = −0.459 / −0.384 / −0.315（三 seed）、3B −0.509。m2_HB（本文 M1）的 dInj 是 **+0.233**，符号相反，不得混用。 | 「所有模型 dInj 为负」；「M1 的 dInj 为 −0.459」；「载荷一律让守卫更宽松」 | `results/diag/metrics.json`、`results/diag/offline_vs_online.json`、`reports/phase1_baseline_v2.md` |
| C2 | 任务感知降低端到端 ASR | `done` | 整体效果：banking 2/64→0（天花板，p=.50）；slack 6/105→0（p=.031）；travel 13/80→1（p=.0018）。只对这三个套件、这一套 agent 成立。 | 「跨套件泛化」；「未见套件」；「对任意 agent 成立」 | `reports/phase1_baseline_v2.md`、`reports/b10_ablation.md`、`reports/final_metrics.csv` |
| C3 | 相对 Task-Shield 的效用/延迟优势 | `done` | slack 42 攻击场景、同一 7B agent：ASR 0/42 vs 0/42；干净效用 66.7% vs 23.8%（McNemar 9:0, p=.0039）；延迟 251 vs 574 ms（0.44×）；显存 +4.1 GB。 | 「成本是 1/5」；「更便宜一个数量级」；「全面优于 Task-Shield」 | `reports/b3_tshield.md`、`reports/mcnemar_audit.md` |
| C4 | 干净效用不劣于基线 | `partial` | banking 持平 37.5%；slack 66.7% 高于基线 61.9%；travel 10% 低于基线 25%。只在 slack（in-distribution）成立。 | 「效用全面不低于基线」；「travel 上也保住效用」 | `reports/final_metrics.csv`、`reports/b10_ablation.md` |
| C5a | 0.5B 保留 86.5% 判别力 | `pass` | 离线 ACB 0.849 vs 0.981（=86.5%）；端到端 travel ASR 3/40 vs 1/40、干净误拦 21/99 vs 11/97（p=.081）。 | 「0.5B 与 1.5B 等效」；「参数量减半无代价」 | `reports/b5_lightweight.md`、`probes/mcnemar_audit.json` |
| C5b | CPU 单次 ≤1.5 s | `partial` | 仅 p50 达标（1.461 s）；mean 1.851 s、p95 4.182 s、max 7.468 s 均超标。 | 「CPU 可实时部署」；「交互级延迟」；「把 251 ms 当作 0.5B 的延迟」 | `results/classifier/latency_05b_cpu.json`、`reports/b5_lightweight.md` |
| C6 | 跨任务泛化的边界 | `done` | 任务级：travel seen 0/20 vs unseen 1/20（+5pp）。**不是**套件级：travel 有 50% 任务在配对训练集里，hardneg 对 travel 零覆盖。 | 「未见套件」；「跨套件泛化」；「OOD 套件上验证」 | `reports/correction_ood.md`、`reports/phase1_baseline_v2.md` |
| C7 | 自适应攻击与部署层补丁 | `main_model_not_passed_patch_mitigates` | 主模型 meta 3/20（未满足 ≤2/20）；补丁后 0/20，但 Fisher p=.231（n=20），显著性未建立；补丁只挡『参数来自不可信文本』。 | 「达标」；「显著改善」；「证明补丁有效」；「自适应攻击已解决」 | `reports/b6_adaptive.md`、`reports/posthoc_alignment.md`、`reports/mcnemar_audit.md` |
| C8 | DENY 归因与净增益（阶段五新增） | `done` | M1 的 26 条非载荷依赖 DENY 中 M0 覆盖 76.9%；M1 only 6 / M0 only 4 / 交集 20；6 条中 4 条受污染，稳健净增益 2；McNemar p=.754。结论：动作先验为主。 | 「任务信息带来净增益」；「76.5% 是授权推理」；「任务字段在写类上不可替代」 | `reports/deny_attribution.md`、`probes/net_gain_sets.json`、`reports/mcnemar_audit.md`、`reports/consistency_check.md` |

## 越界扫描（reports/*.md）

分两类：**旧文档**（早于 `correction_ood.md` 的更正，需加横幅）与**现行文档**（需改）。

### A. 旧文档（结论已被更正，需加 `SUPERSEDED` 横幅）

| 文件 | 行 | claim | 命中词 | 原文 |
|---|---|---|---|---|
| baselines_controls.md | 4 | C2 | 未见套件 | > travel = 未见套件 / slack = 训练套件）下评测。 |
| baselines_controls.md | 4 | C6 | 未见套件 | > travel = 未见套件 / slack = 训练套件）下评测。 |
| baselines_controls.md | 28 | C2 | 未见套件 | ## 二、外部基线：端到端（travel = 未见套件 / slack = 训练套件） |
| baselines_controls.md | 28 | C6 | 未见套件 | ## 二、外部基线：端到端（travel = 未见套件 / slack = 训练套件） |
| e2e_ablation.md | 4 | C2 | 未见套件 | > travel = 未见套件（20 任务 × injection_task_0/1），slack = **训练过的套件** |
| e2e_ablation.md | 4 | C6 | 未见套件 | > travel = 未见套件（20 任务 × injection_task_0/1），slack = **训练过的套件** |
| m2_ladder.md | 33 | C2 | 未见套件 | （ACB/CCB 为三套件汇总；travel 是**未见套件**，是唯一可作泛化结论的一列。 |
| m2_ladder.md | 33 | C6 | 未见套件 | （ACB/CCB 为三套件汇总；travel 是**未见套件**，是唯一可作泛化结论的一列。 |
| m2_ladder.md | 85 | C2 | 未见套件 | ## 端到端（travel = 未见套件） |
| m2_ladder.md | 85 | C6 | 未见套件 | ## 端到端（travel = 未见套件） |
| phase1_baseline_v2.md | 95 | C2 | 未见套件 | travel 未参与训练，ACB 0.918（full）是唯一可称"未见套件"的离线数字。 |
| phase1_baseline_v2.md | 95 | C6 | 未见套件 | travel 未参与训练，ACB 0.918（full）是唯一可称"未见套件"的离线数字。 |

处理建议：在这些文件顶部加一行 “⚠️ 本文早于 2026-11-01 的 `correction_ood.md`，travel 已由『未见套件』降级为『配对配方未见套件』；引用前先看更正。”

现行文档未命中（已按 claim 语境过滤，并豁免否定语境）。

## 初稿评估

`reports/paper_draft.md` 是 P0/P1 阶段的旧稿（英文，§1–§8 讲 benchmark 与分类器，§4 是 Method 而非本文的归因节），**不含 C1–C8**，不能直接沿用；需要按本表重写。 旧稿长度 36981 字符，§5 Results 讲 PRA/SPA（PAB 配对），与本文 e2e 指标不同源。

结论：**没有可直接沿用的正文初稿**；C1–C8 的表述以本表为准，写作时逐条对照 scope。

