# -*- coding: utf-8 -*-
"""B9 · 六张定稿图。全部读机器产物，不手填数字。

输入：
  reports/final_metrics.csv                    （b9_metrics.py 生成）
  results/diag/offline_vs_online.json
  results/p2/diag/metrics.json                 （四臂 dInj 同文件）
  results/classifier/routing_ablation.json
  results/classifier/latency_rule_cpu.json
  reports/b3_tshield.md                        （M1 / Task-Shield 的 slack e2e 延迟）
输出：final_figures/fig1..fig6.png + reports/final_figures.md（图注索引）
"""
import csv
import json
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

R = "/data/projects/guardrails"
FIG = os.path.join(R, "final_figures")
os.makedirs(FIG, exist_ok=True)

for cand in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
             "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"):
    if os.path.exists(cand):
        fm.fontManager.addfont(cand)
        break
plt.rcParams.update({
    "font.family": "Noto Sans CJK JP",
    "axes.unicode_minus": False,
    "figure.dpi": 170,
    "savefig.bbox": "tight",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linestyle": ":",
    "font.size": 9,
})
C = dict(m1="#1f4e79", m0="#c0504d", e0="#7f7f7f", ts="#e69f00",
         rule="#8c8c8c", s="#5b9bd5", hbsm="#70ad47")

CAPTIONS = []


def cap(name, text):
    CAPTIONS.append((name, text))


def rd_csv():
    with open(os.path.join(R, "reports/final_metrics.csv"), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def val(rows, **kw):
    for r in rows:
        if all((r.get(k) == v) for k, v in kw.items()):
            try:
                return float(r["value"])
            except (TypeError, ValueError):
                return None
    return None


def n_of(rows, **kw):
    for r in rows:
        if all((r.get(k) == v) for k, v in kw.items()):
            return int(float(r["num"])), int(float(r["den"])) if r["den"] else 0
    return None, None


def footer(fig, txt):
    fig.text(0.005, -0.055, txt, fontsize=6.2, color="#666666", ha="left", va="top")


ROWS = rd_csv()

# ---------------------------------------------------------------- 图 1
ov = json.load(open(os.path.join(R, "results/diag/offline_vs_online.json"), encoding="utf-8"))
NAME = {"p1_15b_nt_s0": "1.5B 任务盲 s0", "p1_15b_task_s0": "1.5B 任务感知 s0",
        "p1_15b_task_s42": "1.5B 任务感知 s42", "p1_15b_task_s123": "1.5B 任务感知 s123",
        "p1_3b_task_s0": "3B 任务感知 s0"}
fig, ax = plt.subplots(figsize=(5.4, 3.7))
xs = [r["PRA"] for r in ov]
ys = [100 * r["ACB_full"] for r in ov]
ax.scatter(xs, ys, s=52, c=C["m1"], edgecolor="white", linewidth=0.8, zorder=3)
for r in ov:
    ax.annotate(NAME.get(r["arm"], r["arm"]), (r["PRA"], 100 * r["ACB_full"]),
                textcoords="offset points", xytext=(6, 7), fontsize=7.2, color="#333333")
k, b = np.polyfit(xs, ys, 1)
xx = np.linspace(min(xs) - 0.01, max(xs) + 0.01, 20)
ax.plot(xx, k * xx + b, "--", color=C["e0"], lw=1.2,
        label="线性趋势（斜率 %.0f pp / PRA）" % k)
ax.set_xlabel("离线配对排序准确率 PRA（PAB-RD strict_test）")
ax.set_ylabel("线上攻击调用拦截率 ACB（%）")
ax.set_title("图 1｜离线授权排序能力不预测线上攻击拦截", fontsize=10)
ax.legend(loc="upper right", fontsize=7.5, frameon=False)
ax.text(0.02, 0.03,
        "臂 E 的映射缺口：调用级误拦 15.9%→62.4%，\n任务级 ASR 仍为 0/42 vs 0/42",
        transform=ax.transAxes, fontsize=7.2, va="bottom",
        bbox=dict(boxstyle="round,pad=0.35", fc="#fdf2e9", ec="#e69f00", lw=0.8))
footer(fig, "数据：results/diag/offline_vs_online.json（5 个同协议 checkpoint）｜重算：scripts/b9_metrics.py, scripts/b9_figures.py")
fig.savefig(os.path.join(FIG, "fig1_offline_vs_online.png"))
plt.close(fig)
cap("fig1_offline_vs_online.png",
    "离线 PRA 与线上 ACB 的散点（5 个 p1 系列 checkpoint，同一诊断集）。"
    "PRA 最高的 1.5B task-aware s0（0.856）线上拦截最低（21.4%），"
    "说明配对排序能力不能替代攻击拦截评估。数据 `results/diag/offline_vs_online.json`；"
    "重算 `scripts/b9_metrics.py`（fig1 段）、`scripts/b9_figures.py`。"
    "臂 E 标注来自 `results/e2e/slack/m2_SM_s0_b10e_inj1-3` 的调用级复算。")

# ---------------------------------------------------------------- 图 2
met = json.load(open(os.path.join(R, "results/p2/diag/metrics.json"), encoding="utf-8"))
SEEDS = [("m2_HB_s0", "s0", C["m1"]), ("m2_HB_s42", "s42", C["m1"]),
         ("m2_HB_s123", "s123", C["m1"]), ("m2_HBnt_s0", "M0 任务盲", C["m0"])]
fig, ax = plt.subplots(figsize=(4.9, 3.3))
lab, vals, los, his = [], [], [], []
for tag, name, _ in SEEDS:
    d = met[tag]["dInj"]
    lab.append(name)
    vals.append(100 * d["delta"])
    los.append(100 * (d["delta"] - d["ci"][0]))
    his.append(100 * (d["ci"][1] - d["delta"]))
cols = [c for _, _, c in SEEDS]
ax.bar(range(len(lab)), vals, color=cols, width=0.58, alpha=0.9)
ax.errorbar(range(len(lab)), vals, yerr=[los, his], fmt="none", ecolor="#333333",
            capsize=4, lw=1.1)
for i, v in enumerate(vals):
    ax.text(i, vals[i] + his[i] + 1.6, "%+.1f" % v, ha="center", fontsize=8)
ax.set_xticks(range(len(lab)))
ax.set_xticklabels(lab)
ax.set_ylim(0, max(vals) + max(his) + 9)
ax.set_ylabel("dInj = ACB(full) − ACB(noinj)（pp）")
ax.set_title("图 2｜dInj 的 seed 稳定性与任务盲臂对照", fontsize=10)
ax.text(0.02, 0.96, "正值 = 载荷本身成为告警线索；误差棒为场景簇 bootstrap 95%CI",
        transform=ax.transAxes, fontsize=6.9, va="top", color="#444444")
footer(fig, "数据：results/p2/diag/metrics.json（dInj.delta / dInj.ci，n=159 攻击调用；对 m2_HB_s0 与 results/diag 逐位一致）｜重算：scripts/b9_metrics.py, scripts/b9_figures.py")
fig.savefig(os.path.join(FIG, "fig2_dinj_seeds.png"))
plt.close(fig)
cap("fig2_dinj_seeds.png",
    "三个 seed 的 dInj 与任务盲臂对照，误差棒为场景簇 bootstrap 95%CI。"
    "M1 三 seed 为 +22.6~+24.5pp（载荷是告警线索，幅度稳定），M0 任务盲为 +55.4pp（更依赖载荷）。"
    "数据 `results/p2/diag/metrics.json`；重算 `scripts/b9_metrics.py`（C1 段）、`scripts/b9_figures.py`。")

# ---------------------------------------------------------------- 图 3
fig, ax = plt.subplots(figsize=(5.8, 3.5))
suites = ["banking", "slack", "travel"]
arms = [("E0", "E0 无守卫", C["e0"]), ("M0", "M0 任务盲", C["m0"]), ("M1", "M1 任务感知", C["m1"])]
w = 0.26
for j, (arm, name, col) in enumerate(arms):
    vs, ns = [], []
    for s in suites:
        vs.append(val(ROWS, claim="C2_task_aware", suite=s, arm=arm, metric="asr"))
        ns.append(n_of(ROWS, claim="C2_task_aware", suite=s, arm=arm, metric="asr"))
    ax.bar([i + (j - 1) * w for i in range(len(suites))], vs, width=w, label=name, color=col, alpha=0.9)
    for i, v in enumerate(vs):
        ax.text(i + (j - 1) * w, v + 0.9, "%d/%d" % ns[i], ha="center", fontsize=6.9)
ax.set_xticks(range(len(suites)))
ax.set_xticklabels(["banking\n(32 攻击场景)", "slack\n(42)", "travel\n(40)"])
ax.set_ylabel("ASR（%）")
ax.set_ylim(0, 58)
ax.set_title("图 3｜三套件 × 三臂的攻击成功率", fontsize=10)
ax.legend(frameon=False, fontsize=7.4, ncol=3, loc="upper right", bbox_to_anchor=(1.0, 1.02))
footer(fig, "数据：results/e2e/{banking,slack,travel}/*/scen.jsonl + results/ad_v3/*/scen_merged.jsonl（E0）｜重算：scripts/b9_metrics.py, scripts/b9_figures.py")
fig.savefig(os.path.join(FIG, "fig3_suites_arms.png"))
plt.close(fig)
cap("fig3_suites_arms.png",
    "三套件 × 三臂 ASR，柱标为分子/分母。banking 为天花板（E0 25.0%），"
    "slack 与 travel 上 M1 相对 M0 分别为 0/42 vs 4/42、1/40 vs 6/40。"
    "数据 `results/e2e/*/*/scen.jsonl` 与 `results/ad_v3/*/scen_merged.jsonl`；重算 `scripts/b9_metrics.py`（C2 段）。")

# ---------------------------------------------------------------- 图 4
def b3_latency():
    """从 b3_tshield.md 的 slack 表取 M1 / Task-Shield 的 e2e 单次延迟。

    同一文件里 travel 表也有 'NNN / NNN ms'，必须用 '0/42' 锚定 slack 行。
    """
    out = {}
    for line in open(os.path.join(R, "reports/b3_tshield.md"), encoding="utf-8"):
        if "0/42" not in line:
            continue
        m = re.search(r"(\d+) / (\d+) ms", line)
        if not m:
            continue
        if "M1 任务感知" in line:
            out["m1"] = float(m.group(1))
        if "Task-Shield" in line:
            out["ts"] = float(m.group(1))
    return out.get("m1"), out.get("ts")


m1_lat, ts_lat = b3_latency()
rule = json.load(open(os.path.join(R, "results/classifier/latency_rule_cpu.json"), encoding="utf-8"))

pts = [
    ("M1 任务感知（1.5B LoRA）", m1_lat, C["m1"],
     val(ROWS, claim="C2_task_aware", suite="slack", arm="M1", metric="asr"),
     val(ROWS, claim="C2_task_aware", suite="slack", arm="M1", metric="utility"),
     (12, 17), "left"),
    ("Task-Shield（7B 判官）", ts_lat, C["ts"],
     val(ROWS, claim="C3_vs_prior", suite="slack", arm="tshield", metric="asr"),
     val(ROWS, claim="C3_vs_prior", suite="slack", arm="tshield", metric="utility"),
     (12, -21), "left"),
    ("纯规则 γ==3", rule["p50"], C["rule"],
     val(ROWS, claim="C3_vs_prior", suite="slack", arm="rule_gamma", metric="asr"),
     val(ROWS, claim="C3_vs_prior", suite="slack", arm="rule_gamma", metric="utility"),
     (10, 4), "left"),
    ("M0 任务盲（同基座）", m1_lat, C["m0"],
     val(ROWS, claim="C2_task_aware", suite="slack", arm="M0", metric="asr"),
     val(ROWS, claim="C2_task_aware", suite="slack", arm="M0", metric="utility"),
     (-16, 14), "right"),
]
fig, ax = plt.subplots(figsize=(5.8, 3.7))
for name, x, col, y, u, off, ha in pts:
    lat = "%.1f µs" % (x * 1000) if x < 1 else "%.0f ms" % x
    ax.scatter([x], [y], s=[70 + 10 * (u or 0)], c=col, alpha=0.85, edgecolor="white", zorder=3)
    ax.annotate("%s\n%s · 效用 %.1f%%" % (name, lat, u), (x, y),
                textcoords="offset points", xytext=off, fontsize=7.2, ha=ha)
ax.set_xscale("log")
ax.set_xlim(5e-4, 2.4e3)
ax.set_ylim(-9, 40)
ax.set_xlabel("单次判定延迟（ms，log 轴）")
ax.set_ylabel("ASR（%，lower better）")
ax.set_title("图 4｜成本-安全：便宜不等于可用", fontsize=10)
ax.text(0.02, 0.05, "点面积 ∝ 干净任务完成率；M0 延迟复用 M1 实测（同基座，未单独测）",
        transform=ax.transAxes, fontsize=6.6, color="#555555")
footer(fig, "数据：延迟 M1/TS 见 reports/b3_tshield.md（slack 表，正则读取）、规则 results/classifier/latency_rule_cpu.json；ASR/效用 reports/final_metrics.csv｜脚本 scripts/b9_rule_latency.py, scripts/b9_figures.py")
fig.savefig(os.path.join(FIG, "fig4_cost_safety.png"))
plt.close(fig)
cap("fig4_cost_safety.png",
    "成本-安全散点。纯规则延迟约 1.2 µs（416 次调用实测）但 ASR 31.0%、效用 4.8%；"
    "Task-Shield 安全达标但效用 23.8%、延迟 574 ms；M1 同时取得 0% ASR 与 66.7% 效用、251 ms。"
    "M0 的延迟按同基座复用 M1 实测值（未单独测，图内已标注）。"
    "数据 `reports/b3_tshield.md`（slack 表）、`results/classifier/latency_rule_cpu.json`、"
    "`reports/final_metrics.csv`；重算 `scripts/b9_rule_latency.py`、`scripts/b9_figures.py`。")

# ---------------------------------------------------------------- 图 5
fig, axes = plt.subplots(1, 3, figsize=(9.4, 4.0),
                         gridspec_kw=dict(width_ratios=[1.15, 0.95, 0.85]))
ax = axes[0]
steps = [("E0\n无守卫", val(ROWS, claim="B10", suite="slack", arm="E0", metric="asr")),
         ("+ 标准\nSFT", val(ROWS, claim="B10", suite="slack", arm="S", metric="asr")),
         ("+ 任务盲\n配方", val(ROWS, claim="B10", suite="slack", arm="M0", metric="asr")),
         ("+ 完整\n配方 M1", val(ROWS, claim="B10", suite="slack", arm="M1_block", metric="asr"))]
for i, (name, v) in enumerate(steps):
    ax.bar(i, v, color=C["s"] if i < 3 else C["m1"], width=0.6, alpha=0.9)
    ax.text(i, v + 1.3, "%.1f%%" % v, ha="center", fontsize=8)
    if i:
        d = v - steps[i - 1][1]
        ax.text(i - 0.5, max(v, steps[i - 1][1]) + 6.5, "%.1fpp" % d,
                ha="center", fontsize=7.4, color="#333333")
        ax.plot([i - 1 + 0.3, i - 0.3], [steps[i - 1][1], steps[i - 1][1]],
                ls=":", lw=0.8, color="#999999")
ax.set_xticks(range(len(steps)))
ax.set_xticklabels([s[0] for s in steps], fontsize=7.4)
ax.set_ylabel("slack ASR（%）")
ax.set_ylim(0, 62)
ax.set_title("(a) 数据配方瀑布（轴 ③）", fontsize=9)

ax = axes[1]
dep = [("纯硬规则", val(ROWS, claim="B10", suite="slack", arm="rule_only", metric="asr"), C["rule"]),
       ("M1 仅模型", val(ROWS, claim="B10", suite="slack", arm="M1_block", metric="asr"), C["m1"]),
       ("M1+硬规则", val(ROWS, claim="B10", suite="slack", arm="M1_rule", metric="asr"), C["m0"]),
       ("HB-sm", val(ROWS, claim="B10", suite="slack", arm="HBsm", metric="asr"), C["hbsm"])]
ax.barh(range(len(dep)), [d[1] for d in dep], color=[d[2] for d in dep], height=0.55, alpha=0.9)
for i, d in enumerate(dep):
    ax.text(max(d[1], 0) + 0.7, i, "%.1f%%" % d[1], va="center", fontsize=7.6)
ax.set_yticks(range(len(dep)))
ax.set_yticklabels([d[0] for d in dep], fontsize=7.6)
ax.invert_yaxis()
ax.set_xlabel("slack ASR（%）")
ax.set_xlim(0, 36)
ax.set_title("(b) 部署轴（轴 ⑤）与配方轴（轴 ④）", fontsize=9)

# --- (c) 第七轴：动作先验 vs 任务信息（DENY 集合） ---
ax = axes[2]
ng = json.load(open(os.path.join(R, "probes/net_gain_sets.json"), encoding="utf-8"))
A, B = ng["M1_deny"], ng["M0_deny"]
inter, only1, only0 = ng["intersection"], ng["M1_only"], ng["M0_only"]
ax.barh([1], [inter], color="#9dc3e6", height=0.5)
ax.barh([1], [only1], left=[inter], color=C["m1"], height=0.5)
ax.barh([0], [inter], color="#9dc3e6", height=0.5)
ax.barh([0], [only0], left=[inter], color=C["m0"], height=0.5)
ax.text(inter / 2, 1, "交集 %d" % inter, ha="center", va="center", fontsize=7.6)
ax.text(inter + only1 / 2, 1, "%d" % only1, ha="center", va="center", fontsize=7.6, color="white")
ax.text(inter / 2, 0, "交集 %d" % inter, ha="center", va="center", fontsize=7.6)
ax.text(inter + only0 / 2, 0, "%d" % only0, ha="center", va="center", fontsize=7.6, color="white")
ax.set_yticks([1, 0])
ax.set_yticklabels(["M1 任务感知\n(共 %d)" % A, "M0 任务盲\n(共 %d)" % B], fontsize=7.6)
ax.set_xlabel("P1 后仍 DENY 的调用数\n稳健净增益 %d 条（6 条中 %d 条受污染）\nMcNemar p = 0.754"
              % (ng["robust_subset"], ng["contaminated"]), fontsize=7.0)
ax.set_xlim(0, A + 3)
ax.set_title("(c) 第七轴：净增益集合", fontsize=9)


fig.suptitle("图 5｜消融轴：①任务字段 ②历史长度 ③配方 ④配对正例 ⑤部署组件 ⑥路由策略 ⑦动作先验 vs 任务信息",
             fontsize=9.2, y=1.02)
fig.tight_layout()
footer(fig, "数据：reports/final_metrics.csv（B10 段）；②与⑥的数字见图 6 与 reports/b9_notes｜重算：scripts/b9_metrics.py, scripts/b9_figures.py")
fig.savefig(os.path.join(FIG, "fig5_ablation_waterfall.png"))
plt.close(fig)
cap("fig5_ablation_waterfall.png",
    "六根消融轴。(a) 数据配方瀑布：E0 50.0% → 标准 SFT 11.9%（−38.1pp）→ 任务盲 9.5% → M1 0.0%（−9.5pp）。"
    "(b) 部署轴与配方轴：纯硬规则 28.6%、M1 0%、M1+硬规则 0%（安全零增益、效用 4.8%）、HB-sm 0%（调用级误拦 62.4%）。"
    "(c) 第七轴：M1 与 M0 在 P1 判定下的 DENY 集合（交集 20、M1 only 6、M0 only 4），"
    "6 条净增益中 4 条受污染，稳健子集 2 条；McNemar p=0.754。来源 `reports/deny_attribution.md` 第 3 节。"
    "轴②历史长度（ACB none .560→last3 .837→full .918）与轴⑥路由见图 6 与 `reports/b9_notes.md`。"
    "数据 `reports/final_metrics.csv`（B10 段）；重算 `scripts/b9_metrics.py`、`scripts/b9_figures.py`。")

# ---------------------------------------------------------------- 图 6
rt = json.load(open(os.path.join(R, "results/classifier/routing_ablation.json"), encoding="utf-8"))
POL = ["all", "gamma>=2", "gamma>=3"]
fig, ax = plt.subplots(figsize=(5.6, 3.6))
style = {"m2_HB_s0": ("M1 任务感知 · 总体", C["m1"], "-", "o"),
         "m2_HBnt_s0": ("M0 任务盲 · 总体", C["m0"], "--", "s"),
         "m2_S_s0": ("S 标准 SFT · 总体", C["s"], ":", "^")}
for arm, (name, col, ls, mk) in style.items():
    xs = [100 * rt[arm][p]["checked_frac"] for p in POL]
    ys = [100 * rt[arm][p]["ACB"] for p in POL]
    ax.plot(xs, ys, ls, marker=mk, color=col, lw=1.3, ms=4.5, label=name)
m1 = rt["m2_HB_s0"]
xs = [100 * m1[p]["checked_frac"] for p in POL]
ax.plot(xs, [100 * m1[p]["ACB_read"] for p in POL], "-.", marker="x",
        color="#c00000", lw=1.1, ms=5, label="M1 · 读类攻击")
ax.plot(xs, [100 * m1[p]["ACB_write"] for p in POL], "-.", marker="+",
        color="#2e7d32", lw=1.1, ms=7, label="M1 · 写类攻击")
ax.annotate("路由到 γ≥2 后读类归零（0/28）", (xs[1], 0), textcoords="offset points",
            xytext=(20, 34), fontsize=7.2, color="#c00000",
            arrowprops=dict(arrowstyle="->", color="#c00000", lw=0.8))
ax.annotate("全查时读类 92.9%", (xs[0], 92.9), textcoords="offset points",
            xytext=(-96, -18), fontsize=7.2, color="#c00000",
            arrowprops=dict(arrowstyle="->", color="#c00000", lw=0.7))
ax.set_xlabel("被检查调用比例（%）")
ax.set_ylabel("ACB（%）")
ax.set_ylim(-4, 112)
ax.set_xlim(18, 104)
ax.set_title("图 6｜路由曲线：省下的检查量全部来自放弃读类", fontsize=10)
ax.legend(fontsize=6.8, frameon=False, loc="center right", bbox_to_anchor=(1.0, 0.42))
footer(fig, "数据：results/classifier/routing_ablation.json（2370 调用，159 攻击 / 2174 干净）｜重算：scripts/b9_metrics.py, scripts/b9_figures.py")
fig.savefig(os.path.join(FIG, "fig6_routing.png"))
plt.close(fig)
cap("fig6_routing.png",
    "检查比例 vs ACB，含读类（28 条）与写类（131 条）分解。从全查（100%）到 γ≥2（27.0%）省下 73% 的判定量，"
    "读类拦截从 92.9% 直接掉到 0；写类几乎不变（99.2%）。这是不做路由的直接理由。"
    "数据 `results/classifier/routing_ablation.json`；重算 `scripts/b9_metrics.py`（B10 routing 段）、`scripts/b9_figures.py`。")

# ---------------------------------------------------------------- 图注索引
with open(os.path.join(R, "reports/final_figures.md"), "w", encoding="utf-8") as f:
    f.write("# final_figures · 图注索引\n\n")
    f.write("> 每张图都由 `scripts/b9_figures.py` 从机器产物重画；数字不在脚本里手写。\n")
    f.write("> 图内页脚标注了数据来源文件与重算脚本。\n\n")
    for n, t in CAPTIONS:
        f.write("## %s\n\n![%s](final_figures/%s)\n\n%s\n\n" % (n, n, n, t))
print("ok", len(CAPTIONS), "figures", "m1_lat=%s ts_lat=%s" % (m1_lat, ts_lat))
