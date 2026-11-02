# 新研究计划 · 本轮实验索引

> **P1/M2 已于 2026-11-01 18:57 冻结**（`FREEZE_P1M2.md`）。下表 1–7 属于**冻结版本**，
> 数字可引用；`RESEARCH_PLAN_P2.md` 指向新主线，其后的实验属 P2，产物写在 `results/p2/`。

按阅读顺序：

| # | 文件 | 内容 |
|---|---|---|
| 0 | `FREEZE_P1M2.md` | **冻结清单**：范围、哈希、可引用结论 K1–K10、被推翻说法 S1–S7、复现命令 |
| 0b | `RESEARCH_PLAN_P2.md` | **P2 主线**：定位与差异、三层证据地图、E1–E6 补实验（含成本） |
| 0c | `P2_ablation.md` | **P2 已完成**：E1 推理侧消融、E2 训练侧消融、三种退化↔三种指标 |
| 1 | `diag_protocol.md` | **诊断协议**：五档 history 视图、因果量 `dInj`、机制分解。定义「怎么量」 |
| 2 | `diag_findings.md` | **诊断结论**：错位量级、排序反转、四个 checkpoint 的因果效应、机制 2×2 |
| 3 | `m2_ladder.md` | **M1/M2 五臂**：H 有效但伤效用；HV/HP 退化成动作先验；HB 平衡后最优 |
| 4 | `baselines_controls.md` | **外部基线（规则 / PG2，离线 + travel/slack 端到端）+ 机制对照（HB-sm）+ 三 seed** |
| 5 | `e2e_ablation.md` | **端到端补充八项**：REVIEW 策略消融、攻击链、效用 2×2、in/out-of-distribution、配对检验、拦截后行为、强弱分层 |
| 6 | `results/diag/report.md` | 机器生成的全表（单一计算路径，勿手改） |
| 7 | `../STATUS.md` | 工程记录与踩坑 |

## 对应研究计划的实验编号

| 计划编号 | 状态 | 落在哪里 |
|---|---|---|
| D1 标准授权 SFT vs 无监督基线 | ✅ | `diag_findings.md` §1（含 3B 排序反转）；`p1_15b_nt_s0` 为无任务信息对照 |
| D2 History Ablation + Clean/Attacked 分离 | ✅ | `diag_protocol.md` §2、`diag_findings.md` §2–3（`none/last3/full/noinj` + `ACB/CCB` 分离） |
| D3 Cross-Agent / Cross-Suite | ◐ | 跨套件已完成（banking/slack/travel，含 in-dist slack 与 out-of-dist travel 的端到端）；**跨 agent 未做** |
| M1 意图漂移目标 vs 标准 SFT | ◐ | `m2_ladder.md` 的 HV/HP 两臂（退化）；有效替代是数据平衡 HB，见 `baselines_controls.md` §3 |
| M2 攻击轨迹 hard negative 的收益 | ✅ | H 臂（travel +38.5pp，零误拦）；HB 臂为平衡版 |
| M3 规则 + 轻量打分 + 1.5B 自适应路由 | ⬜ | 复用既有 `risk_adaptive_design.md` 与 `guard/router.py`，本轮未接 |
| E2E 四套件 Utility & ASR | ◐ | **travel（out-of-dist）+ slack（in-dist）已完成**，含无守卫 / HB / 规则 / PG2 四臂，见 `e2e_ablation.md` 与 `baselines_controls.md` §2。四套件只做了 2 个；workspace 已知不可标定 |
| Gen 未见工具/任务/自适应攻击 | ⬜ | 未做 |

## 一句话结论

**错位是真的、可因果测量、而且规模救不了它**：同一 guard 离线 84% / 线上 33%，
3B 更极端（离线最高、线上最低）；把攻击者那句话删掉，拦截率翻倍。
**修法不是"加更多负例"**：那只会把模型教成"敏感动作一律拦"（干净场景零打扰率归 0）；
有效的是**在同一个被污染的上下文里同时给出合法正例**，这样才学得到授权边界。
端到端（travel，未训套件）：ASR 32.5% → 2.5%（−30pp，p=6.7e-4），
干净效用 −15pp 但 n=20 不显著（p=0.41）；守卫单次 254ms / P95 293ms。
