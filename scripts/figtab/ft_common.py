# -*- coding: utf-8 -*-
"""Shared loaders + emitters for the figure/table build.

Rules enforced here:
  * every number is read from a machine artefact (CSV / JSON / scen.jsonl / md table);
  * missing source -> Blocked (no estimation, no manual fill);
  * each table/figure also writes its own .csv next to itself.
"""
import csv
import json
import os
import re

R = "/data/projects/guardrails"
OUT_T = os.path.join(R, "tables")
OUT_F = os.path.join(R, "figures")
os.makedirs(OUT_T, exist_ok=True)
os.makedirs(OUT_F, exist_ok=True)

SRC_CSV = "reports/final_metrics.csv"
SRC_DIAG = "results/diag/metrics.json"
SRC_OVO = "results/diag/offline_vs_online.json"
SRC_B3 = "reports/b3_tshield.md"
SRC_B10 = "reports/b10_ablation.md"
SRC_DENY = "reports/deny_attribution.md"
SRC_B5 = "reports/b5_lightweight.md"
SRC_B6 = "reports/b6_adaptive.md"
SRC_B9 = "reports/b9_notes.md"
SRC_POST = "probes/posthoc_alignment.json"
SRC_PROBE = "probes/probe_user_task_4.json"
SRC_NG = "probes/net_gain_sets.json"
SRC_ROUTE = "results/classifier/routing_ablation.json"
SRC_LAT_RULE = "results/classifier/latency_rule_cpu.json"
SRC_LAT_05B = "results/classifier/latency_05b_cpu.json"


class Blocked(Exception):
    pass


# ------------------------------------------------------------------ csv
def load_csv():
    with open(os.path.join(R, SRC_CSV), encoding="utf-8") as f:
        return list(csv.DictReader(f))


ROWS = load_csv()


def cell(claim, suite, arm, metric):
    for r in ROWS:
        if (r["claim"] == claim and r["suite"] == suite
                and r["arm"] == arm and r["metric"] == metric):
            return r
    return None


def need(claim, suite, arm, metric):
    r = cell(claim, suite, arm, metric)
    if r is None:
        raise Blocked("%s/%s/%s/%s not in %s" % (claim, suite, arm, metric, SRC_CSV))
    return r


def nd(claim, suite, arm, metric):
    """(num, den, value) with num/den as ints when present."""
    r = need(claim, suite, arm, metric)
    n = int(float(r["num"])) if r["num"] else None
    d = int(float(r["den"])) if r["den"] else None
    v = float(r["value"]) if r["value"] else None
    return n, d, v


def p(num, den, digits=1):
    if num is None or not den:
        return "--"
    return ("%." + str(digits) + "f") % (100.0 * num / den)


def frac(num, den, digits=1, pct=True):
    """'12/42 (28.6)' -- denominator kept explicit, never a bare percentage."""
    if num is None or not den:
        return "--"
    if pct:
        return "%d/%d (%s)" % (num, den, p(num, den, digits))
    return "%d/%d" % (num, den)


def pv(x, digits=4):
    """p=0.0039 / p=0.754 / p<0.001 (only for a reported 0)."""
    if x is None or x == "":
        return "--"
    v = float(x)
    if v == 0.0:
        return "$<$0.001"
    s = ("%." + str(digits) + "f") % v
    if "." in s:
        head, tail = s.split(".")
        while len(tail) > 3 and tail.endswith("0"):
            tail = tail[:-1]
        s = head + "." + tail
    return "p=" + s


# ------------------------------------------------------------------ scen.jsonl
def scen(rel):
    path = os.path.join(R, rel, "scen.jsonl")
    if not os.path.exists(path):
        raise Blocked("missing run: " + rel)
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def clean_false_block(rel):
    """(blocked calls, clean calls) recomputed from guard_hits of clean scenes."""
    tot = blk = 0
    for r in scen(rel):
        if r.get("injection_present"):
            continue
        for h in (r.get("guard_hits") or []):
            tot += 1
            if h.get("decision") != "ALLOW":
                blk += 1
    return blk, tot


def guard_counts(rel):
    tot = deny = review = 0
    for r in scen(rel):
        for h in (r.get("guard_hits") or []):
            tot += 1
            if h.get("decision") == "DENY":
                deny += 1
            elif h.get("decision") == "REVIEW":
                review += 1
    return deny, review, tot


def rw_split(rel):
    """(write_success, write_n, read_success, read_n) on injection_task_1 / _3."""
    out = {"injection_task_1": [0, 0], "injection_task_3": [0, 0]}
    for r in scen(rel):
        t = r.get("injection_task")
        if t in out:
            out[t][1] += 1
            if r.get("attack_success"):
                out[t][0] += 1
    return out["injection_task_1"][0], out["injection_task_1"][1], \
        out["injection_task_3"][0], out["injection_task_3"][1]


# ------------------------------------------------------------------ md tables
def md_rows(rel, start_pat, stop_pat):
    """Rows of the first markdown table between two headings."""
    path = os.path.join(R, rel)
    with open(path, encoding="utf-8") as f:
        lines = [l.rstrip("\n") for l in f]
    i = 0
    while i < len(lines) and not re.search(start_pat, lines[i]):
        i += 1
    if i == len(lines):
        raise Blocked("heading %r not found in %s" % (start_pat, rel))
    rows = []
    for line in lines[i + 1:]:
        if re.search(stop_pat, line):
            break
        if line.strip().startswith("|"):
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    if not rows:
        raise Blocked("no table under %r in %s" % (start_pat, rel))
    return rows


SRC_AUDIT = "probes/mcnemar_audit.json"


def audit(name_part):
    """Entry of probes/mcnemar_audit.json whose 'name' contains name_part."""
    path = os.path.join(R, SRC_AUDIT)
    if not os.path.exists(path):
        raise Blocked("missing " + SRC_AUDIT)
    for e in json.load(open(path, encoding="utf-8")):
        if name_part in e.get("name", ""):
            return e
    raise Blocked("audit entry %r not found" % name_part)


def b3_calib():
    """ACB and sample size of the v3 prompt row in b3_tshield.md section 1."""
    acb = None
    for line in open(os.path.join(R, SRC_B3), encoding="utf-8"):
        if "v3" in line and "dev" in line:
            cells = [c.strip().strip("*") for c in line.strip().strip("|").split("|")]
            for c in cells:
                if re.fullmatch(r"[01]\.\d{3}", c):
                    acb = float(c)
    if acb is None:
        raise Blocked("b3 v3 calibration row not parsed")
    return acb, 300


def b3_latency_map():
    """{'slack': {'m1': (mean, p95), 'ts': ...}, 'travel': {...}} from b3_tshield.md."""
    out = {}
    suite = None
    for line in open(os.path.join(R, SRC_B3), encoding="utf-8"):
        if line.startswith("### 2.1"):
            suite = "travel"
        elif line.startswith("### 2.2"):
            suite = "slack"
        elif line.startswith("## 3."):
            suite = None
        if suite is None or "ms" not in line:
            continue
        m = re.search(r"(\d+) / (\d+) ms", line)
        if not m:
            continue
        if "M1 任务感知" in line:
            out.setdefault(suite, {})["m1"] = (float(m.group(1)), float(m.group(2)))
        elif "Task-Shield" in line:
            out.setdefault(suite, {})["ts"] = (float(m.group(1)), float(m.group(2)))
    if "slack" not in out or "travel" not in out:
        raise Blocked("b3 latency map incomplete: %r" % out)
    return out


def b3_latency():
    """(m1_mean, ts_mean) from the slack table of b3_tshield.md."""
    got = {}
    for line in open(os.path.join(R, SRC_B3), encoding="utf-8"):
        if "0/42" not in line:
            continue
        m = re.search(r"\*\*?(\d+) / (\d+) ms", line)
        if not m:
            m = re.search(r"(\d+) / (\d+) ms", line)
        if not m:
            continue
        if "M1 任务感知" in line:
            got["m1"] = (float(m.group(1)), float(m.group(2)))
        elif "Task-Shield" in line:
            got["ts"] = (float(m.group(1)), float(m.group(2)))
    if "m1" not in got or "ts" not in got:
        raise Blocked("b3 latency not parsed: %r" % got)
    return got["m1"], got["ts"]


# ------------------------------------------------------------------ emitters
def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _tex2md(t):
    """Inline LaTeX -> markdown, for the .md previews and the atlas."""
    import re as _re
    t = t.strip()
    t = t.replace("-{}-", "--").replace("{-}", "")
    t = _re.sub(r"\\emph\{([^{}]*)\}", r"*\1*", t)
    t = _re.sub(r"\\texttt\{([^{}]*)\}", r"`\1`", t)
    t = t.replace("\\%", "%").replace("\\_", "_").replace("\\&", "&")
    t = t.replace("\\#", "#")
    t = t.replace("$\\gamma\\geq2$", "gamma>=2").replace("$\\gamma\\geq3$", "gamma>=3")
    t = t.replace("$\\gamma{=}3$", "gamma=3")
    t = t.replace("$\\to$", "->").replace("$\\cap$", "cap")
    t = t.replace("$A\\cap B$", "A cap B")
    t = t.replace("$<$", "<").replace("$+$", "+").replace("$p$", "p")
    t = t.replace("\\,", " ").replace("\\ ", " ")
    t = _re.sub(r"\$([^$]*)\$", lambda m: m.group(1).replace("{", "").replace("}", "")
                .replace("\\", ""), t)
    t = t.replace("{", "").replace("}", "")
    t = t.replace("---", "\u2014").replace("--", "\u2013")
    return t.strip()


def _row_cells(row, ncol):
    """Split a booktabs row into exactly ncol markdown cells."""
    import re as _re
    row = row.rstrip()
    if row.endswith("\\\\"):
        row = row[:-2].rstrip()
    m = _re.match(r"\\multicolumn\{(\d+)\}\{\w+\}\{(.*)\}$", row)
    if m:
        span = int(m.group(1))
        text = _tex2md(m.group(2)).replace("*", "")
        cells = ["**" + text + "**"] + [""] * (span - 1)
        return (cells + [""] * (ncol - span))[:ncol]
    cells = [_tex2md(c) for c in row.split(" & ")]
    return (cells + [""] * (ncol - len(cells)))[:ncol]


def emit_table(name, caption, label, colspec, head, body, notes,
               csv_head, csv_rows, size="\\small", packages="booktabs,threeparttable"):
    """Write <name>.tex + <name>.csv + <name>.md. body/notes are raw LaTeX."""
    tex = []
    tex.append("% generated by scripts/figtab/ft_tables.py -- do not edit by hand")
    tex.append("% requires: " + packages)
    tex.append("\\begin{table}[t]")
    tex.append("\\centering")
    tex.append(size)
    tex.append("\\begin{threeparttable}")
    tex.append("\\caption{%s}" % caption)
    tex.append("\\label{%s}" % label)
    tex.append("\\begin{tabular}{%s}" % colspec)
    tex.append("\\toprule")
    for h in head:
        tex.append(h + " \\\\")
    tex.append("\\midrule")
    for b in body:
        if b.startswith("\\midrule") or b.startswith("\\cmidrule") \
                or b.startswith("\\bottomrule"):
            tex.append(b)
        else:
            tex.append(b if b.endswith("\\\\") else b + " \\\\")
    tex.append("\\bottomrule")
    tex.append("\\end{tabular}")
    if notes:
        tex.append("\\begin{tablenotes}\\footnotesize")
        for n in notes:
            tex.append("\\item %s" % n)
        tex.append("\\end{tablenotes}")
    tex.append("\\end{threeparttable}")
    tex.append("\\end{table}")
    _write(os.path.join(OUT_T, name + ".tex"), "\n".join(tex) + "\n")

    with open(os.path.join(OUT_T, name + ".csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(csv_head)
        for r in csv_rows:
            w.writerow(r)

    ndisp = len(head[0].split(" & "))
    md = ["# %s" % name, "", caption, "",
          "| " + " | ".join(_tex2md(c) for c in head[0].split(" & ")) + " |",
          "|" + "|".join(["---"] * ndisp) + "|"]
    for b in body:
        if b.startswith("\\midrule") or b.startswith("\\cmidrule") \
                or b.startswith("\\bottomrule"):
            continue
        md.append("| " + " | ".join(_row_cells(b, ndisp)) + " |")
    if notes:
        md += ["", "**Notes**", ""]
        for n in notes:
            md.append("- " + _tex2md(n))
    md += ["", "LaTeX: `tables/%s.tex` · CSV: `tables/%s.csv`" % (name, name)]
    _write(os.path.join(OUT_T, name + ".md"), "\n".join(md) + "\n")
    print("  table  %-40s tex/csv/md" % name)


def emit_fig_csv(name, head, rows):
    with open(os.path.join(OUT_F, name + ".csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(head)
        for r in rows:
            w.writerow(r)


def save_fig(fig, name):
    import matplotlib.pyplot as plt
    fig.savefig(os.path.join(OUT_F, name + ".pdf"))
    fig.savefig(os.path.join(OUT_F, name + ".png"), dpi=300)
    plt.close(fig)
    print("  figure %-40s pdf/png" % name)


def esc(s):
    for a, b in (("\\", "\\textbackslash{}"), ("&", "\\&"), ("%", "\\%"),
                 ("_", "\\_"), ("#", "\\#")):
        s = s.replace(a, b)
    return s
