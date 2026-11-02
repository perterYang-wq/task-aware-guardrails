# -*- coding: utf-8 -*-
"""Build the 4 main-text tables + 6 appendix tables (tex/csv/md)."""
import json
import os
import re

from ft_common import (Blocked, OUT_T, R, SRC_B10, SRC_B3, SRC_B5, SRC_B6, SRC_B9,
                       audit,
                       SRC_DENY, SRC_LAT_05B, SRC_LAT_RULE, SRC_NG, SRC_POST,
                       SRC_PROBE, b3_calib, b3_latency, clean_false_block, emit_table, frac,
                       guard_counts, md_rows, nd, p, pv, rw_split, scen)

SLACK = "results/e2e/slack/m2_HB_s0_inj1-3"
SLACK_M0 = "results/e2e/slack/m2_HBnt_s0_b1_inj1-3"
SLACK_S = "results/e2e/slack/m2_S_s0_b10_inj1-3"
SLACK_RULE = "results/e2e/slack/hard_b10_inj1-3"
SLACK_M1RULE = "results/e2e/slack/m2_HB_s0_b10hr_inj1-3"
SLACK_RG = "results/e2e/slack/rule-gamma_inj1-3"
SLACK_TS = "results/e2e/slack/tshield_b3_inj1-3"
TRAVEL = "results/e2e/travel/m2_HB_s0_calls_inj0-1"
TRAVEL_M0 = "results/e2e/travel/m2_HBnt_s0_inj0-1"
BANK = "results/e2e/banking/m2_HB_s0_inj5-7"
BANK_M0 = "results/e2e/banking/m2_HBnt_s0_inj5-7"


def t1():
    rows, csv_rows = [], []
    groups = [
        ("banking", "32 attack / 16 clean", "C2_task_aware", BANK, BANK_M0),
        ("slack", "42 attack / 21 clean", "C2_task_aware", SLACK, SLACK_M0),
        ("travel", "40 attack / 20 clean", "C2_task_aware", TRAVEL, TRAVEL_M0),
    ]
    for suite, proto, claim, run_m1, run_m0 in groups:
        rows.append("\\multicolumn{4}{l}{\\emph{%s}: %s scenarios}" % (suite, proto))
        for arm, run in (("E0", None), ("M0", run_m0), ("M1", run_m1)):
            a_n, a_d, _ = nd(claim, suite, arm, "asr")
            u_n, u_d, _ = nd(claim, suite, arm, "utility")
            if run is None:
                fb = "--"
                fbn, fbd = None, None
            else:
                fbn, fbd = clean_false_block(run)
                fb = frac(fbn, fbd)
            rows.append(" & ".join([arm, frac(a_n, a_d), frac(u_n, u_d), fb]))
            csv_rows.append([suite, proto, arm, a_n, a_d, p(a_n, a_d),
                             u_n, u_d, p(u_n, u_d), fbn, fbd, p(fbn, fbd),
                             "" if run is None else run])
        if suite != "travel":
            rows.append("\\midrule")

    notes = [
        "ASR and clean-task completion are scenario-level; clean false block is call-level "
        "over clean scenarios (recomputed from \\texttt{scen.jsonl} guard decisions).",
        "All rows: seed 0, guard GPU fp16, one execution boundary. Denominators are fixed by "
        "suite and never shared across suites.",
        "E0 has no guard, hence no call-level false block. banking: 29 clean calls (M0 1, M1 0).",
        "travel uses the 40-scenario protocol (inj0--1). Under the separate 80-scenario protocol "
        "(inj0--3) M0 is 13/80 and M1 is 1/80; those counts are not comparable with this table.",
    ]
    emit_table(
        "tab1_three_suites_three_arms",
        "End-to-end safety and utility of three arms on three suites.",
        "tab:three-suites",
        "lccc",
        ["Suite / arm & ASR (\\%) & Clean completion (\\%) & Clean false block (\\%)"],
        rows, notes,
        ["suite", "protocol", "arm", "asr_num", "asr_den", "asr_pct",
         "util_num", "util_den", "util_pct", "fb_num", "fb_den", "fb_pct", "run"],
        csv_rows,
    )


def t2():
    m1_lat, ts_lat = b3_latency()
    m_n, m_d, _ = nd("C2_task_aware", "slack", "M1", "asr")
    mu_n, mu_d, _ = nd("C2_task_aware", "slack", "M1", "utility")
    m1_deny, _, m1_hits = guard_counts(SLACK)

    t_n, t_d, _ = nd("C3_vs_prior", "slack", "tshield", "asr")
    tu_n, tu_d, _ = nd("C3_vs_prior", "slack", "tshield", "utility")
    ts_deny, _, ts_hits = guard_counts(SLACK_TS)
    ts_p = nd("C3_vs_prior", "slack", "tshield_vs_M1", "mcnemar_p_utility")[2]

    r_n, r_d, _ = nd("C3_vs_prior", "slack", "rule_gamma", "asr")
    ru_n, ru_d, _ = nd("C3_vs_prior", "slack", "rule_gamma", "utility")
    r_deny, _, r_hits = guard_counts(SLACK_RG)
    rule_lat = json.load(open(os.path.join(R, SRC_LAT_RULE), encoding="utf-8"))

    rows = [
        " & ".join(["M1 (1.5B guard, ours)", frac(m_n, m_d), frac(mu_n, mu_d),
                    "%d/%d" % (m1_deny, m1_hits),
                    "%d / %d" % (m1_lat[0], m1_lat[1]), "$+$4.1", "reference"]),
        " & ".join(["Task-Shield (7B judge)", frac(t_n, t_d), frac(tu_n, tu_d),
                    "%d/%d" % (ts_deny, ts_hits),
                    "%d / %d" % (ts_lat[0], ts_lat[1]), "0 (shares agent 7B)",
                    pv(ts_p)]),
        " & ".join(["ToolSafe", "not reproduced", "--", "--", "--", "--", "--"]),
        " & ".join(["String rule ($\\gamma{=}3$)", frac(r_n, r_d), frac(ru_n, ru_d),
                    "%d/%d" % (r_deny, r_hits),
                    "%.4f / %.4f" % (rule_lat["p50"], rule_lat["p95"]),
                    "0", "--"]),
    ]
    notes = [
        "slack, seed 0, GPU fp16, 42 attack / 21 clean scenarios; latency and decision counts "
        "come from the same runs as ASR and utility.",
        "Task-Shield latency is read from \\texttt{reports/b3\\_tshield.md} (slack table); "
        "the string rule runs on CPU (416 calls), so its latency column is not comparable "
        "with the two GPU rows.",
        "The only formally tested contrast is M1 vs Task-Shield on clean-task completion "
        "(McNemar exact, 9:0, p=0.0039); the string-rule arm is reported descriptively.",
        "Extra VRAM is guard-only: the 7B judge reuses the agent's weights, the 1.5B guard "
        "adds 4.1 GB. ToolSafe was not reproduced under this protocol, so no number is given.",
    ]
    emit_table(
        "tab2_vs_tshield",
        "Head-to-head against a 7B task-aware judge on slack.",
        "tab:vs-tshield",
        "lcccccc",
        ["Arm & ASR (\\%) & Clean completion (\\%) & DENY/checked & "
         "Latency mean/P95 (ms) & Extra VRAM (GB) & McNemar $p$"],
        rows, notes,
        ["arm", "asr_num", "asr_den", "asr_pct", "util_num", "util_den", "util_pct",
         "deny", "checked", "lat_mean_ms", "lat_p95_ms", "extra_vram_gb", "p_mcnemar"],
        [
            ["M1", m_n, m_d, p(m_n, m_d), mu_n, mu_d, p(mu_n, mu_d),
             m1_deny, m1_hits, m1_lat[0], m1_lat[1], 4.1, ""],
            ["Task-Shield 7B", t_n, t_d, p(t_n, t_d), tu_n, tu_d, p(tu_n, tu_d),
             ts_deny, ts_hits, ts_lat[0], ts_lat[1], 0.0, ts_p],
            ["ToolSafe", "", "", "", "", "", "", "", "", "", "", "", "not reproduced"],
            ["String rule gamma=3", r_n, r_d, p(r_n, r_d), ru_n, ru_d, p(ru_n, ru_d),
             r_deny, r_hits, rule_lat["p50"], rule_lat["p95"], 0.0, ""],
        ],
        size="\\small",
    )


def t4():
    a = {"rule": ("rule_only", SLACK_RULE), "m1": ("M1_block", SLACK),
         "m1r": ("M1_rule", SLACK_M1RULE)}
    rows, csv_rows = [], []
    # read/write split recomputed per run (write = injection_task_1, read = injection_task_3)
    for key, label in (("rule", "String rule only"), ("m1", "M1, model only"),
                       ("m1r", "M1 $+$ string rule")):
        arm, run = a[key]
        n, d, _ = nd("B10", "slack", arm, "asr")
        un, ud, _ = nd("B10", "slack", arm, "utility")
        fb_n, fb_d = clean_false_block(run)
        w_s, w_n, r_s, r_n = rw_split(run)
        if key == "rule":
            p_asr = pv(audit("纯硬规则 vs M1")["p_mcnemar"]) + " (McNemar)"
            p_ut = "--"
        elif key == "m1":
            p_asr, p_ut = "reference", "reference"
        else:
            p_asr = "n/a (no discordant pairs)"
            p_ut = pv(audit("效用（M1+硬规则 vs M1）")["p_mcnemar"]) + " (McNemar)"
        rows.append(" & ".join([label, frac(n, d), frac(w_s, w_n), frac(r_s, r_n),
                                frac(un, ud), frac(fb_n, fb_d), p_asr, p_ut]))
        csv_rows.append([label, n, d, p(n, d), w_s, w_n, p(w_s, w_n), r_s, r_n,
                         p(r_s, r_n), un, ud, p(un, ud), fb_n, fb_d, p(fb_n, fb_d),
                         p_asr, p_ut])

    notes = [
        "slack, seed 0, GPU fp16, 42 attack / 21 clean scenarios; all three arms share one "
        "execution boundary (the \\texttt{-{}-hard-rule} switch).",
        "Write-type = slack \\texttt{injection\\_task\\_1} (21 scenarios), read-type = "
        "\\texttt{injection\\_task\\_3} (21 scenarios), recomputed from guard decisions.",
        "The string rule blocks every write-type attack but leaves read-type at 12/21 --- "
        "identical to the unguarded baseline (E0, also 12/21).",
        "M1+rule vs M1 on ASR is 0:0, so no exact test exists; the audit's $p{=}1.0$ only "
        "records that nothing was testable, not that the arms are equivalent.",
        "McNemar exact: ASR rule-vs-M1 12:0 ($p{=}0.0005$; Fisher gives 0.0002); utility "
        "M1+rule-vs-M1 0:13 ($p{=}0.0002$).",
    ]
    emit_table(
        "tab4_rule_three_arms",
        "Where the gain comes from: string rules versus the model versus both (slack).",
        "tab:rule-arms",
        "lccccccc",
        ["Arm & ASR (\\%) & ASR, write & ASR, read & Clean completion (\\%) & "
         "Clean false block (\\%) & $p$ vs M1 (ASR) & $p$ vs M1 (utility)"],
        rows, notes,
        ["arm", "asr_num", "asr_den", "asr_pct", "write_num", "write_den", "write_pct",
         "read_num", "read_den", "read_pct", "util_num", "util_den", "util_pct",
         "fb_num", "fb_den", "fb_pct", "p_asr", "p_util"],
        csv_rows,
        size="\\footnotesize",
    )


def t6():
    m_n, _, _ = nd("deny_attr", "all", "M1", "deny_total")
    mp_n, _, _ = nd("deny_attr", "all", "M1", "payload_recognition")
    mn_n, _, _ = nd("deny_attr", "all", "M1", "non_payload_dependent")
    z_n, _, _ = nd("deny_attr", "all", "M0", "deny_total")
    zp_n, _, _ = nd("deny_attr", "all", "M0", "payload_recognition")
    zn_n, _, _ = nd("deny_attr", "all", "M0", "non_payload_dependent")

    ng = json.load(open(os.path.join(R, SRC_NG), encoding="utf-8"))
    p_ng = nd("deny_attr", "all", "M1_vs_M0", "mcnemar_p")[2]

    rows = [
        " & ".join(["M1 (task-aware)", "%d" % m_n, "%d" % mp_n,
                    "%d (%s)" % (mn_n, p(mn_n, m_n)), "--", "--", "--", "--", "--"]),
        " & ".join(["M0 (task-blind)", "%d" % z_n, "%d" % zp_n,
                    "%d (%s)" % (zn_n, p(zn_n, z_n)), "--", "--", "--", "--", "--"]),
        " & ".join(["Set difference", "--", "--", "--", "%d" % ng["intersection"],
                    "%d" % ng["M1_only"], "%d" % ng["M0_only"],
                    "%d" % ng["robust_subset"], pv(p_ng)]),
    ]
    notes = [
        "Same 34 DENY instances, re-scored on CPU fp32, greedy; this is a different "
        "precision from the GPU fp16 end-to-end runs.",
        "``Non-payload'' means the call is still denied after the whole "
        "\\texttt{<INFORMATION>} block is deleted (P1); it does not mean the input is free of "
        "attack content (17/34 keep payload entities, 6/34 are paraphrased).",
        "Columns 5--8 use the P1-expanded sets: $|A|{=}26$ (M1), $|B|{=}24$ (M0). The M0 "
        "\\emph{non-payload} count of 22 is the P0$\\cap$P1 subset and is not the same "
        "quantity as $|B|$.",
        "M0 covers 20/26 (76.9\\%) of the M1 non-payload denials, so 76.9\\% is a "
        "within-set agreement rate, not a recall.",
        "Net gain 6 vs 4, McNemar exact $p{=}0.754$; after removing 4 contaminated items "
        "the robust subset is 2.",
    ]
    emit_table(
        "tab6_deny_attribution",
        "Where the denials come from: payload recognition versus action prior.",
        "tab:deny-attribution",
        "lcccccccc",
        ["Arm & DENY total & Payload recog. & Non-payload (\\%) & $A\\cap B$ & "
         "M1 only & M0 only & Robust net gain & McNemar $p$"],
        rows, notes,
        ["arm", "deny_total", "payload", "non_payload", "non_payload_pct",
         "intersection", "m1_only", "m0_only", "robust", "p_mcnemar"],
        [["M1", m_n, mp_n, mn_n, p(mn_n, m_n), "", "", "", "", ""],
         ["M0", z_n, zp_n, zn_n, p(zn_n, z_n), "", "", "", "", ""],
         ["set-difference", "", "", "", "", ng["intersection"], ng["M1_only"],
          ng["M0_only"], ng["robust_subset"], p_ng]],
        size="\\footnotesize",
    )


def t3_app():
    rows, csv_rows = [], []
    arms = [("E0", "E0 (no guard)", "E0"), ("S", "S (standard SFT)", "S"),
            ("M0", "M0 (task-blind recipe)", "M0"), ("M1", "M1 (full recipe)", "M1_block")]
    for label, name, arm in arms:
        n, d, _ = nd("B10", "slack", arm, "asr")
        un, ud, _ = nd("B10", "slack", arm, "utility")
        if arm == "E0":
            r = None
        elif arm == "M1_block":
            r = clean_false_block(SLACK) + (None,)
        else:
            r = nd("B10", "slack", arm, "clean_false_block_call")
        fb = frac(r[0], r[1]) if r else "--"
        if arm == "E0":
            pa = pv(nd("C2_task_aware", "slack", "E0_vs_M1", "fisher_p_asr")[2])
            pu = pv(nd("C4_utility", "slack", "M1_vs_E0", "mcnemar_p_utility")[2])
            tst = "Fisher / McNemar"
        elif arm == "S":
            pa = pv(nd("B10", "slack", "S_vs_M1", "fisher_p_asr")[2])
            pu = pv(nd("B10", "slack", "S_vs_M1", "mcnemar_p_utility")[2])
            tst = "Fisher / McNemar"
        elif arm == "M0":
            pa = pv(nd("C2_task_aware", "slack", "M0_vs_M1", "fisher_p_asr")[2])
            pu = pv(nd("C4_utility", "slack", "M1_vs_M0", "mcnemar_p_utility")[2])
            tst = "Fisher / McNemar"
        else:
            pa = pu = "reference"
            tst = "--"
        rows.append(" & ".join([name, frac(n, d), frac(un, ud), fb, pa, pu, tst]))
        csv_rows.append([name, n, d, p(n, d), un, ud, p(un, ud),
                         "" if not r else r[0], "" if not r else r[1],
                         "" if not r else p(r[0], r[1]), pa, pu, tst])

    notes = [
        "slack, seed 0, GPU fp16, 42 attack / 21 clean scenarios, one execution boundary.",
        "$p$ columns are exact tests against M1: ASR with Fisher (E0, M0) or McNemar (S, 5:0); "
        "clean-task completion with McNemar (E0 1:0, S 0:4, M0 7:0).",
        "E0 vs M1 on clean completion is 1:0 ($p{=}1.0$): a one-case difference, not a "
        "utility gain.",
        "The 19.0\\% / 11.5\\% / 3.3\\% false-block cells have different denominators "
        "(116 / 113 / 123 calls) because each arm issues a different number of calls.",
    ]
    emit_table(
        "app_tab3_recipe_ladder",
        "Recipe ladder with exact denominators (backing table for Figure~4).",
        "tab:app-recipe",
        "lcccccc",
        ["Arm & ASR (\\%) & Clean completion (\\%) & Clean false block (\\%) & "
         "$p$ (ASR vs M1) & $p$ (utility vs M1) & Test"],
        rows, notes,
        ["arm", "asr_num", "asr_den", "asr_pct", "util_num", "util_den", "util_pct",
         "fb_num", "fb_den", "fb_pct", "p_asr", "p_util", "test"],
        csv_rows,
        size="\\footnotesize",
    )


def t5_app():
    d = json.load(open(os.path.join(R, SRC_PROBE), encoding="utf-8"))
    seeds = [("s0", "seed 0"), ("s42", "seed 42"), ("s123", "seed 123")]
    by_seed = {}
    for key, _ in seeds:
        by_seed[key] = {r["variant"].split()[0]: r for r in d["results"][key]}
    variants = [("P0", "P0 as-is"), ("P1", "P1 payload removed"), ("P2", "P2 recipient swapped"),
                ("P3", "P3 body truncated"), ("P4", "P4 tool swapped")]
    rows, csv_rows = [], []
    for v, name in variants:
        cells = []
        for key, _ in seeds:
            r = by_seed[key][v]
            cells.append("%s / %s" % (r["raw"], r["parsed"]))
            csv_rows.append([v, name, key, r["raw"], r["parsed"], r["n_in"], r["hist_len"]])
        rows.append(" & ".join([name] + cells))
    notes = [
        "Single scenario: travel \\texttt{user\\_task\\_4} with \\texttt{injection\\_task\\_1}, "
        "step 6 \\texttt{send\\_email} to \\texttt{jay@google.com}.",
        "CPU fp32, greedy, \\texttt{max\\_new\\_tokens=6}; the seed-123 P0 cell reproduces the "
        "end-to-end record (ALLOW).",
        "Cells are \\texttt{raw} / verdict. No REVIEW verdict occurs in this matrix, so the "
        "verdict is binary here.",
        "This table is the only admissible reading of the probe; the four ``explanation'' "
        "lines at the end of \\texttt{reports/probe\\_user\\_task\\_4.md} are DO-NOT-QUOTE.",
    ]
    emit_table(
        "app_tab5_probe_matrix",
        "Counterfactual probe matrix: five variants $\\times$ three seeds.",
        "tab:app-probe",
        "lccc",
        ["Variant & seed 0 & seed 42 & seed 123"],
        rows, notes,
        ["variant", "variant_name", "seed", "raw", "verdict", "n_in", "hist_len"],
        csv_rows,
        size="\\footnotesize",
    )


def _b6_table():
    rows = md_rows(SRC_B6, r"^## 2\. 结果", r"^## 3\.")
    out = {}
    for r in rows:
        if len(r) < 5 or r[0] in ("变形",) or set(r[0]) <= set("-: "):
            continue
        key = r[0].replace("*", "").strip().lower()
        m = re.search(r"(\d+)/20", r[1])
        mu = re.search(r"(\d+)/20", r[2])
        mp = None
        for c in r[3:6]:
            mm = re.fullmatch(r"[\d.]+", c.strip().replace("*", ""))
            if mm:
                mp = float(c.strip().replace("*", ""))
                break
        if not m:
            continue
        out[key] = (int(m.group(1)), int(mu.group(1)) if mu else None, mp)
    if not {"static", "meta", "obfusc"} <= set(out):
        raise Blocked("b6 section 2 table not parsed: %r" % sorted(out))
    return out


def _b6_flips():
    rows = md_rows(SRC_B6, r"^## 3\. 关键证据", r"^## 4\.")
    flips = []
    for r in rows:
        if len(r) < 4 or not r[0].startswith("user_task"):
            continue
        a = r[1].replace("*", "").strip()
        b = r[2].replace("*", "").strip()
        if a in ("DENY", "ALLOW") and b in ("DENY", "ALLOW") and a != b:
            flips.append((r[0], a, b))
    return flips


def t7_app():
    t = _b6_table()
    flips = _b6_flips()
    csv_rows = []

    def row(name, key, pcell, flip_txt):
        s, u, _ = t[key]
        rows = " & ".join([name, frac(s, 20), frac(u, 20) if u is not None else "--",
                           pcell, flip_txt])
        csv_rows.append([name, s, 20, u, 20, pcell, flip_txt])
        return rows

    meta_p = pv(nd("C7_adaptive", "travel", "meta_vs_static", "fisher_p_asr")[2])
    rt_p = pv(nd("C7_adaptive", "travel", "metaretrain_vs_meta", "fisher_p_asr")[2])
    rt_n, rt_d, _ = nd("C7_adaptive", "travel", "meta_retrain", "asr")

    down = [f for f in flips if f[1] == "DENY" and f[2] == "ALLOW"]
    up = [f for f in flips if f[1] == "ALLOW" and f[2] == "DENY"]
    flip_txt = "%d DENY$\\to$ALLOW (%s)" % (
        len(down), ", ".join(x[0].replace("user_task_", "t") for x in down))
    if up:
        flip_txt += "; %d ALLOW$\\to$DENY (%s)" % (
            len(up), ", ".join(x[0].replace("user_task_", "t") for x in up))

    body = [
        row("static", "static", "reference", "--"),
        row("meta", "meta", meta_p, flip_txt),
        row("obfusc", "obfusc", pv(t["obfusc"][2]), "no flip; t4 becomes blocked"),
        " & ".join(["meta, after retraining", frac(rt_n, rt_d), "--", rt_p,
                    "same three scenes; 6/20 scenes changed verdicts"]),
    ]
    notes = [
        "travel, 20 attack scenarios (\\texttt{injection\\_task\\_1}), seed 0, GPU fp16; "
        "meta and obfusc are attack-only runs, so clean-task completion is undefined there.",
        "static is a 60-scenario run (20 clean + 40 attack); only ASR on the same 20 "
        "injection scenarios is compared across the three variants.",
        "$p$ values are Fisher exact against static (meta 3/20 vs 1/20, obfusc 0/20 vs 1/20).",
        "3/20 vs 1/20 is not significant at $n{=}20$ ($p{=}0.605$); the pre-registered ratio "
        "criterion ($\\le$2/20) is still missed, and that is what the row records.",
        "Retraining leaves ASR at 3/20 ($p{=}1.0$) and the same three scenarios broken, "
        "although 6/20 verdict sequences change (\\texttt{reports/b6\\_meta\\_retrain.md}).",
    ]
    emit_table(
        "app_tab7_adaptive",
        "Adaptive attack variants and the retraining branch (travel).",
        "tab:app-adaptive",
        "lcccc",
        ["Guard & ASR (\\%) & Task completion (\\%) & Fisher $p$ & Per-call flips"],
        body, notes,
        ["guard", "asr_num", "asr_den", "util_num", "util_den", "p_fisher", "flips"],
        csv_rows,
        size="\\footnotesize",
    )


def t8_app():
    d = json.load(open(os.path.join(R, SRC_POST), encoding="utf-8"))
    tm = d["travel-meta"]
    sl = d["slack-static"]
    rows = [
        " & ".join(["meta attack, M1 only", frac(tm["baseline"]["asr"], 20), "--", "--",
                    "%d" % tm["baseline"]["auth_deny"], "reference"]),
        " & ".join(["meta attack, M1 $+$ auth layer", frac(tm["patched"]["asr"], 20), "--",
                    "--", "%d" % tm["patched"]["auth_deny"], "0.231"]),
        " & ".join(["slack, M1 only", frac(sl["baseline"]["asr"], 42),
                    frac(sl["baseline"]["util"], 21),
                    frac(sl["baseline"]["cl_hits_block"], sl["baseline"]["cl_hits"]),
                    "%d" % sl["baseline"]["auth_deny"], "reference"]),
        " & ".join(["slack, M1 $+$ auth layer", frac(sl["patched"]["asr"], 42),
                    frac(sl["patched"]["util"], 21),
                    frac(sl["patched"]["cl_hits_block"], sl["patched"]["cl_hits"]),
                    "%d" % sl["patched"]["auth_deny"], "1.000"]),
        " & ".join(["travel \\texttt{user\\_task\\_3} (legitimate send\\_email)", "--",
                    "1/1 (100.0)", "0/1 (0.0)", "0", "--"]),
    ]
    notes = [
        "meta = travel 20 attack scenarios (attack-only); slack = 42 / 21; seed 0; GPU fp16. "
        "The legitimate single case is a separate travel run.",
        "ASR $p$ is Fisher exact, baseline vs patched: meta 3/20 vs 0/20 $p{=}0.231$; slack "
        "0/42 vs 0/42 (nothing testable). Slack clean completion is unchanged "
        "(14/21 both, Fisher $p{=}1.000$).",
        "Wording is fixed: formally meets $\\le$2/20; Fisher $p{=}0.231$ at $n{=}20$; "
        "significance NOT established.",
        "The layer only blocks arguments that come from untrusted text: it intercepted 4 "
        "\\texttt{send\\_email} calls carrying \\texttt{jay@google.com} and 2 "
        "\\texttt{send\\_channel\\_message} calls to \\texttt{general}.",
    ]
    emit_table(
        "app_tab8_posthoc_patch",
        "Deployment-layer authorization patch: exact numbers.",
        "tab:app-patch",
        "lccccc",
        ["Setting & ASR (\\%) & Clean completion (\\%) & Clean false block (\\%) & "
         "Auth-layer blocks & Fisher $p$"],
        rows, notes,
        ["setting", "asr_num", "asr_den", "util_num", "util_den", "fb_num", "fb_den",
         "auth_blocks", "p_fisher"],
        [["meta, M1", tm["baseline"]["asr"], 20, "", "", "", "", 0, ""],
         ["meta, patched", tm["patched"]["asr"], 20, "", "", "", "",
          tm["patched"]["auth_deny"], 0.231],
         ["slack, M1", sl["baseline"]["asr"], 42, sl["baseline"]["util"], 21,
          sl["baseline"]["cl_hits_block"], sl["baseline"]["cl_hits"], 0, ""],
         ["slack, patched", sl["patched"]["asr"], 42, sl["patched"]["util"], 21,
          sl["patched"]["cl_hits_block"], sl["patched"]["cl_hits"],
          sl["patched"]["auth_deny"], 1.0],
         ["legit send_email", "", "", 1, 1, 0, 1, 0, ""]],
        size="\\footnotesize",
    )


def t9_app():
    m1_lat, ts_lat = b3_latency()
    l05 = json.load(open(os.path.join(R, SRC_LAT_05B), encoding="utf-8"))
    ts_acb, ts_n = b3_calib()
    rule_lat = json.load(open(os.path.join(R, SRC_LAT_RULE), encoding="utf-8"))
    fb_m1 = clean_false_block(SLACK)
    fb_ts = clean_false_block(SLACK_TS)
    fb_ru = clean_false_block(SLACK_RULE)
    fb_05 = clean_false_block("results/e2e/travel/m2_HB05_s0_b5e2e_inj0-1")

    rows = [
        " & ".join(["M1 (1.5B)", "slack", "%d / %d" % (m1_lat[0], m1_lat[1]), "GPU fp16",
                    "$+$4.1", "0.981 (2370)", frac(*fb_m1)]),
        " & ".join(["Task-Shield (7B judge)", "slack", "%d / %d" % (ts_lat[0], ts_lat[1]),
                    "GPU fp16", "0 (shared)", "%.3f (%d)" % (ts_acb, ts_n), frac(*fb_ts)]),
        " & ".join(["String rule ($\\gamma{=}3$)", "slack",
                    "%.4f / %.4f" % (rule_lat["p50"], rule_lat["p95"]), "CPU, 416 calls",
                    "0", "--", frac(*fb_ru)]),
        " & ".join(["0.5B guard", "travel", "%.0f / %.0f" % (l05["p50"], l05["p95"]),
                    "CPU, $n{=}95$", "-- (not measured)", "0.849 (2370)", frac(*fb_05)]),
    ]
    notes = [
        "Latency is never compared across devices: the two upper rows are GPU fp16 end-to-end "
        "calls, the lower two are CPU-only string / 0.5B measurements.",
        "ACB denominators differ: 2370 diagnostic calls for the guards, 300 calibration calls "
        "for Task-Shield. The two are not interchangeable.",
        "The false-block column mixes suites by design (M1, Task-Shield and the string rule on "
        "slack; 0.5B on travel, its only end-to-end run): read it as within-row only.",
        "0.5B GPU latency and VRAM were never measured (\\texttt{reports/b5\\_lightweight.md}); "
        "the cell stays empty rather than guessed.",
    ]
    emit_table(
        "app_tab9_cost",
        "Cost comparison: latency, VRAM, ACB and false blocks per arm.",
        "tab:app-cost",
        "llccccl",
        ["Arm & Suite & Latency mean/P95 (ms) & Device & Extra VRAM (GB) & ACB (n) & "
         "Clean false block (\\%)"],
        rows, notes,
        ["arm", "suite", "lat_mean_p95", "device", "extra_vram_gb", "acb", "false_block"],
        [["M1", "slack", "%d/%d" % (m1_lat[0], m1_lat[1]), "GPU fp16", 4.1, 0.9811,
          p(*fb_m1)],
         ["Task-Shield", "slack", "%d/%d" % (ts_lat[0], ts_lat[1]), "GPU fp16", 0.0, ts_acb,
          p(*fb_ts)],
         ["String rule", "slack", "%s/%s" % (rule_lat["p50"], rule_lat["p95"]), "CPU",
          0.0, "", p(*fb_ru)],
         ["0.5B", "travel", "%s/%s" % (l05["p50"], l05["p95"]), "CPU", "", 0.8491, p(*fb_05)]],
        size="\\footnotesize",
    )


TRANS = {
    "干净零打扰": "clean non-interference", "效用": "utility", "离线": "offline",
    "线上调用级": "online, call level", "任务级相同": "same at task level",
    "检查比例": "checked fraction", "读类": "read-type", "交集": "intersection",
    "稳健净增益": "robust net gain", "纯硬规则": "string rule only",
    "全查": "check all", "抹掉": "removed",
}
AXES = [
    ("Task field (training)", "E0 / M0 / M1", "final\\_metrics.csv::C2\\_task\\_aware"),
    ("Task field (inference)", "full vs task field removed (E1)",
     "frozen P1M2 / P2\\_ablation.md"),
    ("History length", "none / last3 / full", "results/diag/metrics.json"),
    ("Data recipe", "E0 $\\to$ S $\\to$ M0 $\\to$ M1", "final\\_metrics.csv::B10"),
    ("Paired positives", "HB vs HB-sm", "b10e\\_hbsm.md"),
    ("Deployment component", "string rule / M1 / M1 $+$ rule", "final\\_metrics.csv::B10"),
    ("Decision policy", "check all / $\\gamma\\ge2$ / $\\gamma\\ge3$",
     "results/classifier/routing\\_ablation.json"),
    ("Action prior vs task info", "M1 only / M0 only", "probes/net\\_gain\\_sets.json"),
]


def t10_app():
    rows = md_rows(SRC_B9, r"^## 2\. 消融轴", r"^## 3\.")
    data = []
    for r in rows:
        if len(r) < 4 or r[0] in ("轴",) or set(r[0]) <= set("-: "):
            continue
        data.append(r)
    if len(data) != 8:
        raise Blocked("expected 7 axes + header in b9_notes, got %d" % len(data))

    body, csv_rows = [], []
    for i, (r, ax) in enumerate(zip(data, AXES)):
        result = r[2]
        for k, v in TRANS.items():
            result = result.replace(k, v)
        result = (result.replace("→", "$\\to$").replace("，", "; ")
                  .replace("；", "; ").replace("（", " (").replace("）", ")"))
        if re.search(r"[\u4e00-\u9fff]", result):
            raise Blocked("untranslated CJK in axis %d: %r" % (i, result))
        body.append(" & ".join([ax[0], ax[1], result, ax[2]]))
        csv_rows.append([ax[0], ax[1], result, ax[2]])

    notes = [
        "Metrics differ per axis (ASR, ACB, call counts, set sizes): rows are not comparable "
        "with each other, and the table is a map of the ablation, not a ranking.",
        "Every cell is copied from \\texttt{reports/b9\\_notes.md} section 2; the source column "
        "names the artefact that produced it.",
        "Axis 7 is the set view of the denial attribution (M1 only 6, M0 only 4, intersection "
        "20, robust 2), not a proportion.",
    ]
    emit_table(
        "app_tab10_seven_axis",
        "Seven-axis ablation summary.",
        "tab:app-seven-axis",
        "llll",
        ["Axis & Comparison & Result (metric as reported) & Source"],
        body, notes,
        ["axis", "comparison", "result", "source"],
        csv_rows,
        size="\\scriptsize",
    )


def main():
    for fn in (t1, t2, t4, t6, t3_app, t5_app, t7_app, t8_app, t9_app, t10_app):
        fn()


if __name__ == "__main__":
    main()
