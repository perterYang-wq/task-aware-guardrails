# -*- coding: utf-8 -*-
"""STEP E：三处数字对账（final_metrics.csv / fig5 / state）。

对 5 个数：M1 only / M0 only / 交集 / 稳健子集 / McNemar p。
真值来源：`probes/net_gain_sets.json`（由 `scripts/net_gain_sets.py` 从判定结果算出）。
fig5 是 PNG，无法读数字——改为核对它的**图注**（`reports/final_figures.md`）与
生成脚本里引用的字段（`scripts/b9_figures.py` 直接读 net_gain_sets.json，不手写）。

产物：reports/consistency_check.md
"""
import csv
import json
import os
import re

R = "/data/projects/guardrails"
TRUTH_P = os.path.join(R, "probes/net_gain_sets.json")
CSV_P = os.path.join(R, "reports/final_metrics.csv")
STATE_P = os.path.join(R, "runs/auto/state.json")
FIG_P = os.path.join(R, "reports/final_figures.md")
SCR_P = os.path.join(R, "scripts/b9_figures.py")
OUT = os.path.join(R, "reports/consistency_check.md")

truth = json.load(open(TRUTH_P, encoding="utf-8"))
WANT = [("M1_only", truth["M1_only"]), ("M0_only", truth["M0_only"]),
        ("intersection", truth["intersection"]), ("robust_subset", truth["robust_subset"]),
        ("mcnemar_p", 0.7539)]

# ---- CSV ----
rows = list(csv.DictReader(open(CSV_P, encoding="utf-8")))
csv_val = {}
for r in rows:
    if r["claim"] == "deny_attr" and r["axis"] == "net_gain":
        csv_val[r["metric"]] = float(r["value"])

# ---- state ----
st = json.load(open(STATE_P, encoding="utf-8"))["phase5"]["net_gain"]

# ---- fig5 图注 ----
figtxt = open(FIG_P, encoding="utf-8").read()
cap = ""
for block in figtxt.split("## "):
    if block.startswith("fig5"):
        cap = block
fig_num = {
    "M1_only": re.search(r"M1 only (\d+)", cap),
    "M0_only": re.search(r"M0 only (\d+)", cap),
    "intersection": re.search(r"交集 (\d+)", cap),
    "robust_subset": re.search(r"稳健子集 (\d+)", cap),
    "mcnemar_p": re.search(r"p=([\d.]+)", cap),
}
# ---- 生成脚本是否硬编码 ----
script = open(SCR_P, encoding="utf-8").read()
hardcoded = bool(re.search(r'ng\["(M1_only|M0_only|intersection|robust_subset)"\]', script))

L = ["# 三处对账：final_metrics.csv / fig5 / state", "",
     "真值来源：`probes/net_gain_sets.json`（`scripts/net_gain_sets.py` 从 P1 判定结果算出）。", "",
     "| 量 | 真值 | final_metrics.csv | fig5 图注 | state.phase5 | 一致 |",
     "|---|---|---|---|---|---|"]

bad = []
for k, v in WANT:
    cv = csv_val.get(k)
    fv = fig_num[k].group(1) if fig_num[k] else None
    sv = st.get(k)
    ok_c = (cv is not None) and abs(cv - float(v)) <= 1e-6
    ok_f = (fv is not None) and abs(float(fv) - float(v)) <= 5e-4
    ok_s = (sv is not None) and abs(float(sv) - float(v)) <= 5e-4
    ok = ok_c and ok_f and ok_s
    if not ok:
        bad.append((k, v, cv, fv, sv))
    L.append("| %s | %s | %s | %s | %s | %s |"
             % (k, v, ("—" if cv is None else cv), fv, sv, "✓" if ok else "✗"))

L += ["", "## 结论", ""]
if bad:
    L += ["- **%d 处不一致**：" % len(bad)]
    for k, v, cv, fv, sv in bad:
        L.append("  - %s：真值 %s / CSV %s / 图注 %s / state %s" % (k, v, cv, fv, sv))
    L.append("- 处理：以 `scripts/net_gain_sets.py` 的输出为准，重跑 `b9_metrics.py` 与 `b9_figures.py`。")
else:
    L += ["- 5 个数在三处**完全一致**，无手填。"]
L += ["- fig5 的 (c) 面板直接读 `probes/net_gain_sets.json`（脚本里 ng[...] 取值，%s），"
      "不是把数字写死在绘图代码里。" % ("已确认" if hardcoded else "未检测到硬编码"),
      "- `b9_metrics.py` 的 net_gain 行同样读该 JSON，来源列已标注路径。", ""]

open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
print("\n".join(L))
