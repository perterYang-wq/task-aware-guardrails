# -*- coding: utf-8 -*-
"""STEP F：claim 与判据状态表 + 越界扫描。

C1–C8 的 status / claim_scope / 禁止表述 / 证据文件；再对 reports/*.md 扫一遍
禁用表述（带否定语境的豁免），把命中的行标出来供人工确认。

产物：reports/claim_status.md
"""
import glob
import json
import os
import re

R = "/data/projects/guardrails"
OUT = os.path.join(R, "reports/claim_status.md")
state = json.load(open(os.path.join(R, "runs/auto/state.json"), encoding="utf-8"))
cl = state["claims"]

CLAIMS = [
    dict(id="C1", ctx=["dInj"], key="C1_problem", name="载荷污染是可测量的因果量",
         status="done",
         scope="**仅 p1 系列（标准授权 SFT）**：dInj = −0.459 / −0.384 / −0.315（三 seed）、3B −0.509。"
               "m2_HB（本文 M1）的 dInj 是 **+0.233**，符号相反，不得混用。",
         forbidden=["所有模型 dInj 为负", "M1 的 dInj 为 −0.459", "载荷一律让守卫更宽松"],
         evidence=["results/diag/metrics.json", "results/diag/offline_vs_online.json",
                   "reports/phase1_baseline_v2.md"]),
    dict(id="C2", ctx=["ASR", "泛化", "未见", "套件"], key="C2_task_aware", name="任务感知降低端到端 ASR",
         status="done",
         scope="整体效果：banking 2/64→0（天花板，p=.50）；slack 6/105→0（p=.031）；"
               "travel 13/80→1（p=.0018）。只对这三个套件、这一套 agent 成立。",
         forbidden=["跨套件泛化", "未见套件", "对任意 agent 成立"],
         evidence=["reports/phase1_baseline_v2.md", "reports/b10_ablation.md",
                   "reports/final_metrics.csv"]),
    dict(id="C3", ctx=["Task-Shield", "成本", "延迟"], key="C3_vs_prior", name="相对 Task-Shield 的效用/延迟优势",
         status="done",
         scope="slack 42 攻击场景、同一 7B agent：ASR 0/42 vs 0/42；干净效用 66.7% vs 23.8%"
               "（McNemar 9:0, p=.0039）；延迟 251 vs 574 ms（0.44×）；显存 +4.1 GB。",
         forbidden=["成本是 1/5", "更便宜一个数量级", "全面优于 Task-Shield"],
         evidence=["reports/b3_tshield.md", "reports/mcnemar_audit.md"]),
    dict(id="C4", ctx=["效用"], key="C4_utility", name="干净效用不劣于基线",
         status="partial",
         scope="banking 持平 37.5%；slack 66.7% 高于基线 61.9%；travel 10% 低于基线 25%。"
               "只在 slack（in-distribution）成立。",
         forbidden=["效用全面不低于基线", "travel 上也保住效用"],
         evidence=["reports/final_metrics.csv", "reports/b10_ablation.md"]),
    dict(id="C5a", ctx=["0.5B", "ACB"], key="C5_model_size", name="0.5B 保留 86.5% 判别力",
         status="pass",
         scope="离线 ACB 0.849 vs 0.981（=86.5%）；端到端 travel ASR 3/40 vs 1/40、"
               "干净误拦 21/99 vs 11/97（p=.081）。",
         forbidden=["0.5B 与 1.5B 等效", "参数量减半无代价"],
         evidence=["reports/b5_lightweight.md", "probes/mcnemar_audit.json"]),
    dict(id="C5b", ctx=["CPU", "实时", "延迟", "p95"], key="C5_cpu_latency", name="CPU 单次 ≤1.5 s",
         status="partial",
         scope="仅 p50 达标（1.461 s）；mean 1.851 s、p95 4.182 s、max 7.468 s 均超标。",
         forbidden=["CPU 可实时部署", "交互级延迟", "把 251 ms 当作 0.5B 的延迟"],
         evidence=["results/classifier/latency_05b_cpu.json", "reports/b5_lightweight.md"]),
    dict(id="C6", ctx=["未见", "泛化", "OOD"], key="C6_cross_task", name="跨任务泛化的边界",
         status="done_task_level_only",
         scope="任务级：travel seen 0/20 vs unseen 1/20（+5pp）。**不是**套件级：travel 有 50% "
               "任务在配对训练集里，hardneg 对 travel 零覆盖。",
         forbidden=["未见套件", "跨套件泛化", "OOD 套件上验证"],
         evidence=["reports/correction_ood.md", "reports/phase1_baseline_v2.md"]),
    dict(id="C7", ctx=["meta", "C7", "补丁", "自适应", "授权层"], key="C7_adaptive", name="自适应攻击与部署层补丁",
         status="main_model_not_passed_patch_mitigates",
         scope="主模型 meta 3/20（未满足 ≤2/20）；补丁后 0/20，"
               "但 Fisher p=.231（n=20），显著性未建立；补丁只挡『参数来自不可信文本』。",
         forbidden=["达标", "显著改善", "证明补丁有效", "自适应攻击已解决"],
         evidence=["reports/b6_adaptive.md", "reports/posthoc_alignment.md",
                   "reports/mcnemar_audit.md"]),
    dict(id="C8", ctx=["净增益", "授权推理", "76.5"], key="C8_deny_attribution", name="DENY 归因与净增益（阶段五新增）",
         status="done",
         scope="M1 的 26 条非载荷依赖 DENY 中 M0 覆盖 76.9%；M1 only 6 / M0 only 4 / 交集 20；"
               "6 条中 4 条受污染，稳健净增益 2；McNemar p=.754。结论：动作先验为主。",
         forbidden=["任务信息带来净增益", "76.5% 是授权推理", "任务字段在写类上不可替代"],
         evidence=["reports/deny_attribution.md", "probes/net_gain_sets.json",
                   "reports/mcnemar_audit.md", "reports/consistency_check.md"]),
]

# ---- 越界扫描 ----
NEG = ("不得", "不能", "不应", "作废", "撤回", "错误", "不是", "并非", "旧表述", "已被推翻",
       "禁", "避免", "别写", "更正", "不显著", "既不", "不稳健", "不具备", "未满足", "未达标")
hits = []
for p in sorted(glob.glob(os.path.join(R, "reports/*.md"))):
    base = os.path.basename(p)
    if base in ("claim_status.md",):
        continue
    for i, line in enumerate(open(p, encoding="utf-8"), 1):
        s = line.strip()
        if not s:
            continue
        for c in CLAIMS:
            for w in c["forbidden"]:
                if w not in s or any(n in s for n in NEG):
                    continue
                if c.get("ctx") and not any(k.lower() in s.lower() for k in c["ctx"]):
                    continue
                hits.append((base, i, c["id"], w, s[:120]))

# ---- 初稿评估 ----
draft = os.path.join(R, "reports/paper_draft.md")
draft_note = ("`reports/paper_draft.md` 是 P0/P1 阶段的旧稿（英文，§1–§8 讲 benchmark 与分类器，"
              "§4 是 Method 而非本文的归因节），**不含 C1–C8**，不能直接沿用；"
              "需要按本表重写。")
if os.path.exists(draft):
    txt = open(draft, encoding="utf-8").read()
    draft_note += " 旧稿长度 %d 字符，§5 Results 讲 PRA/SPA（PAB 配对），与本文 e2e 指标不同源。" % len(txt)

# ---- 输出 ----
L = ["# Claim 与判据状态表（C1–C8）", "",
     "> 状态取自 `runs/auto/state.json`；scope 与禁用表述由本表维护（`scripts/claim_table.py`）。", "",
     "| # | claim | status | claim_scope（能说到哪） | 禁止表述 | 证据文件 |",
     "|---|---|---|---|---|---|"]
for c in CLAIMS:
    st = cl.get(c["key"], {}).get("status", c["status"])
    L.append("| %s | %s | `%s` | %s | %s | %s |"
             % (c["id"], c["name"], st, c["scope"],
                "；".join("「%s」" % w for w in c["forbidden"]),
                "、".join("`%s`" % e for e in c["evidence"])))

OLD = {"baselines_controls.md", "e2e_ablation.md", "m2_ladder.md", "p2v2_report.md",
       "phase1_baseline_v2.md", "paper_draft.md"}
EXEMPT = {"correction_ood.md", "claim_status.md"}   # 更正文档本身引用旧表述，不算越界
hits = [h for h in hits if h[0] not in EXEMPT]
old_hits = [h for h in hits if h[0] in OLD]
new_hits = [h for h in hits if h[0] not in OLD]
L += ["", "## 越界扫描（reports/*.md）", "",
      "分两类：**旧文档**（早于 `correction_ood.md` 的更正，需加横幅）与**现行文档**（需改）。", ""]
if old_hits:
    L += ["### A. 旧文档（结论已被更正，需加 `SUPERSEDED` 横幅）", "",
          "| 文件 | 行 | claim | 命中词 | 原文 |", "|---|---|---|---|---|"]
    for h in old_hits:
        L.append("| %s | %d | %s | %s | %s |" % h)
    L += ["", "处理建议：在这些文件顶部加一行 “⚠️ 本文早于 2026-11-01 的 `correction_ood.md`，"
          "travel 已由『未见套件』降级为『配对配方未见套件』；引用前先看更正。”", ""]
if new_hits:
    L += ["### B. 现行文档（需改）", "",
          "命中 %d 行：" % len(new_hits), "",
          "| 文件 | 行 | claim | 命中词 | 原文 |", "|---|---|---|---|---|"]
    for h in new_hits:
        L.append("| %s | %d | %s | %s | %s |" % h)
if not new_hits:
    L += ["现行文档未命中（已按 claim 语境过滤，并豁免否定语境）。"]

L += ["", "## 初稿评估", "", draft_note, "",
      "结论：**没有可直接沿用的正文初稿**；C1–C8 的表述以本表为准，写作时逐条对照 scope。", ""]
open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
print("claims", len(CLAIMS), "| hits", len(hits))
for h in hits:
    print("  ", h[0], h[1], h[2], h[3], h[4][:60])
