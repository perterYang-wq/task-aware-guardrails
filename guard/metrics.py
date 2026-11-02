# -*- coding: utf-8 -*-
"""统一的评测指标。所有臂（规则/分类器/零 shot/微调）都用这一个函数，
避免不同脚本各算一套导致数字不可比。"""
import collections

CLASSES = ["ALLOW", "REVIEW", "DENY"]


def evaluate(gold, pred, tag="", verbose=True):
    """gold/pred 均为标签字符串；pred=None 记作解析失败，按错误计入。"""
    n = len(gold)
    assert len(pred) == n
    ok = sum(1 for g, p in zip(gold, pred) if g == p)
    nfail = sum(1 for p in pred if p is None)
    res = {"n": n, "acc": ok / n if n else 0.0,
           "parse_fail": nfail, "parse_fail_rate": nfail / n if n else 0.0}
    per = {}
    f1s = []
    for c in CLASSES:
        tp = sum(1 for g, p in zip(gold, pred) if g == c and p == c)
        fp = sum(1 for g, p in zip(gold, pred) if g != c and p == c)
        fn = sum(1 for g, p in zip(gold, pred) if g == c and p != c)
        sup = sum(1 for g in gold if g == c)
        P = tp / (tp + fp) if tp + fp else 0.0
        R = tp / (tp + fn) if tp + fn else 0.0
        F = 2 * P * R / (P + R) if P + R else 0.0
        f1s.append(F)
        per[c] = {"P": P, "R": R, "F1": F, "support": sup}
    res["per_class"] = per
    res["macro_f1"] = sum(f1s) / len(f1s)
    res["majority_acc"] = (max(collections.Counter(gold).values()) / n) if n else 0.0
    cm = collections.Counter((g, p) for g, p in zip(gold, pred))
    res["confusion"] = {"%s|%s" % k: v for k, v in cm.items()}

    if verbose:
        print("\n[%s] n=%d  acc=%.4f  macro-F1=%.4f  解析失败=%d (%.1f%%)  多数类=%.4f"
              % (tag, n, res["acc"], res["macro_f1"], nfail,
                 100 * res["parse_fail_rate"], res["majority_acc"]))
        print("%-8s%8s%8s%8s%8s" % ("class", "P", "R", "F1", "support"))
        for c in CLASSES:
            d = per[c]
            print("%-8s%8.3f%8.3f%8.3f%8d" % (c, d["P"], d["R"], d["F1"], d["support"]))
        print("混淆（行=gold, 列=pred）:")
        print("        " + "".join("%9s" % c for c in CLASSES + ["None"]))
        for g in CLASSES:
            print("%-8s" % g + "".join("%9d" % cm.get((g, p), 0)
                                       for p in CLASSES + [None]))
    return res
