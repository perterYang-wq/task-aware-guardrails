# -*- coding: utf-8 -*-
"""P1 多种子汇总：12 个臂（2 模型 × 2 臂 × 3 种子）→ PRA/SPA/TieRate/Macro-F1
+ 每个种子的 ΔPRA/ΔSPA（动作聚类 CI 与整组翻符号置换 p）+ 跨种子 Mean±Std。

指标定义与推断实现全部从 p0-1.1 的冻结代码 import，不另写一份，保证口径不变。
"""
import argparse
import collections
import json
import os
import re
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from final_stats import (  # noqa: E402
    cluster_boot, cluster_perm, pair_value, score_of, sign_test)
from unified_eval_v2 import macro_f1  # noqa: E402
import hashlib  # noqa: E402

DATA = os.path.join(ROOT, "data", "pab_rd.jsonl")
SPLITS = os.path.join(ROOT, "data", "pab_rd_splits.json")
P1 = os.path.join(ROOT, "results", "p1")
PREDS = os.path.join(P1, "preds")
TAG_RX = re.compile(r"p1_(?P<model>[^_]+)_(?P<arm>task|nt)_(?P<lrkey>l[12])_s(?P<seed>\d+)")


def build_pairs(te):
    g = collections.defaultdict(lambda: {"ALLOW": [], "other": []})
    for r in te:
        g[r["current_action"]]["ALLOW" if r["label"] == "ALLOW" else "other"].append(r)
    pairs = []
    for act, v in sorted(g.items()):
        aid = hashlib.sha1(act.encode("utf-8")).hexdigest()[:10]
        for x in v["ALLOW"]:
            for y in v["other"]:
                pairs.append({"pid": "%s|%s|%s" % (aid, x["sid"], y["sid"]),
                              "aid": aid, "a": x["sid"], "o": y["sid"]})
    return pairs


def load_pred(path):
    d = {}
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        d[r["sid"]] = r
    return d


def arm_metrics(pred, te, pairs):
    gold = [r["label"] for r in te]
    predl = [(pred.get(r["sid"]) or {}).get("pred") or "REVIEW" for r in te]
    w = t = l = 0
    for pr in pairs:
        sa, so = score_of(pred[pr["a"]]), score_of(pred[pr["o"]])
        if sa > so:
            w += 1
        elif sa == so:
            t += 1
        else:
            l += 1
    n = len(pairs)
    return {"wins": w, "ties": t, "losses": l,
            "PRA": (w + 0.5 * t) / n, "SPA": w / n, "TieRate": t / n,
            "macro_f1": macro_f1(gold, predl)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(P1, "p1_report.json"))
    a = ap.parse_args()

    rec = json.load(open(os.path.join(P1, "p1_record.json"), encoding="utf-8"))
    lr = {m: v["lrkey"] for m, v in rec["lr_choice"].items()}

    rows = [json.loads(l) for l in open(DATA, encoding="utf-8")]
    by_sid = {r["sid"]: r for r in rows}
    sp = json.load(open(SPLITS, encoding="utf-8"))
    te = [by_sid[s] for s in sp["test"]]
    pairs = build_pairs(te)
    aids = [p["aid"] for p in pairs]

    # 收集预测
    arms = {}
    for f in sorted(os.listdir(PREDS)):
        m = TAG_RX.search(f)
        if not m:
            continue
        d = m.groupdict()
        arms[(d["model"], d["arm"], int(d["seed"]))] = os.path.join(PREDS, f)
    print("找到 %d 个预测文件" % len(arms), flush=True)

    res = {"metric_version": "p0-1.1",
           "protocol": rec["protocol"], "lr_choice": rec["lr_choice"],
           "n_test": len(te), "n_pairs": len(pairs),
           "n_action_groups": len({p["aid"] for p in pairs}),
           "arms": {}, "deltas": {}, "summary": {}}

    for (model, arm, seed), path in sorted(arms.items()):
        pred = load_pred(path)
        if len(pred) != len(te):
            print("  [warn] %s 覆盖 %d/%d" % (path, len(pred), len(te)), flush=True)
        met = arm_metrics(pred, te, pairs)
        met.update(model=model, arm=arm, seed=seed, path=os.path.relpath(path, ROOT))
        res["arms"]["%s|%s|%d" % (model, arm, seed)] = met

    # 每个 (model, seed) 的差值
    for model in sorted({m for m, _, _ in arms}):
        for seed in sorted({s for m, _, s in arms if m == model}):
            fa, fb = ("%s|task|%d" % (model, seed)), ("%s|nt|%d" % (model, seed))
            if fa not in res["arms"] or fb not in res["arms"]:
                continue
            pa = load_pred(arms[(model, "task", seed)])
            pb = load_pred(arms[(model, "nt", seed)])
            out = {"model": model, "seed": seed}
            for tag, strict in (("PRA", False), ("SPA", True)):
                vals = [pair_value(pa, pb, pr, strict) for pr in pairs]
                lo, hi, design, ng = cluster_boot(aids, vals)
                ps, w, l, t = sign_test(vals)
                out[tag] = {"delta": float(np.mean(vals)),
                            "ci_action_cluster": [lo, hi],
                            "p_cluster_perm": cluster_perm(aids, vals),
                            "design_effect": design,
                            "p_pair_sign_aux": ps,
                            "pairs_better": w, "pairs_worse": l, "pairs_nodiff": t}
            res["deltas"]["%s|%d" % (model, seed)] = out

    # 跨种子 Mean±Std
    print("\n%-6s%-7s%22s%22s%10s" % ("model", "metric", "task (mean±sd)", "no-task (mean±sd)", "Δ mean±sd"))
    for model in sorted({m for m, _, _ in arms}):
        s = {}
        for tag in ("PRA", "SPA", "macro_f1", "TieRate"):
            for arm in ("task", "nt"):
                v = [res["arms"]["%s|%s|%d" % (model, arm, seed)][tag]
                     for seed in sorted({x for m, _, x in arms if m == model})
                     if "%s|%s|%d" % (model, arm, seed) in res["arms"]]
                s[(tag, arm)] = (float(np.mean(v)), float(np.std(v, ddof=1)) if len(v) > 1 else 0.0)
            dv = [res["deltas"]["%s|%d" % (model, seed)][tag]["delta"]
                  for seed in sorted({x for m, _, x in arms if m == model})
                  if "%s|%d" % (model, seed) in res["deltas"]]
            s[(tag, "delta")] = (float(np.mean(dv)), float(np.std(dv, ddof=1)) if len(dv) > 1 else 0.0)
            print("%-6s%-7s%22s%22s%10s"
                  % (model, tag,
                     "%.3f±%.3f" % s[(tag, "task")], "%.3f±%.3f" % s[(tag, "nt")],
                     "%+.3f±%.3f" % s[(tag, "delta")]))
        # 每个种子的 Δ 显著性
        sig = [res["deltas"]["%s|%d" % (model, sd)]["PRA"]["p_cluster_perm"]
               for sd in sorted({x for m, _, x in arms if m == model})
               if "%s|%d" % (model, sd) in res["deltas"]]
        print("       ΔPRA cluster-perm p per seed: %s" % ["%.4f" % x for x in sig])
        res["summary"][model] = {
            "PRA_task": s[("PRA", "task")], "PRA_nt": s[("PRA", "nt")],
            "SPA_task": s[("SPA", "task")], "SPA_nt": s[("SPA", "nt")],
            "macro_f1_task": s[("macro_f1", "task")], "macro_f1_nt": s[("macro_f1", "nt")],
            "TieRate_task": s[("TieRate", "task")], "TieRate_nt": s[("TieRate", "nt")],
            "dPRA": s[("PRA", "delta")], "dSPA": s[("SPA", "delta")],
            "dmacro_f1": s[("macro_f1", "delta")],
            "p_cluster_perm_PRA_by_seed": sig,
        }

    # 两模型合并（同一 lr 规则、同一种子集合），按动作组聚类
    models = sorted({m for m, _, _ in arms})
    seeds = sorted({s for _, _, s in arms})
    if len(models) > 1:
        allv = {"PRA": [], "SPA": []}
        for seed in seeds:
            for model in models:
                k = "%s|%d" % (model, seed)
                if k not in res["deltas"]:
                    continue
                pa = load_pred(arms[(model, "task", seed)])
                pb = load_pred(arms[(model, "nt", seed)])
                for tag, strict in (("PRA", False), ("SPA", True)):
                    allv[tag].append([pair_value(pa, pb, pr, strict) for pr in pairs])
        for tag in ("PRA", "SPA"):
            if not allv[tag]:
                continue
            v = np.mean(np.array(allv[tag]), axis=0)
            lo, hi, design, ng = cluster_boot(aids, list(v))
            res["summary"]["pooled_" + tag] = {
                "delta": float(v.mean()), "ci_action_cluster": [lo, hi],
                "p_cluster_perm": cluster_perm(aids, list(v)),
                "design_effect": design, "n_runs": len(allv[tag])}
            print("\n[合并 %s] 模型x种子平均 Δ=%+.4f CI[%+.3f,%+.3f] p_perm=%.4f"
                  % (tag, v.mean(), lo, hi, res["summary"]["pooled_" + tag]["p_cluster_perm"]))

    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n-> %s" % a.out)


if __name__ == "__main__":
    main()
