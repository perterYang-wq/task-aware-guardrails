# -*- coding: utf-8 -*-
"""P2-v2 全种子零样本评测（P1 正常结束后运行）

硬性规则（逐条落在代码里，见 RULES）
------------------------------------
R2  幂等/单实例：文件锁 + 已有结果则跳过，禁止重复启动评测进程。
R3  保留全部样本：不截断任何输入（推理链无截断点），并记录 max prompt tokens；
    额外给出剔除场景 91ae3a54fd 的敏感性结果。
R4  No-task 必须同配对同分 → PRA=0.500；否则记 anomaly 并大声报错，但不改数据。
R5  主结果 = strict_test，且硬断言 19 场景 / 41 配对 / 6 动作；
    场景等权 PRA 为主，SPA / TieRate 为辅，**逐动作 × 逐 seed** 全部给出。
R6  不做正式显著性检验：只给场景层 bootstrap 描述区间，不输出 p 值。
R7  不做任何选择：lrkey 只从 p1_record.json 读，评测过程不回写、不重选。
R8  只读：P2-v2 数据、results/frozen、p1_record.json 的哈希在运行前后必须一致。

指标函数直接 import 冻结版 `p2v2_eval`（run_arm/build_pairs/report），零分支差异。
"""
import argparse
import collections
import fcntl
import hashlib
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from p2v2_eval import (PAIRS, P1, build_pairs, check_freeze,  # noqa: E402
                       report as frozen_report, run_arm, scen_equal, tier_of)

M = {"15b": "/data/hf_cache/qwen1.5b", "3b": "/data/hf_cache/qwen3b"}
OUTJ = os.path.join(ROOT, "results", "p2v2", "p2v2_allseeds.json")
OUTM = os.path.join(ROOT, "reports", "p2v2_allseeds_report.md")
PD = os.path.join(ROOT, "results", "p2v2", "preds_allseeds")
LOCK = os.path.join(ROOT, "results", "p2v2", ".eval.lock")
OVER_SCEN = "91ae3a54fd"          # 唯一含 >1024 token 记录的场景（见 input_audit）
EXPECT = {"n_scenarios": 19, "n_pairs": 41, "n_actions": 6}
FROZEN = ["results/frozen/final_report.json", "data/p2v2_pairs.jsonl",
          "data/p2v2_index.json", "results/p1/p1_record.json"]


def sha(p):
    p = os.path.join(ROOT, p)
    if not os.path.exists(p):
        return None
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def snapshot():
    return {p: sha(p) for p in FROZEN}


def by_action_full(tab):
    """逐动作 PRA / SPA / TieRate，口径与冻结 report() 的场景等权一致。"""
    per = collections.defaultdict(
        lambda: collections.defaultdict(lambda: {"val": [], "spa": [], "tie": []}))
    for t in tab:
        if t["tier"] != "strict_test":
            continue
        d = per[(t["action_id"], t["tool"])][t["scenario_id"]]
        d["val"].append(t["val"])
        d["spa"].append(t["spa"])
        d["tie"].append(t["tie"])
    out = []
    for (aid, tool), sc in per.items():
        out.append({"action_id": aid, "tool": tool,
                    "n_scenarios": len(sc),
                    "n_pairs": sum(len(v["val"]) for v in sc.values()),
                    "PRA": float(np.mean([np.mean(v["val"]) for v in sc.values()])),
                    "SPA": float(np.mean([np.mean(v["spa"]) for v in sc.values()])),
                    "TieRate": float(np.mean([np.mean(v["tie"]) for v in sc.values()]))})
    return sorted(out, key=lambda r: -r["PRA"])


def prompt_len_evidence(model_path, rows):
    """R3：证明没有任何截断——记录完整模板下的输入长度分布。"""
    from transformers import AutoTokenizer
    from p2v2_eval import render_pab, to_step
    tok = AutoTokenizer.from_pretrained(model_path, padding_side="left")
    L = []
    for r in rows:
        t = tok.apply_chat_template(
            [{"role": "user", "content": render_pab(to_step(r), task_aware=True)}],
            tokenize=False, add_generation_prompt=True)
        L.append(len(tok(t, add_special_tokens=False).input_ids))
    a = np.asarray(L)
    return {"max_prompt_tokens": int(a.max()), "p95": float(np.percentile(a, 95)),
            "n_over_1024": int((a > 1024).sum()), "n": int(a.size),
            "truncated": False,
            "note": "推理链无 truncation；超 1024 的样本原样输入（长度外推，非截断）"}


def diag_nt(preds, rows):
    by = collections.defaultdict(dict)
    for r, p in zip(rows, preds):
        by[r["pair_id"]][r["pair_role"]] = p
    diff = [k for k, d in by.items() if d.get("positive") != d.get("negative")]
    return {"pairs": len(by), "same_pred": len(by) - len(diff),
            "n_diff": len(diff), "diff_pairs": diff[:10]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bs", type=int, default=12)
    ap.add_argument("--max-new", type=int, default=6)
    ap.add_argument("--seeds", default="0,42,123")
    ap.add_argument("--models", default="15b,3b")
    ap.add_argument("--out", default=OUTJ)
    a = ap.parse_args()

    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    fh = open(LOCK, "w")
    try:                                        # R2 单实例
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("[SKIP] 已有评测进程持有锁 %s，本次不启动" % LOCK, flush=True)
        return 0

    idx = check_freeze()                        # R8 数据哈希校验
    before = snapshot()
    rows = [json.loads(l) for l in open(PAIRS, encoding="utf-8")]
    print("P2-v2 校验通过：%d 记录 / %d 配对 / %d 场景（hash %s）"
          % (len(rows), idx["index"]["n_pairs"], idx["index"]["n_scenarios"],
             idx["index"]["sha256"][:16]), flush=True)
    rec = json.load(open(os.path.join(P1, "p1_record.json"), encoding="utf-8"))
    seeds = [int(x) for x in a.seeds.split(",") if x.strip()]
    models = [x.strip() for x in a.models.split(",") if x.strip()]
    for m in models:
        if m not in M or m not in rec.get("lr_choice", {}):
            raise SystemExit("R7: 模型 %s 没有 P1 预先确定的 lr，拒绝评测" % m)
    os.makedirs(PD, exist_ok=True)

    res = {"sha256": idx["index"]["sha256"], "seeds": seeds,
           "metric": "scenario_equal_PRA_on_strict_pairs",
           "expected_strict": EXPECT, "rules": {
               "R3_no_truncation": True, "R6_no_significance_test": True,
               "R7_no_reselection": "lr 只读自 p1_record.json（P2-v2 不参与选择）",
               "R8_readonly": True},
           "integrity_before": before, "arms": {}, "anomalies": []}

    for model in models:
        lrkey = rec["lr_choice"][model]["lrkey"]
        res["arms"].setdefault(model, {})["lrkey"] = lrkey
        res["arms"][model]["prompt_len"] = prompt_len_evidence(M[model], rows)
        runs = [("zero-shot", "", False)]
        for s in seeds:
            runs.append(("task_s%d" % s, "guard/adapters/p1_%s_task_%s_s%d"
                         % (model, lrkey, s), False))
            runs.append(("nt_s%d" % s, "guard/adapters/p1_%s_nt_%s_s%d"
                         % (model, lrkey, s), True))
        for label, adapter, no_task in runs:
            apath = os.path.join(ROOT, adapter) if adapter else ""
            if adapter and not os.path.isdir(apath):
                print("  [skip] %s %s（adapter 不存在）" % (model, label), flush=True)
                continue
            print("\n[%s | %s]" % (model, label), flush=True)
            preds, raws = run_arm(M[model], apath, rows, no_task, a.bs, a.max_new)
            tab = build_pairs(rows, preds)
            out = {"surface_only": False,
                   "unparsed": sum(1 for p in preds if p is None) / len(preds)}
            rep = frozen_report(tab)
            rep["strict"]["by_action"] = by_action_full(tab)   # 带 SPA/Tie
            out.update(rep)

            s = out["strict"]
            if (s["n_scenarios"], s["n_pairs"], len(s["by_action"])) != (
                    EXPECT["n_scenarios"], EXPECT["n_pairs"], EXPECT["n_actions"]):
                raise SystemExit(
                    "R5 违反：strict_test 应为 19 场景/41 对/6 动作，实测 %d/%d/%d"
                    % (s["n_scenarios"], s["n_pairs"], len(s["by_action"])))
            kept = [t for t in tab if t["scenario_id"] != OVER_SCEN]
            alt = scen_equal(kept, "strict_test", "val")
            s["drop_overlen_scenario"] = {
                "excluded": OVER_SCEN, "n_scenarios": alt["n_scenarios"],
                "n_pairs": alt["n_pairs"], "PRA": alt["mean"]}
            if no_task:
                c = diag_nt(preds, rows)
                ok = (c["n_diff"] == 0 and abs(s["PRA_scenario_equal"] - 0.5) < 1e-12
                      and abs(s["TieRate_scenario_equal"] - 1.0) < 1e-12)
                c["ok"] = bool(ok)
                c["PRA"] = s["PRA_scenario_equal"]
                c["TieRate"] = s["TieRate_scenario_equal"]
                out["nt_consistency"] = c
                if not ok:
                    msg = ("R4 异常：%s No-task 未达 PRA=0.500（实测 %.4f，"
                           "同配对异分 %d 个）。输入已证实逐字节相同 → 排查批内 padding "
                           "的浮点非确定性，**不修改数据**。"
                           % (label, s["PRA_scenario_equal"], c["n_diff"]))
                    print("  !!! " + msg, flush=True)
                    res["anomalies"].append({"arm": "%s|%s" % (model, label),
                                             "type": "nt_not_half", "detail": msg})

            fn = os.path.join(PD, "%s_%s.jsonl" % (model, label))
            with open(fn, "w", encoding="utf-8") as f:
                for r, p, rw in zip(rows, preds, raws):
                    f.write(json.dumps(dict(
                        pair_id=r["pair_id"], scenario_id=r["scenario_id"],
                        role=r["pair_role"], gold=r["label"], pred=p, raw=rw[:120],
                        tier=tier_of(r), suite=r["suite"], tool=r["tool"],
                        action_id=r["action_id"], task_id=r["task_id"]),
                        ensure_ascii=False) + "\n")
            res["arms"][model][label] = out
            print("  strict PRA=%.4f  SPA=%.3f Tie=%.3f  %d 场景/%d 对/%d 动作  "
                  "unparsed=%.3f%s"
                  % (s["PRA_scenario_equal"], s["SPA_scenario_equal"],
                     s["TieRate_scenario_equal"], s["n_scenarios"], s["n_pairs"],
                     len(s["by_action"]), out["unparsed"],
                     "  [nt ok]" if no_task and out.get("nt_consistency", {}).get("ok")
                     else ""), flush=True)

    after = snapshot()
    res["integrity_after"] = after
    res["integrity_ok"] = (before == after)
    if not res["integrity_ok"]:
        bad = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
        res["anomalies"].append({"type": "readonly_violation", "detail": str(bad)})
        print("!!! R8 违反：只读文件被改动 %s" % bad, flush=True)

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(OUTM, "w", encoding="utf-8").write(render_md(res, idx))
    print("\n-> %s\n-> %s" % (a.out, OUTM), flush=True)
    if res["anomalies"]:
        print("ANOMALY %d 项，见报告顶部" % len(res["anomalies"]), flush=True)


def render_md(res, idx):
    seeds = res["seeds"]
    order = ["zero-shot"] + [x for s in seeds for x in ("task_s%d" % s, "nt_s%d" % s)]
    L = []
    A = L.append
    A("# P2-v2 零样本评测结果（全种子）\n")
    A("P2-v2 冻结件 sha256 `%s`（632 记录 / %d 配对 / %d 场景）。"
      % (res["sha256"][:16], idx["index"]["n_pairs"], idx["index"]["n_scenarios"]))
    A("本表**不使用 P2-v2 做任何训练、调参或 checkpoint 选择**；lr 与 checkpoint 由 P1 协议"
      "（只看验证集）预先确定，评测脚本只读 `p1_record.json`。\n")
    A("> **统计口径（R6）**：主指标为 strict_test 层的**场景等权 PRA**"
      "（场景内配对先平均，再跨场景等权）。strict 层只有 **6 个动作簇、19 个场景、41 个配对**，"
      "**不做正式显著性声明，不输出 p 值**；方括号内区间由场景层 bootstrap 给出，"
      "仅作描述性参考，不可解读为对动作总体的推断。\n")
    if res.get("anomalies"):
        A("## 注意：异常（需排查，未改动数据）\n")
        for x in res["anomalies"]:
            A("- `%s`：%s" % (x.get("type"), x.get("detail")))
        A("")
    else:
        A("异常检查：No-task 全部达到 PRA=0.500；只读文件哈希运行前后一致。\n")

    for model in [m for m in ("15b", "3b") if m in res["arms"]]:
        arms = res["arms"][model]
        pl = arms.get("prompt_len")
        A("\n## %s（lr=%s）\n" % (model, arms.get("lrkey")))
        if pl:
            A("输入长度证据（R3）：完整模板 max **%d** token，p95 %.0f，>1024 的 %d/%d 条；"
              "**未做任何截断**，超长样本原样输入。\n"
              % (pl["max_prompt_tokens"], pl["p95"], pl["n_over_1024"], pl["n"]))
        A("| 臂 | n 场景 | n 配对 | PRA | SPA | TieRate | bootstrap 描述区间 | unparsed |")
        A("|---|---|---|---|---|---|---|---|")
        for lab in order:
            d = arms.get(lab)
            if not d:
                continue
            s = d["strict"]
            A("| %s | %d | %d | **%.3f** | %.3f | %.3f | [%.3f, %.3f] | %.3f |"
              % (lab, s["n_scenarios"], s["n_pairs"], s["PRA_scenario_equal"],
                 s["SPA_scenario_equal"], s["TieRate_scenario_equal"],
                 s["PRA_ci_scenario_boot"][0], s["PRA_ci_scenario_boot"][1],
                 d["unparsed"]))
        A("")
        for fam, nm in (("task", "Task-aware"), ("nt", "No-task")):
            cols = (["zero-shot"] if fam == "task" else []) + \
                   ["%s_s%d" % (fam, s) for s in seeds]
            acts = collections.OrderedDict()
            for lab in cols:
                d = arms.get(lab)
                if not d:
                    continue
                for r in d["strict"]["by_action"]:
                    acts.setdefault((r["action_id"], r["tool"]), {})[lab] = r
            if not acts:
                continue
            A("### 逐动作 × 逐 seed（%s）\n" % nm)
            A("单元格 = **PRA / SPA / TieRate**（场景等权）。\n")
            A("| 动作（tool · action_id） | n 场景 | n 配对 | " + " | ".join(cols) + " |")
            A("|" + "---|" * (3 + len(cols)))
            for (aid, tool), m in acts.items():
                r0 = next(iter(m.values()))
                cells = ["%.2f / %.2f / %.2f" % (m[c]["PRA"], m[c]["SPA"], m[c]["TieRate"])
                         if c in m else "—" for c in cols]
                A("| `%s` · %s | %d | %d | %s |"
                  % (tool, aid[:8], r0["n_scenarios"], r0["n_pairs"], " | ".join(cells)))
            A("")
        for fam, nm in (("task", "Task-aware"), ("nt", "No-task")):
            vals = [arms["%s_s%d" % (fam, s)]["strict"] for s in seeds
                    if "%s_s%d" % (fam, s) in arms]
            if not vals:
                continue
            pr = np.array([v["PRA_scenario_equal"] for v in vals])
            sp = np.array([v["SPA_scenario_equal"] for v in vals])
            ti = np.array([v["TieRate_scenario_equal"] for v in vals])
            A("- **%s 跨 seed**：PRA %.3f ± %.3f（min %.3f / max %.3f，%d seed）；"
              "SPA %.3f ± %.3f；TieRate %.3f ± %.3f"
              % (nm, pr.mean(), pr.std(ddof=1) if len(pr) > 1 else 0, pr.min(), pr.max(),
                 len(pr), sp.mean(), sp.std(ddof=1) if len(sp) > 1 else 0,
                 ti.mean(), ti.std(ddof=1) if len(ti) > 1 else 0))
        A("")
        A("### 敏感性与辅助口径\n")
        A("| 口径 | " + " | ".join(order) + " |")
        A("|" + "---|" * (len(order) + 1))
        A("| 剔除超长场景 %s（敏感性）" % OVER_SCEN
          + "".join(" | %.3f" % arms[l]["strict"]["drop_overlen_scenario"]["PRA"]
                    if l in arms else " | —" for l in order) + " |")
        A("| aux: 全部 79 场景（场景等权 PRA）"
          + "".join(" | %.3f" % arms[l]["all"]["PRA_scenario_equal"]
                    if l in arms else " | —" for l in order) + " |")
        for t in ("unseen", "contains_train"):
            A("| aux: %s（场景等权 PRA）" % t
              + "".join(" | %.3f" % arms[l][t]["PRA_scenario_equal"]
                        if l in arms and t in arms[l] else " | —" for l in order) + " |")
        A("")
        nt = [(l, arms[l]["nt_consistency"]) for l in order
              if l.startswith("nt") and "nt_consistency" in arms.get(l, {})]
        if nt:
            A("### No-task 同分自检（R4）\n")
            A("同配对输入逐字节相同（`p2v2_input_audit.md` 316/316），故理论值 "
              "PRA=0.500 / SPA=0.000 / TieRate=1.000。\n")
            A("| 臂 | 同配对同分 | 异分配对 | PRA | TieRate | 判定 |")
            A("|---|---|---|---|---|---|")
            for l, c in nt:
                s = arms[l]["strict"]
                A("| %s | %d/%d | %d | %.4f | %.4f | %s |"
                  % (l, c["same_pred"], c["pairs"], c["n_diff"],
                     s["PRA_scenario_equal"], s["TieRate_scenario_equal"],
                     "通过" if c["ok"] else "**异常**"))
            A("")
    A("\n## 结论口径（预先声明）\n")
    A("1. 主结论只看 **strict_test 场景等权 PRA**；SPA / TieRate 用于区分"
      "“真的判低”与“不敢判”（Tie 高说明没区分开，而非判对）。")
    A("2. 逐动作、逐 seed 全部给数；跨 seed 只报均值 ± 标准差（3 个种子）。")
    A("3. 79 场景全体、unseen、contains_train 只作辅助，不与主结果混为一谈。")
    A("4. 不做正式显著性检验（6 个动作簇）；不据 P2-v2 结果回选 checkpoint 或超参。\n")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
