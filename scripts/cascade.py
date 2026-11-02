# -*- coding: utf-8 -*-
"""O2：风险自适应级联（便宜的层先判，只在不确定时升级到 1.5B guard）。

动机
----
把每条待执行动作都送进 1.5B 成本是固定的。但大量样本（工具明显合法、
参数完全落在证据里）用词袋级打分就够。级联的目标是：
在**不降低配对准确率**的前提下，把 1.5B 的调用比例压下来。

做法
----
1. 便宜层：TF-IDF + 逻辑回归（任务 + 证据 + 动作），给出三类概率。
2. 不确定性 = 最大类概率低于阈值 τ，或落在决策边界附近。
3. τ 在 **val** 上选：取"升级比例 ≈ 目标预算"的最大 τ。
4. 只在 test 上报：升级比例、macro-F1、配对准确率。

注意：这里刻意不用 PG2 当第一层。PG2 是**提示注入**检测器，
它判断不了"这个工具调用是否被用户授权"；在 PAB 上它的分数与标签无关，
强行用会导致升级率 100%，等于没有级联。这一点要如实写进论文。
"""
import argparse
import json
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from guard.metrics import evaluate  # noqa: E402

DATA = os.path.join(ROOT, "data", "pab.jsonl")
SPLITS = os.path.join(ROOT, "data", "pab_splits.json")
LABELS = ["ALLOW", "REVIEW", "DENY"]
SCORE = {"ALLOW": 1.0, "REVIEW": 0.5, "DENY": 0.0, None: -1.0}


def load():
    rows = {}
    for l in open(DATA, encoding="utf-8"):
        d = json.loads(l)
        rows[d["sid"]] = d
    sp = json.load(open(SPLITS))
    return rows, sp


def text_of(r):
    return (r["instruction"] + " || " + (r.get("history") or "")
            + " || " + r["current_action"])


def fit_cheap(train_rows):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    pipe = make_pipeline(
        TfidfVectorizer(max_features=30000, ngram_range=(1, 2), min_df=2, sublinear_tf=True),
        LogisticRegression(max_iter=3000, C=1.0, class_weight="balanced"))
    pipe.fit([text_of(r) for r in train_rows], [r["label"] for r in train_rows])
    return pipe, list(pipe.classes_)


def probs_of(pipe, classes, rows):
    P = pipe.predict_proba([text_of(r) for r in rows])
    return P, classes


def pairwise_from_scores(rows, score_fn):
    import collections
    g = collections.defaultdict(lambda: {"ALLOW": [], "other": []})
    for r in rows:
        g[r["current_action"]]["ALLOW" if r["label"] == "ALLOW" else "other"].append(r)
    win = tie = n = 0
    for k, v in g.items():
        for a in v["ALLOW"]:
            for o in v["other"]:
                sa, so = score_fn(a), score_fn(o)
                if sa > so:
                    win += 1
                elif sa == so:
                    tie += 1
                n += 1
    return (win + 0.5 * tie) / n if n else 0.0, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True, help="1.5B 在 PAB test 上的预测 jsonl")
    ap.add_argument("--budgets", default="0.05,0.1,0.2,0.3,0.5,0.7,1.0")
    a = ap.parse_args()

    rows, sp = load()
    tr = [rows[i] for i in sp["train"]]
    va = [rows[i] for i in sp["val"]]
    te = [rows[i] for i in sp["test"]]

    pipe, classes = fit_cheap(tr)
    Pv, classes = probs_of(pipe, classes, va)
    Pt, classes = probs_of(pipe, classes, te)
    print("cheap 层 classes_ 顺序 =", classes)

    preds = {json.loads(l)["sid"]: json.loads(l)["pred"]
             for l in open(a.pred, encoding="utf-8")}

    def cheap_label(p):
        # 必须用 classes_ 的真实顺序（字母序 ALLOW/DENY/REVIEW），
        # 不能用 LABELS 的下标，否则三个标签会被置换
        return classes[int(np.argmax(p))]

    def cheap_score(p):
        return float(p[classes.index("ALLOW")]) * 1.0 + \
            float(p[classes.index("REVIEW")]) * 0.5

    # 便宜层单独的表现
    print("便宜层（TF-IDF, 任务+证据+动作）单独：")
    r0 = evaluate([r["label"] for r in te], [cheap_label(p) for p in Pt], "cheap", verbose=False)
    tidx = {r["sid"]: i for i, r in enumerate(te)}
    acc0, n0 = pairwise_from_scores(te, lambda r: cheap_score(Pt[tidx[r["sid"]]]))
    print("  macro-F1=%.4f  配对准确率=%.1f%% (n=%d)" % (r0["macro_f1"], 100 * acc0, n0))

    print("\n1.5B 单独：")
    r1 = evaluate([r["label"] for r in te], [preds.get(r["sid"]) for r in te],
                  "1.5B", verbose=False)
    acc1, _ = pairwise_from_scores(te, lambda r: SCORE[preds.get(r["sid"])])
    print("  macro-F1=%.4f  配对准确率=%.1f%%" % (r1["macro_f1"], 100 * acc1))

    # 级联：max prob 低于 τ 时升级
    print("\n级联（τ 在 val 上按目标预算选；test 上报告）")
    print("%-10s%10s%12s%12s%12s" % ("budget", "tau", "实际升级率", "macro-F1", "配对准确率"))
    budgets = [float(x) for x in a.budgets.split(",")]
    conf_v = Pv.max(axis=1)
    out = []
    for b in budgets:
        if b >= 1.0:
            tau = 1.0
        else:
            tau = float(np.quantile(conf_v, b))
        esc = Pt.max(axis=1) < tau
        mixed, scores = [], {}
        for i, r in enumerate(te):
            if esc[i]:
                lab = preds.get(r["sid"])
                sc = SCORE[lab]
            else:
                lab = cheap_label(Pt[i])
                sc = cheap_score(Pt[i])
            mixed.append(lab)
            scores[r["sid"]] = sc
        rr = evaluate([r["label"] for r in te], mixed, "cascade", verbose=False)
        acc, _ = pairwise_from_scores(te, lambda r: scores[r["sid"]])
        rate = float(esc.mean())
        print("%-10.2f%10.4f%12.3f%12.4f%12.1f%%"
              % (b, tau, rate, rr["macro_f1"], 100 * acc))
        out.append({"budget": b, "tau": tau, "escalation": rate,
                    "macro_f1": rr["macro_f1"], "pair_acc": acc})

    json.dump({"cheap_only": {"macro_f1": r0["macro_f1"], "pair_acc": acc0},
               "model_only": {"macro_f1": r1["macro_f1"], "pair_acc": acc1},
               "cascade": out},
              open(os.path.join(ROOT, "results", "cascade.json"), "w"),
              ensure_ascii=False, indent=1)
    print("\n-> results/cascade.json")


if __name__ == "__main__":
    main()
