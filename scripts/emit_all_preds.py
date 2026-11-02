# -*- coding: utf-8 -*-
"""把每个臂的预测统一落到 results/preds/<arm>.jsonl，schema 固定为 {sid, pred, score}。

统一口径的理由
--------------
PRA/SPA 需要**连续 score**，Macro-F1 只需要 pred。早期脚本里基线只有 pred、
LLM 臂只有 label，导致两边算法不同、表格不可比。这里一次性物化：
  - 表面基线：score = 训练集上该键的平滑 ALLOW 率（查表）或 p(ALLOW)+0.5·p(REVIEW)（词袋）
  - LLM 臂：score = 序数映射 ALLOW=1.0 / REVIEW=0.5 / DENY=0.0
分数越高越"允许"，方向统一。
"""
import collections
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DATA = os.path.join(ROOT, "data", "pab_rd.jsonl")
SPLITS = os.path.join(ROOT, "data", "pab_rd_splits.json")
OUT = os.path.join(ROOT, "results", "preds")
LAB2SCORE = {"ALLOW": 1.0, "REVIEW": 0.5, "DENY": 0.0}

# 复用现成的模型预测文件：(输出名, 源文件)
MODEL_ARMS = [
    ("zs_0.5B", "b3_rd_05b_test.jsonl"),
    ("zs_1.5B", "b3_rd_15b_test.jsonl"),
    ("zs_3B", "b3_rd_3b_test.jsonl"),
    ("zs_7B", "b3_rd_7b_test.jsonl"),
    ("full_0.5B", "o1_rd_05b_test.jsonl"),
    ("full_1.5B", "o1_rd_15b_test.jsonl"),
    ("full_3B", "o1_rd_3b_test.jsonl"),
    ("full_7B", "o1_rd_7b_test.jsonl"),
    ("blind_0.5B", "o1_rd_05b_nt_test.jsonl"),
    ("blind_1.5B", "o1_rd_15b_nt_test.jsonl"),
    ("blind_3B", "o1_rd_3b_nt_test.jsonl"),
    ("blind_7B", "o1_rd_7b_nt_test.jsonl"),
    ("full_1.5B_lr4", "o1_rd_15b_lr4_test.jsonl"),
    ("blind_1.5B_lr4", "o1_rd_15b_nt_lr4_test.jsonl"),
]


def write(name, rows):
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, name + ".jsonl")
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return p


def main():
    rows = {json.loads(l)["sid"]: json.loads(l)
            for l in open(DATA, encoding="utf-8")}
    sp = json.load(open(SPLITS))
    tr = [rows[i] for i in sp["train"]]
    te = [rows[i] for i in sp["test"]]
    print("train=%d test=%d" % (len(tr), len(te)))

    # ---------- 表面基线
    def lookup(key, name):
        tab = collections.defaultdict(collections.Counter)
        for r in tr:
            tab[r[key]][r["label"]] += 1
        glob = collections.Counter(x["label"] for x in tr).most_common(1)[0][0]
        out = []
        for r in te:
            c = tab.get(r[key])
            if c:
                pred = c.most_common(1)[0][0]
                score = (c["ALLOW"] + 0.5) / (sum(c.values()) + 1.0)   # 平滑 ALLOW 率
            else:
                pred, score = glob, 0.0
            out.append({"sid": r["sid"], "pred": pred, "score": float(score)})
        write(name, out)
        print("  %-16s pred=%s" % (name, collections.Counter(x["pred"] for x in out).most_common(3)))

    maj = collections.Counter(x["label"] for x in tr).most_common(1)[0][0]
    write("base_majority", [{"sid": r["sid"], "pred": maj, "score": 0.5} for r in te])
    print("  %-16s pred=%s" % ("base_majority", maj))

    lookup("tool", "base_tool_lookup")
    lookup("current_action", "base_action_lookup")

    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline

    def text(r, kind):
        return {"action": r["current_action"],
                "task": r["instruction"] + " || " + r["current_action"],
                "full": r["instruction"] + " || " + (r.get("history") or "")
                        + " || " + r["current_action"]}[kind]

    for kind in ("action", "task", "full"):
        pipe = make_pipeline(
            TfidfVectorizer(max_features=30000, ngram_range=(1, 2), min_df=2,
                            sublinear_tf=True),
            LogisticRegression(max_iter=3000, C=1.0, class_weight="balanced"))
        pipe.fit([text(r, kind) for r in tr], [r["label"] for r in tr])
        cls = list(pipe.classes_)
        P = pipe.predict_proba([text(r, kind) for r in te])
        out = []
        for r, p in zip(te, P):
            pred = cls[int(np.argmax(p))]
            score = float(p[cls.index("ALLOW")]) + 0.5 * float(p[cls.index("REVIEW")])
            out.append({"sid": r["sid"], "pred": pred, "score": score})
        write("base_tfidf_" + kind, out)
        print("  %-16s pred=%s" % ("base_tfidf_" + kind,
                                   collections.Counter(x["pred"] for x in out).most_common(3)))

    # ---------- 模型臂
    for name, src in MODEL_ARMS:
        p = os.path.join(ROOT, "results", src)
        if not os.path.exists(p):
            print("  [skip] %s" % src)
            continue
        out = []
        for line in open(p, encoding="utf-8"):
            d = json.loads(line)
            out.append({"sid": d["sid"], "pred": d["pred"],
                        "score": LAB2SCORE.get(d["pred"])})
        write(name, out)
        print("  %-16s n=%d" % (name, len(out)))


if __name__ == "__main__":
    main()
