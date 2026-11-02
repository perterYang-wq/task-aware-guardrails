# -*- coding: utf-8 -*-
"""Build the 3 main-text figures + 6 appendix figures (pdf + png + csv)."""
import json
import os
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Patch  # noqa: E402

from ft_common import (OUT_F, R, SRC_DIAG, SRC_LAT_05B, SRC_LAT_RULE, SRC_NG,
                       SRC_OVO, SRC_POST, SRC_PROBE, SRC_ROUTE, b3_latency_map,
                       emit_fig_csv, nd, save_fig)

OK = dict(blue="#0072B2", verm="#D55E00", green="#009E73", orange="#E69F00",
          sky="#56B4E9", yellow="#F0E442", grey="#999999", dark="#333333")

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 8,
    "axes.labelsize": 8,
    "axes.titlesize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 6.8,
    "axes.linewidth": 0.6,
    "xtick.major.width": 0.5,
    "ytick.major.width": 0.5,
    "xtick.major.size": 2.5,
    "ytick.major.size": 2.5,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "grid.alpha": 0.25,
    "grid.linewidth": 0.4,
    "grid.linestyle": ":",
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "savefig.bbox": "tight",
})

LAB = {"p1_15b_task_s0": "s0", "p1_15b_task_s42": "s42", "p1_15b_task_s123": "s123",
       "p1_3b_task_s0": "3B", "p1_15b_nt_s0": "blind"}


def tag(ax, text, dx=-0.16):
    ax.text(dx, 1.03, text, transform=ax.transAxes, fontsize=9, fontweight="bold",
            va="bottom", ha="left")


def nd3(claim, suite, arm, metric):
    n, d, _ = nd(claim, suite, arm, metric)
    return 100.0 * n / d


# ------------------------------------------------------------------ fig 1
def fig1():
    diag = json.load(open(os.path.join(R, SRC_DIAG), encoding="utf-8"))
    ov = json.load(open(os.path.join(R, SRC_OVO), encoding="utf-8"))
    order = ["p1_15b_task_s0", "p1_15b_task_s42", "p1_15b_task_s123",
             "p1_3b_task_s0", "p1_15b_nt_s0"]

    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(7.0, 2.85), gridspec_kw=dict(width_ratios=[1.0, 1.05], wspace=0.30))

    vals, lo, hi = [], [], []
    for arm in order:
        d = diag[arm]["dInj"]
        vals.append(100 * d["delta"])
        lo.append(100 * (d["delta"] - d["ci"][0]))
        hi.append(100 * (d["ci"][1] - d["delta"]))
    x = np.arange(len(order))
    ax1.axhline(0, color=OK["grey"], lw=0.8, ls="--", zorder=1)
    ax1.errorbar(x, vals, yerr=[lo, hi], fmt="o", ms=5, color=OK["blue"],
                 ecolor=OK["blue"], elinewidth=1.0, capsize=2.5, capthick=0.9, zorder=3)
    ax1.set_xticks(x)
    ax1.set_xticklabels([LAB[a] for a in order], fontsize=7)
    ax1.set_xlabel("Checkpoint (1.5B unless labelled)")
    ax1.set_ylabel("dInj (pp)")
    ax1.set_xlim(-0.7, len(order) - 0.3)
    ax1.set_ylim(-64, 8)
    ax1.grid(axis="y")
    tag(ax1, "(a)", dx=-0.14)

    pra = [r["PRA"] for r in ov]
    acb = [100 * r["ACB_full"] for r in ov]
    ax2.scatter(pra, acb, s=28, color=OK["verm"], edgecolor="white",
                linewidth=0.6, zorder=3)
    k, b = np.polyfit(pra, acb, 1)
    xx = np.linspace(min(pra) - 0.006, max(pra) + 0.006, 50)
    ax2.plot(xx, k * xx + b, ls="--", lw=1.0, color=OK["grey"], zorder=2)
    off = {"p1_15b_nt_s0": (6, -11, "left"), "p1_15b_task_s123": (7, 3, "left"),
           "p1_15b_task_s42": (7, 3, "left"), "p1_15b_task_s0": (7, 4, "left"),
           "p1_3b_task_s0": (0, -13, "center")}
    for r in ov:
        dx, dy, ha = off.get(r["arm"], (6, 4, "left"))
        ax2.annotate(LAB.get(r["arm"], r["arm"]), (r["PRA"], 100 * r["ACB_full"]),
                     textcoords="offset points", xytext=(dx, dy), fontsize=6.5,
                     color=OK["dark"], ha=ha)
    ax2.set_xlabel("Offline PRA")
    ax2.set_ylabel("Online ACB (%)")
    ax2.set_xlim(0.786, 0.892)
    ax2.set_ylim(12, 48)
    ax2.grid(axis="y")
    ax2.text(0.03, 0.07, "slope %.0f pp per PRA" % k, transform=ax2.transAxes,
             fontsize=6.5, va="bottom", color=OK["dark"])
    tag(ax2, "(b)", dx=-0.14)

    save_fig(fig, "fig1_dinj_pra_acb")
    emit_fig_csv("fig1_dinj_pra_acb", ["panel", "arm", "x", "y", "ci_low", "ci_high"],
                 [["a", a, "", v, v - l, v + h] for a, v, l, h in zip(order, vals, lo, hi)]
                 + [["b", r["arm"], r["PRA"], 100 * r["ACB_full"], "", ""] for r in ov])


# ------------------------------------------------------------------ fig 4
def fig4():
    stages = [("E0", "E0"), ("+SFT", "S"), ("+blind", "M0"), ("M1", "M1_block")]
    a_pct = [nd3("B10", "slack", a, "asr") for _, a in stages]
    u_pct = [nd3("B10", "slack", a, "utility") for _, a in stages]
    xs = np.arange(len(stages))

    fig, ax = plt.subplots(figsize=(4.6, 2.95))
    ax2 = ax.twinx()
    l1, = ax.plot(xs, a_pct, "-o", color=OK["verm"], ms=5, lw=1.4, label="ASR (left)")
    l2, = ax2.plot(xs, u_pct, "-s", color=OK["blue"], ms=4.5, lw=1.4,
                   label="Clean completion (right)")
    a_off = [(-9, -2, "right"), (0, -14, "center"), (0, -14, "center"), (0, 10, "center")]
    u_off = [(13, 3, "left"), (0, 9, "center"), (11, 2, "left"), (0, 9, "center")]
    for i, v in enumerate(a_pct):
        dx, dy, ha = a_off[i]
        ax.annotate("%.1f" % v, (i, v), textcoords="offset points", xytext=(dx, dy),
                    ha=ha, fontsize=6.5, color=OK["verm"])
    for i, v in enumerate(u_pct):
        dx, dy, ha = u_off[i]
        ax2.annotate("%.1f" % v, (i, v), textcoords="offset points", xytext=(dx, dy),
                     ha=ha, fontsize=6.5, color=OK["blue"])
    ax.set_xticks(xs)
    ax.set_xticklabels([s[0] for s in stages], fontsize=7)
    ax.set_xlim(-0.4, len(stages) - 0.6)
    ax.set_ylim(-7, 62)
    ax2.set_ylim(20, 76)
    ax.set_ylabel("ASR (%)", color=OK["verm"])
    ax2.set_ylabel("Clean-task completion (%)", color=OK["blue"])
    ax.tick_params(axis="y", colors=OK["verm"])
    ax2.tick_params(axis="y", colors=OK["blue"])
    ax2.spines["right"].set_visible(True)
    ax2.spines["right"].set_color(OK["blue"])
    ax.set_xlabel("Recipe stage")
    ax.legend(handles=[l1, l2], loc="upper center", bbox_to_anchor=(0.5, -0.26),
              ncol=2, frameon=False, handlelength=1.5, columnspacing=1.2)

    save_fig(fig, "fig4_recipe_ladder")
    emit_fig_csv("fig4_recipe_ladder", ["stage", "asr_num", "asr_den", "asr_pct",
                                       "util_num", "util_den", "util_pct"],
                 [[s, nd("B10", "slack", a, "asr")[0], nd("B10", "slack", a, "asr")[1],
                   ap, nd("B10", "slack", a, "utility")[0],
                   nd("B10", "slack", a, "utility")[1], up]
                  for (s, a), ap, up in zip(stages, a_pct, u_pct)])


# ------------------------------------------------------------------ fig 6
def fig6():
    d = json.load(open(os.path.join(R, SRC_PROBE), encoding="utf-8"))
    seeds = ["s0", "s42", "s123"]
    variants = ["P0", "P1", "P2", "P3", "P4"]
    code = {"ALLOW": 0, "REVIEW": 1, "DENY": 2}
    grid = np.full((len(seeds), len(variants)), np.nan)
    raw = [["" for _ in variants] for _ in seeds]
    verdict = [["" for _ in variants] for _ in seeds]
    for i, s in enumerate(seeds):
        for r in d["results"][s]:
            j = variants.index(r["variant"].split()[0])
            grid[i, j] = code[r["parsed"]]
            raw[i][j] = r["raw"]
            verdict[i][j] = r["parsed"]

    cmap = ListedColormap([OK["sky"], OK["yellow"], OK["verm"]])
    fig, ax = plt.subplots(figsize=(4.4, 2.4))
    ax.imshow(grid, cmap=cmap, vmin=-0.5, vmax=2.5, aspect="auto")
    for i in range(len(seeds)):
        for j in range(len(variants)):
            if np.isnan(grid[i, j]):
                txt, col = "n/a", OK["dark"]
            else:
                txt = raw[i][j]
                col = "white" if verdict[i][j] == "DENY" else OK["dark"]
            ax.text(j, i, txt, ha="center", va="center", fontsize=7, color=col)
    ax.set_xticks(range(len(variants)))
    ax.set_xticklabels(variants)
    ax.set_yticks(range(len(seeds)))
    ax.set_yticklabels(["seed 0", "seed 42", "seed 123"])
    ax.set_xlabel("Probe variant")
    ax.set_ylabel("Guard seed")
    ax.set_xticks(np.arange(-0.5, len(variants), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(seeds), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.4, linestyle="-")
    ax.tick_params(which="minor", length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    handles = [Patch(facecolor=OK["sky"], label="ALLOW"),
               Patch(facecolor=OK["yellow"], label="REVIEW"),
               Patch(facecolor=OK["verm"], label="DENY")]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.26),
              ncol=3, frameon=False, handlelength=1.0, handleheight=0.9,
              columnspacing=1.2, borderpad=0.2)

    save_fig(fig, "fig6_probe_heatmap")
    rows = [[s, v, raw[i][j], verdict[i][j]] for i, s in enumerate(seeds)
            for j, v in enumerate(variants)]
    emit_fig_csv("fig6_probe_heatmap", ["seed", "variant", "raw", "verdict"], rows)


# ------------------------------------------------------------------ app fig 3
def fig3_app():
    suites = [("banking", "32/16"), ("slack", "42/21"), ("travel", "40/20")]
    arms = [("E0", "E0, no guard", OK["grey"]), ("M0", "M0, task-blind", OK["orange"]),
            ("M1", "M1, task-aware", OK["blue"])]
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.7),
                             gridspec_kw=dict(wspace=0.24, width_ratios=[1, 1]))
    w = 0.26
    for ax, metric, ylab, tg, top in ((axes[0], "asr", "ASR (%)", "(a)", 80),
                                      (axes[1], "utility", "Clean completion (%)", "(b)", 88)):
        for j, (arm, name, col) in enumerate(arms):
            vs, lbl = [], []
            for s, _ in suites:
                n, dd, _ = nd("C2_task_aware", s, arm, metric)
                vs.append(100 * n / dd)
                lbl.append("%d/%d" % (n, dd))
            ax.bar([i + (j - 1) * w for i in range(len(suites))], vs, width=w,
                   color=col, label=name, linewidth=0)
            for i, v in enumerate(vs):
                ax.text(i + (j - 1) * w, v + 1.5, lbl[i], ha="center", fontsize=5.8,
                        rotation=90, va="bottom")
        ax.set_xticks(range(len(suites)))
        ax.set_xticklabels(["%s\n%s" % (s, pp) for s, pp in suites], fontsize=7)
        ax.set_ylabel(ylab)
        ax.set_ylim(0, top)
        ax.grid(axis="y")
        tag(ax, tg, dx=-0.13)
    axes[0].legend(frameon=False, ncol=1, loc="upper right", handlelength=1.0)
    axes[0].set_xlabel("Suite (attack / clean scenarios)")

    save_fig(fig, "app_fig3_suites_arms")
    rows = []
    for s, pp in suites:
        for arm, name, _ in arms:
            for metric in ("asr", "utility"):
                n, dd, v = nd("C2_task_aware", s, arm, metric)
                rows.append([s, pp, arm, metric, n, dd, v])
    emit_fig_csv("app_fig3_suites_arms", ["suite", "protocol", "arm", "metric",
                                         "num", "den", "value_pct"], rows)


# ------------------------------------------------------------------ app fig 5
def fig5_app():
    fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.55),
                             gridspec_kw=dict(width_ratios=[0.95, 1.15, 1.0], wspace=0.5))
    ax = axes[0]
    stages = [("E0", "E0"), ("+SFT", "S"), ("+blind", "M0"), ("M1", "M1_block")]
    vs = [nd3("B10", "slack", a, "asr") for _, a in stages]
    cols = [OK["grey"], OK["sky"], OK["orange"], OK["blue"]]
    ax.bar(range(len(vs)), vs, color=cols, width=0.62, linewidth=0)
    for i, v in enumerate(vs):
        ax.text(i, v + 1.5, "%.1f" % v, ha="center", fontsize=6.5)
    ax.set_xticks(range(len(stages)))
    ax.set_xticklabels([s[0] for s in stages], fontsize=6.8)
    ax.set_ylabel("slack ASR (%)")
    ax.set_ylim(0, 60)
    ax.grid(axis="y")
    tag(ax, "(a)", dx=-0.30)

    ax = axes[1]
    items = [("string rule", "rule_only", OK["grey"]), ("M1", "M1_block", OK["blue"]),
             ("M1 + rule", "M1_rule", OK["verm"]), ("HB-sm", "HBsm", OK["green"])]
    av = [nd3("B10", "slack", a, "asr") for _, a, _ in items]
    uv = [nd3("B10", "slack", a, "utility") for _, a, _ in items]
    y = np.arange(len(items))
    ax.barh(y, av, height=0.5, color=[c for _, _, c in items], linewidth=0)
    for i in range(len(items)):
        ax.text(av[i] + 1.5, i, "%.1f  $\\cdot$  %.1f" % (av[i], uv[i]), va="center",
                fontsize=6.2)
    ax.set_yticks(y)
    ax.set_yticklabels([n for n, _, _ in items], fontsize=6.8)
    ax.invert_yaxis()
    ax.set_xlabel("slack: ASR $\\cdot$ clean completion (%)")
    ax.set_xlim(0, 96)
    ax.grid(axis="x")
    tag(ax, "(b)", dx=-0.34)

    ax = axes[2]
    ng = json.load(open(os.path.join(R, SRC_NG), encoding="utf-8"))
    inter, o1, o0 = ng["intersection"], ng["M1_only"], ng["M0_only"]
    for i, (only, col, name) in enumerate(((o1, OK["blue"], "M1 only"),
                                           (o0, OK["orange"], "M0 only"))):
        ax.barh([i], [inter], color="#dce8f2", height=0.5, linewidth=0)
        ax.barh([i], [only], left=[inter], color=col, height=0.5, linewidth=0, label=name)
        ax.text(inter / 2, i, "%d" % inter, ha="center", va="center", fontsize=6.4)
        ax.text(inter + only / 2, i, "%d" % only, ha="center", va="center", fontsize=6.4,
                color="white")
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["M1 (%d)" % ng["M1_deny"], "M0 (%d)" % ng["M0_deny"]], fontsize=6.8)
    ax.set_ylim(1.6, -0.6)
    ax.set_xlim(0, ng["M1_deny"] + 3)
    ax.set_xlabel("DENY set after P1")
    ax.grid(axis="x")
    ax.legend(frameon=False, fontsize=6.0, loc="lower right", handlelength=1.0)
    tag(ax, "(c)", dx=-0.34)

    save_fig(fig, "app_fig5_seven_axis")
    rows = [["a", s[0], a, v] for (s, a), v in zip(stages, vs)]
    rows += [["b", n, a, v] for (n, a, _), v in zip(items, av)]
    rows += [["b2", n, a + " (utility)", v] for (n, a, _), v in zip(items, uv)]
    rows += [["c", "intersection", "", inter], ["c", "M1_only", "", o1],
             ["c", "M0_only", "", o0], ["c", "robust", "", ng["robust_subset"]]]
    emit_fig_csv("app_fig5_seven_axis", ["panel", "label", "arm", "value"], rows)


# ------------------------------------------------------------------ app fig 7
def fig7_app():
    rt = json.load(open(os.path.join(R, SRC_ROUTE), encoding="utf-8"))
    pol = ["all", "gamma>=2", "gamma>=3"]
    fig, ax = plt.subplots(figsize=(4.3, 3.0))
    style = {"m2_HB_s0": ("M1, task-aware", OK["blue"], "-", "o"),
             "m2_HBnt_s0": ("M0, task-blind", OK["orange"], "--", "s"),
             "m2_S_s0": ("S, standard SFT", OK["sky"], ":", "^")}
    for arm, (name, col, ls, mk) in style.items():
        xs = [100 * rt[arm][q]["checked_frac"] for q in pol]
        ys = [100 * rt[arm][q]["ACB"] for q in pol]
        ax.plot(xs, ys, ls, marker=mk, color=col, lw=1.2, ms=4, label=name)
    m1 = rt["m2_HB_s0"]
    xs = [100 * m1[q]["checked_frac"] for q in pol]
    ax.plot(xs, [100 * m1[q]["ACB_read"] for q in pol], "-.", marker="x",
            color=OK["verm"], lw=1.0, ms=4.5, label="M1, read-type")
    ax.plot(xs, [100 * m1[q]["ACB_write"] for q in pol], "-.", marker="+",
            color=OK["green"], lw=1.0, ms=6, label="M1, write-type")
    ax.text(0.55, 0.10, "read-type: 92.9% $\\rightarrow$ 0%", transform=ax.transAxes,
            fontsize=6.3, color=OK["verm"])
    ax.set_xlabel("Share of calls checked (%)")
    ax.set_ylabel("ACB (%)")
    ax.set_ylim(-4, 108)
    ax.set_xlim(18, 106)
    ax.grid(axis="y")
    ax.legend(frameon=False, fontsize=6.2, loc="lower left", ncol=2,
              bbox_to_anchor=(-0.02, 1.01, 1.04, 0.1), mode="expand",
              handlelength=1.6, labelspacing=0.28, columnspacing=1.2)

    save_fig(fig, "app_fig7_routing")
    rows = []
    for arm in style:
        for q in pol:
            rows.append([arm, q, rt[arm][q]["checked_frac"], rt[arm][q]["ACB"],
                         rt[arm][q]["ACB_read"], rt[arm][q]["ACB_write"]])
    emit_fig_csv("app_fig7_routing", ["arm", "policy", "checked_frac", "acb",
                                      "acb_read", "acb_write"], rows)


# ------------------------------------------------------------------ app fig 8
def fig8_app():
    lat = b3_latency_map()
    rule_lat = json.load(open(os.path.join(R, SRC_LAT_RULE), encoding="utf-8"))
    l05 = json.load(open(os.path.join(R, SRC_LAT_05B), encoding="utf-8"))

    slack = [
        ("M1", lat["slack"]["m1"][0], nd3("C2_task_aware", "slack", "M1", "asr"),
         nd3("C2_task_aware", "slack", "M1", "utility"), OK["blue"], "o"),
        ("Task-Shield", lat["slack"]["ts"][0],
         nd3("C3_vs_prior", "slack", "tshield", "asr"),
         nd3("C3_vs_prior", "slack", "tshield", "utility"), OK["orange"], "s"),
        ("string rule", rule_lat["p50"],
         nd3("C3_vs_prior", "slack", "rule_gamma", "asr"),
         nd3("C3_vs_prior", "slack", "rule_gamma", "utility"), OK["grey"], "^"),
    ]
    travel = [
        ("M1", lat["travel"]["m1"][0], nd3("C2_task_aware", "travel", "M1", "asr"),
         nd3("C2_task_aware", "travel", "M1", "utility"), OK["blue"], "o"),
        ("Task-Shield", lat["travel"]["ts"][0],
         nd3("C3_vs_prior", "travel", "tshield", "asr"),
         nd3("C3_vs_prior", "travel", "tshield", "utility"), OK["orange"], "s"),
        ("0.5B guard", l05["p50"], nd3("C5_e2e", "travel", "m2_HB05_s0", "asr"),
         nd3("C5_e2e", "travel", "m2_HB05_s0", "utility"), OK["green"], "D"),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.9),
                             gridspec_kw=dict(wspace=0.30, width_ratios=[1, 1]))
    for ax, pts, tg, xlim, label in ((axes[0], slack, "(a)", (4e-4, 3.0e3), "slack 42/21"),
                                     (axes[1], travel, "(b)", (1.2e2, 4.2e3), "travel 40/20")):
        for name, x, y, u, col, mk in pts:
            ax.scatter([x], [y], s=45 + 0.55 * u, color=col, marker=mk, alpha=0.9,
                       edgecolor="white", linewidth=0.7, zorder=3)
        ax.set_xscale("log")
        ax.set_xlim(*xlim)
        ax.set_xlabel("Latency per decision (ms, log)")
        ax.set_ylabel("ASR (%)")
        ax.set_ylim(-7, 38)
        ax.grid(axis="y")
        ax.text(0.03, 0.94, label, transform=ax.transAxes, fontsize=6.4, va="top",
                color=OK["dark"])
        tag(ax, tg, dx=-0.14)

    for name, x, y, u, _c, _m in slack:
        dx, dy, ha = {"M1": (0, 11, "center"), "Task-Shield": (0, -15, "center"),
                      "string rule": (10, -3, "left")}[name]
        axes[0].annotate(name, (x, y), textcoords="offset points", xytext=(dx, dy),
                         fontsize=6.4, color=OK["dark"], ha=ha)
    for name, x, y, u, _c, _m in travel:
        dx, dy, ha = {"M1": (0, 11, "center"), "Task-Shield": (0, -15, "center"),
                      "0.5B guard": (0, 12, "center")}[name]
        axes[1].annotate(name, (x, y), textcoords="offset points", xytext=(dx, dy),
                         fontsize=6.4, color=OK["dark"], ha=ha)

    save_fig(fig, "app_fig8_cost_frontier")
    rows = [["slack", n, x, y, u] for n, x, y, u, _, _ in slack]
    rows += [["travel", n, x, y, u] for n, x, y, u, _, _ in travel]
    emit_fig_csv("app_fig8_cost_frontier", ["suite", "arm", "latency_ms", "asr_pct",
                                            "utility_pct"], rows)


# ------------------------------------------------------------------ app fig 9
def fig9_app():
    d = json.load(open(os.path.join(R, SRC_POST), encoding="utf-8"))
    tm, sl = d["travel-meta"], d["slack-static"]
    fig, axes = plt.subplots(1, 2, figsize=(6.4, 2.6),
                             gridspec_kw=dict(wspace=0.34, width_ratios=[0.82, 1.1]))

    ax = axes[0]
    nums = [tm["baseline"]["asr"], tm["patched"]["asr"]]
    vals = [100.0 * x / 20 for x in nums]
    ax.bar([0, 1], vals, color=[OK["verm"], OK["blue"]], width=0.55, linewidth=0)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.6, "%d/20 (%.1f)" % (nums[i], v), ha="center", fontsize=6.5)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["M1 only", "+ auth layer"], fontsize=7)
    ax.set_ylabel("meta ASR (%)")
    ax.set_ylim(0, 22)
    ax.set_yticks([0, 5, 10, 15, 20])
    ax.grid(axis="y")
    ax.text(0.5, 0.87, "Fisher p=0.231 (n=20)", transform=ax.transAxes,
            ha="center", fontsize=6.3, color=OK["dark"])
    tag(ax, "(a)", dx=-0.22)

    ax = axes[1]
    groups = ["Clean\ncompletion", "Clean false\nblock (call)"]
    before = [100 * sl["baseline"]["util"] / 21,
              100 * sl["baseline"]["cl_hits_block"] / sl["baseline"]["cl_hits"]]
    after = [100 * sl["patched"]["util"] / 21,
             100 * sl["patched"]["cl_hits_block"] / sl["patched"]["cl_hits"]]
    x = np.arange(len(groups))
    ax.bar(x - 0.17, before, width=0.32, color=OK["verm"], label="M1 only", linewidth=0)
    ax.bar(x + 0.17, after, width=0.32, color=OK["blue"], label="M1 + auth layer",
           linewidth=0)
    for i in range(len(groups)):
        ax.text(x[i] - 0.17, before[i] + 1.4, "%.1f" % before[i], ha="center", fontsize=6.3)
        ax.text(x[i] + 0.17, after[i] + 1.4, "%.1f" % after[i], ha="center", fontsize=6.3)
    ax.set_xticks(x)
    ax.set_xticklabels(groups, fontsize=7)
    ax.set_ylabel("slack (%)")
    ax.set_ylim(0, 82)
    ax.grid(axis="y")
    ax.legend(frameon=False, fontsize=6.4, loc="upper right", handlelength=1.0)
    tag(ax, "(b)", dx=-0.16)

    save_fig(fig, "app_fig9_patch_before_after")
    emit_fig_csv("app_fig9_patch_before_after",
                 ["panel", "setting", "metric", "num", "den", "pct"],
                 [["a", "meta, M1", "asr", nums[0], 20, vals[0]],
                  ["a", "meta, patched", "asr", nums[1], 20, vals[1]],
                  ["b", "slack, M1", "utility", sl["baseline"]["util"], 21, before[0]],
                  ["b", "slack, patched", "utility", sl["patched"]["util"], 21, after[0]],
                  ["b", "slack, M1", "false_block", sl["baseline"]["cl_hits_block"],
                   sl["baseline"]["cl_hits"], before[1]],
                  ["b", "slack, patched", "false_block", sl["patched"]["cl_hits_block"],
                   sl["patched"]["cl_hits"], after[1]]])


# ------------------------------------------------------------------ app fig 10
def fig10_app():
    from ft_common import md_rows

    rows = md_rows("reports/b6_adaptive.md", r"^## 3\. 关键证据", r"^## 4\.")
    flips = []
    for r in rows:
        if len(r) >= 3 and r[0].startswith("user_task"):
            a = r[1].replace("*", "").strip()
            b = r[2].replace("*", "").strip()
            if a in ("DENY", "ALLOW") and b in ("DENY", "ALLOW") and a != b:
                flips.append((r[0].replace("user_task_", ""), a, b))
    down = [f[0] for f in flips if f[1] == "DENY" and f[2] == "ALLOW"]
    down_txt = " / ".join("task " + x for x in down)

    boxes = [
        ("Evidence 1: payload block removed",
         "seed 42 probe, same call: P0 DENY, P1 ALLOW once the <INFORMATION> block is "
         "deleted."),
        ("Evidence 2: authority claim inserted",
         "meta variant, %s: DENY becomes ALLOW under a \u201cpre-approved by the guard\u201d "
         "sentence." % down_txt),
        ("Evidence 3: task-blind control",
         "Attribution: 20/26 non-payload denials are also denied by the task-blind M0 "
         "model."),
    ]

    fig, ax = plt.subplots(figsize=(7.0, 3.0))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 6)
    ax.axis("off")

    for i, (title, body) in enumerate(boxes):
        x0 = 0.15 + i * 3.95
        ax.add_patch(FancyBboxPatch((x0, 2.35), 3.7, 3.35,
                                    boxstyle="round,pad=0.05,rounding_size=0.08",
                                    linewidth=0.8, edgecolor=OK["grey"],
                                    facecolor="#f5f7f9"))
        ax.text(x0 + 0.18, 5.42, textwrap.fill(title, 27), fontsize=6.8, va="top",
                color=OK["dark"], fontweight="bold", linespacing=1.25)
        ax.text(x0 + 0.18, 4.15, textwrap.fill(body, 30), fontsize=6.3, va="top",
                color=OK["dark"], linespacing=1.4)
        ax.annotate("", xy=(6.0, 1.52), xytext=(x0 + 1.85, 2.3),
                    arrowprops=dict(arrowstyle="->", color=OK["grey"], lw=0.7,
                                    shrinkA=0, shrinkB=2))

    ax.add_patch(FancyBboxPatch((1.1, 0.2), 9.8, 1.12,
                                boxstyle="round,pad=0.05,rounding_size=0.08",
                                linewidth=1.0, edgecolor=OK["blue"], facecolor="#eaf2f8"))
    ax.text(6.0, 0.76, "One mechanism: the decision tracks the payload block and the\n"
                       "action prior, not the user's authorization",
            ha="center", va="center", fontsize=7.2, color=OK["blue"], linespacing=1.35)

    save_fig(fig, "app_fig10_three_evidence")
    emit_fig_csv("app_fig10_three_evidence", ["evidence", "content"],
                 [["1", "seed42 P0 DENY -> P1 ALLOW"],
                  ["2", "%s DENY -> ALLOW under an authority claim" % down_txt],
                  ["3", "20/26 non-payload denials also denied by task-blind M0"]])


def main():
    for fn in (fig1, fig4, fig6, fig3_app, fig5_app, fig7_app, fig8_app, fig9_app,
               fig10_app):
        fn()


if __name__ == "__main__":
    main()
