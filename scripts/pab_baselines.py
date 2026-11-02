# -*- coding: utf-8 -*-
"""PAB 的划分 + 四组证伪基线。

证伪逻辑
--------
PAB 里每个动作文本都同时出现在多个标签下（构造保证）。所以：
  - 动作文本查表 / 动作-only 词袋  -> 理论上不可能超过随机
  - 工具名查表                      -> 同理，因为同一工具跨标签
  - 动作+任务 词袋                  -> 应当显著更高
若"动作+任务"显著高于"动作-only"，就证明该基准确实要求任务条件化，
而不是又一个可以用表面特征刷分的集合。
"""
import argparse
import collections
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from guard.metrics import evaluate  # noqa: E402

DATA = os.path.join(ROOT, "data", "pab.jsonl")
SPLITS = os.path.join(ROOT, "data", "pab_splits.json")


def load():
    return [json.loads(l) for l in open(DATA, encoding="utf-8")]


def make_splits(rows, seed=0):
    """按 (suite, task_id) 分组切分：同一任务的样本必须同侧。"""
    import random
    groups = collections.defaultdict(list)
    for r in rows:
        groups[(r["suite"], r["task_id"])].append(r)
    keys = sorted(groups)
    random.Random(seed).shuffle(keys)
    n = len(keys)
    n_tr, n_va = int(0.65 * n), int(0.10 * n)
    out = {"train": [], "val": [], "test": []}
    for i, k in enumerate(keys):
        part = "train" if i < n_tr else ("val" if i < n_tr + n_va else "test")
        out[part].extend(r["sid"] for r in groups[k])
    return out


def argstr(r):
    try:
        return json.dumps(r.get("args"), sort_keys=True, ensure_ascii=False)
    except Exception:
        return str(r.get("args"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    rows = load()
    by = {r["sid"]: r for r in rows}
    sp = make_splits(rows, a.seed)
    json.dump(sp, open(SPLITS, "w"), ensure_ascii=False, indent=0)

    print("PAB n=%d  train/val/test = %d/%d/%d" % (
        len(rows), len(sp["train"]), len(sp["val"]), len(sp["test"])))
    for part in ("train", "val", "test"):
        c = collections.Counter(by[i]["label"] for i in sp[part])
        print("  %-6s ALLOW=%d REVIEW=%d DENY=%d" % (part, c["ALLOW"], c["REVIEW"], c["DENY"]))
    # 泄漏自检：任务不重叠
    tr = {(by[i]["suite"], by[i]["task_id"]) for i in sp["train"]}
    te = {(by[i]["suite"], by[i]["task_id"]) for i in sp["test"]}
    print("  任务交集 train∩test = %d" % len(tr & te))

    train = [by[i] for i in sp["train"]]
    test = [by[i] for i in sp["test"]]
    gold = [r["label"] for r in test]
    print("\n测试集多数类 = %.3f" % (max(collections.Counter(gold).values()) / len(gold)))

    # B0 多数类
    maj = collections.Counter(r["label"] for r in train).most_common(1)[0][0]
    res = {"PAB_B0": evaluate(gold, [maj] * len(test), "B0 多数类(%s)" % maj, verbose=False)}

    # B2b 工具名查表
    tab = collections.defaultdict(collections.Counter)
    for r in train:
        tab[r["tool"]][r["label"]] += 1
    glob = maj
    pred = [tab[r["tool"]].most_common(1)[0][0] if tab.get(r["tool"]) else glob for r in test]
    res["PAB_tool_lookup"] = evaluate(gold, pred, "B2b 工具名查表", verbose=True)

    # 动作文本查表（完全相同的动作串）
    atab = collections.defaultdict(collections.Counter)
    for r in train:
        atab[r["current_action"]][r["label"]] += 1
    pred2 = [atab[r["current_action"]].most_common(1)[0][0]
             if atab.get(r["current_action"]) else glob for r in test]
    res["PAB_action_lookup"] = evaluate(gold, pred2, "动作文本查表", verbose=True)

    # TF-IDF
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline

    def tfidf(textfn, name, folds=5):
        groups = sorted({(r["suite"], r["task_id"]) for r in train})
        gfold = {g: i % folds for i, g in enumerate(groups)}
        preds = {}
        for f in range(folds):
            tr_ = [r for r in train if gfold[(r["suite"], r["task_id"])] != f]
            te_ = [r for r in train if gfold[(r["suite"], r["task_id"])] == f]
            if not tr_ or not te_:
                continue
            pipe = make_pipeline(
                TfidfVectorizer(max_features=30000, ngram_range=(1, 2), min_df=2,
                                sublinear_tf=True),
                LogisticRegression(max_iter=3000, C=1.0, class_weight="balanced"))
            pipe.fit([textfn(r) for r in tr_], [r["label"] for r in tr_])
            for r, y in zip(te_, pipe.predict([textfn(r) for r in te_])):
                preds[r["sid"]] = y
        ev = [r for r in train if r["sid"] in preds]
        return evaluate([r["label"] for r in ev],
                        [preds[r["sid"]] for r in ev], "TFIDF " + name, verbose=True)

    r_act = tfidf(lambda r: r["current_action"], "动作-only")
    r_both = tfidf(lambda r: r["instruction"] + " || " + r["current_action"], "动作+任务")
    r_ev = tfidf(lambda r: (r["instruction"] + " || " + (r.get("history") or "")
                            + " || " + r["current_action"]), "动作+任务+证据")
    res["PAB_tfidf_action"] = r_act
    res["PAB_tfidf_action_task"] = r_both
    print("\n【关键】动作-only macro-F1 = %.4f   动作+任务 = %.4f (+%.4f)   动作+任务+证据 = %.4f (+%.4f)"
          % (r_act["macro_f1"], r_both["macro_f1"],
             r_both["macro_f1"] - r_act["macro_f1"],
             r_ev["macro_f1"], r_ev["macro_f1"] - r_act["macro_f1"]))

    json.dump(res, open(os.path.join(ROOT, "results", "pab_baselines.json"), "w"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
