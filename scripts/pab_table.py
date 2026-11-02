# -*- coding: utf-8 -*-
"""汇总 PAB 测试集上的全部对照臂，输出论文主表。

每个臂都报两个指标：
  macro-F1  —— 会被"猜多数类/利用先验"抬高
  pair-acc  —— 同动作文本的 ALLOW vs 非 ALLOW，恒等输入必为 50%
"""
import collections
import json
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from guard.metrics import evaluate  # noqa: E402

import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("--data", default=os.path.join(ROOT, "data", "pab.jsonl"))
_ap.add_argument("--splits", default=os.path.join(ROOT, "data", "pab_splits.json"))
_ap.add_argument("--preds", default="b3_pab_test.jsonl,o1_pab_notask_test.jsonl,o1_pab_test.jsonl")
_ap.add_argument("--names", default="1.5B zero-shot,1.5B + LoRA, task-blind,1.5B + LoRA (ours)")
_ap.add_argument("--out", default=os.path.join(ROOT, "results", "pab_table.json"))
ARGS = _ap.parse_args()
DATA = ARGS.data
SPLITS = ARGS.splits
SCORE = {"ALLOW": 1.0, "REVIEW": 0.5, "DENY": 0.0, None: -1.0}


def pair_acc(rows, score_fn):
    g = collections.defaultdict(lambda: {"ALLOW": [], "other": []})
    for r in rows:
        g[r["current_action"]]["ALLOW" if r["label"] == "ALLOW" else "other"].append(r)
    win = tie = n = 0
    per = collections.defaultdict(lambda: [0.0, 0])
    for k, v in g.items():
        for a in v["ALLOW"]:
            for o in v["other"]:
                sa, so = score_fn(a), score_fn(o)
                if sa > so:
                    win += 1
                    per[k][0] += 1.0
                elif sa == so:
                    tie += 1
                    per[k][0] += 0.5
                per[k][1] += 1
                n += 1
    acc = (win + 0.5 * tie) / n if n else 0.0
    return acc, n, [v[0] / v[1] for v in per.values() if v[1]]


def ci(k, n, z=1.96):
    if not n:
        return 0.0, 0.0
    p = k / n
    se = math.sqrt(max(p * (1 - p) / n, 1e-12))
    return max(0.0, p - z * se), min(1.0, p + z * se)


def text(r, kind):
    return {"action": r["current_action"],
            "task": r["instruction"] + " || " + r["current_action"],
            "full": r["instruction"] + " || " + (r.get("history") or "")
                    + " || " + r["current_action"]}[kind]


def main():
    rows = {json.loads(l)["sid"]: json.loads(l) for l in open(DATA, encoding="utf-8")}
    sp = json.load(open(SPLITS))
    tr = [rows[i] for i in sp["train"]]
    te = [rows[i] for i in sp["test"]]
    gold = [r["label"] for r in te]

    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline

    def tfidf(kind):
        pipe = make_pipeline(
            TfidfVectorizer(max_features=30000, ngram_range=(1, 2), min_df=2,
                            sublinear_tf=True),
            LogisticRegression(max_iter=3000, C=1.0, class_weight="balanced"))
        pipe.fit([text(r, kind) for r in tr], [r["label"] for r in tr])
        cls = list(pipe.classes_)
        P = pipe.predict_proba([text(r, kind) for r in te])
        preds = [cls[int(np.argmax(p))] for p in P]
        sc = {r["sid"]: (float(p[cls.index("ALLOW")]) + 0.5 * float(p[cls.index("REVIEW")]))
              for r, p in zip(te, P)}
        return preds, (lambda r: sc[r["sid"]])

    # 查表类
    def lookup(key):
        tab = collections.defaultdict(collections.Counter)
        for r in tr:
            tab[r[key]][r["label"]] += 1
        glob = collections.Counter(x["label"] for x in tr).most_common(1)[0][0]
        preds, sc = [], {}
        for r in te:
            c = tab.get(r[key])
            lab = c.most_common(1)[0][0] if c else glob
            preds.append(lab)
            sc[r["sid"]] = ((c["ALLOW"] + 0.5) / (sum(c.values()) + 1.0)) if c else 0.0
        return preds, (lambda r: sc[r["sid"]])

    maj = collections.Counter(x["label"] for x in tr).most_common(1)[0][0]
    arms = [
        ("多数类 (%s)" % maj, [maj] * len(te), lambda r: 0.0),
        ("工具名查表", *lookup("tool")),
        ("动作文本查表", *lookup("current_action")),
        ("TF-IDF 动作only", *tfidf("action")),
        ("TF-IDF 动作+任务", *tfidf("task")),
        ("TF-IDF 动作+任务+证据", *tfidf("full")),
    ]

    def from_file(path, name):
        if not os.path.exists(path):
            return None
        p = {json.loads(l)["sid"]: json.loads(l)["pred"]
             for l in open(path, encoding="utf-8")}
        return (name, [p.get(r["sid"]) for r in te],
                (lambda r: SCORE[p.get(r["sid"])]))

    fs = [x.strip() for x in ARGS.preds.split(",") if x.strip()]
    ns = [x.strip() for x in ARGS.names.split(",") if x.strip()]
    for i, f in enumerate(fs):
        n = ns[i] if i < len(ns) else f
        got = from_file(os.path.join(ROOT, "results", f), n)
        if got:
            arms.append(got)

    print("%-26s%10s%10s%12s%12s" % ("arm", "macro-F1", "acc", "pair-acc", "95%CI"))
    out = {}
    for name, preds, sc in arms:
        m = evaluate(gold, preds, name, verbose=False)
        pa, n, per = pair_acc(te, sc)
        lo, hi = ci(pa * n, n)
        print("%-26s%10.4f%10.4f%11.1f%%%13s"
              % (name, m["macro_f1"], m["acc"], 100 * pa,
                 "[%.0f,%.0f]" % (100 * lo, 100 * hi)))
        out[name] = {"macro_f1": m["macro_f1"], "acc": m["acc"],
                     "pair_acc": pa, "n_pairs": n, "ci": [lo, hi]}

    json.dump(out, open(ARGS.out, "w"), ensure_ascii=False, indent=1)
    print("\n-> %s" % ARGS.out)


if __name__ == "__main__":
    main()
