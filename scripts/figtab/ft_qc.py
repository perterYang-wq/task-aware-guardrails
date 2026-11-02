# -*- coding: utf-8 -*-
"""Self-check for the figure/table pack: files, LaTeX hygiene, number tracing."""
import csv
import json
import os
import re

R = "/data/projects/guardrails"
T = os.path.join(R, "tables")
F = os.path.join(R, "figures")

MAIN_T = ["tab1_three_suites_three_arms", "tab2_vs_tshield", "tab4_rule_three_arms",
          "tab6_deny_attribution"]
APP_T = ["app_tab3_recipe_ladder", "app_tab5_probe_matrix", "app_tab7_adaptive",
         "app_tab8_posthoc_patch", "app_tab9_cost", "app_tab10_seven_axis"]
MAIN_F = ["fig1_dinj_pra_acb", "fig4_recipe_ladder", "fig6_probe_heatmap"]
APP_F = ["app_fig3_suites_arms", "app_fig5_seven_axis", "app_fig7_routing",
         "app_fig8_cost_frontier", "app_fig9_patch_before_after",
         "app_fig10_three_evidence"]

lines = []
ok = 0
bad = []


def check(name, cond, detail=""):
    global ok
    if cond:
        ok += 1
        lines.append("PASS  %-52s %s" % (name, detail))
    else:
        bad.append(name)
        lines.append("FAIL  %-52s %s" % (name, detail))


def exists(p):
    return os.path.exists(p)


# 1 files
for n in MAIN_T + APP_T:
    check("table %s (tex/csv/md)" % n,
          all(exists(os.path.join(T, n + e)) for e in (".tex", ".csv", ".md")))
for n in MAIN_F + APP_F:
    check("figure %s (pdf/png/csv)" % n,
          all(exists(os.path.join(F, n + e)) for e in (".pdf", ".png", ".csv")))

# 2 latex hygiene
for n in MAIN_T + APP_T:
    tex = open(os.path.join(T, n + ".tex"), encoding="utf-8").read()
    envs = re.findall(r"\\(begin|end)\{(\w+)\}", tex)
    bal = all(tex.count("\\begin{%s}" % e) == tex.count("\\end{%s}" % e)
              for e in ("table", "tabular", "threeparttable", "tablenotes"))
    check("latex %s balanced + booktabs" % n,
          bal and "\\toprule" in tex and "\\midrule" in tex and "\\bottomrule" in tex
          and "\\midrule \\\\" not in tex)

# 3 numbers trace back to source
rows = list(csv.DictReader(open(os.path.join(R, "reports/final_metrics.csv"),
                               encoding="utf-8")))


def get(claim, suite, arm, metric):
    for r in rows:
        if (r["claim"], r["suite"], r["arm"], r["metric"]) == (claim, suite, arm, metric):
            return int(float(r["num"])), int(float(r["den"]))
    return None


t1 = list(csv.DictReader(open(os.path.join(T, "tab1_three_suites_three_arms.csv"),
                             encoding="utf-8")))
d = {(r["suite"], r["arm"]): r for r in t1}
check("tab1 slack M1 ASR = 0/42", (d[("slack", "M1")]["asr_num"],
                                   d[("slack", "M1")]["asr_den"]) == ("0", "42"))
check("tab1 travel M1 ASR = 1/40", (d[("travel", "M1")]["asr_num"],
                                    d[("travel", "M1")]["asr_den"]) == ("1", "40"))
check("tab1 slack M1 false block = 4/123", (d[("slack", "M1")]["fb_num"],
                                            d[("slack", "M1")]["fb_den"]) == ("4", "123"))

t4 = list(csv.DictReader(open(os.path.join(T, "tab4_rule_three_arms.csv"), encoding="utf-8")))
r0 = t4[0]
check("tab4 rule read-type = 12/21", (r0["read_num"], r0["read_den"]) == ("12", "21"))
check("tab4 rule write-type = 0/21", (r0["write_num"], r0["write_den"]) == ("0", "21"))
check("tab4 M1+rule ASR p is n/a", "n/a" in t4[2]["p_asr"])

t6 = list(csv.DictReader(open(os.path.join(T, "tab6_deny_attribution.csv"), encoding="utf-8")))
ng = json.load(open(os.path.join(R, "probes/net_gain_sets.json"), encoding="utf-8"))
check("tab6 sets = json (6/4/20/2)",
      (int(t6[2]["m1_only"]), int(t6[2]["m0_only"]), int(t6[2]["intersection"]),
       int(t6[2]["robust"])) == (ng["M1_only"], ng["M0_only"], ng["intersection"],
                                 ng["robust_subset"]))

f1 = list(csv.DictReader(open(os.path.join(F, "fig1_dinj_pra_acb.csv"), encoding="utf-8")))
pts = {r["arm"]: (float(r["x"]), float(r["y"])) for r in f1 if r["panel"] == "b"}
check("fig1b 0.883->17.0", abs(pts["p1_3b_task_s0"][0] - 0.8833) < 1e-3
      and abs(pts["p1_3b_task_s0"][1] - 16.98) < 0.02)
check("fig1b 0.856->21.4", abs(pts["p1_15b_task_s0"][0] - 0.8556) < 1e-3
      and abs(pts["p1_15b_task_s0"][1] - 21.38) < 0.02)
check("fig1b 0.794->41.5", abs(pts["p1_15b_nt_s0"][0] - 0.7944) < 1e-3
      and abs(pts["p1_15b_nt_s0"][1] - 41.51) < 0.02)

f4 = list(csv.DictReader(open(os.path.join(F, "fig4_recipe_ladder.csv"), encoding="utf-8")))
check("fig4 ladder = 50.0/61.9 ... 0.0/66.7",
      [round(float(r["asr_pct"]), 1) for r in f4] == [50.0, 11.9, 9.5, 0.0]
      and [round(float(r["util_pct"]), 1) for r in f4] == [61.9, 47.6, 33.3, 66.7])

f6 = list(csv.DictReader(open(os.path.join(F, "fig6_probe_heatmap.csv"), encoding="utf-8")))
deny = sum(1 for r in f6 if r["verdict"] == "DENY")
allow = sum(1 for r in f6 if r["verdict"] == "ALLOW")
check("fig6 15 cells, 3 seeds x 5 variants", len(f6) == 15)
check("fig6 verdict counts (DENY 5 / ALLOW 10)", deny == 5 and allow == 10,
      "deny=%d allow=%d" % (deny, allow))

# 4 anchor inputs must predate this session (23:20 on 2026-11-02)
import datetime
from ft_common import (SRC_CSV, SRC_DIAG, SRC_OVO, SRC_PROBE, SRC_ROUTE,
                       SRC_LAT_RULE, SRC_LAT_05B)
THRESH = datetime.datetime(2026, 11, 2, 23, 20).timestamp()
anchors = [SRC_CSV, SRC_DIAG, SRC_OVO, SRC_PROBE, SRC_ROUTE, SRC_LAT_RULE,
           SRC_LAT_05B, "probes/net_gain_sets.json", "probes/posthoc_alignment.json",
           "results/e2e/slack/m2_HB_s0_inj1-3/scen.jsonl"]
dirty = [a for a in anchors
         if os.path.exists(os.path.join(R, a)) and os.path.getmtime(os.path.join(R, a)) > THRESH]
check("anchor inputs untouched (mtime < 23:20)", not dirty, ",".join(dirty))
lines.append("INFO  runs/auto/state.json mtime = %s (concurrent mechanism-probe run "
             "appended mechanism_probe_v41flash; not touched by this task)"
             % datetime.datetime.fromtimestamp(
                 os.path.getmtime(os.path.join(R, "runs/auto/state.json"))).isoformat(" "))

lines.append("")
lines.append("TOTAL pass=%d fail=%d" % (ok, len(bad)))
if bad:
    lines.append("failed: " + ", ".join(bad))
open(os.path.join(R, "reports/figtab_qc.txt"), "w", encoding="utf-8").write(
    "\n".join(lines) + "\n")
print("\n".join(lines))
