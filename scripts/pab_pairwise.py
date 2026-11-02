# -*- coding: utf-8 -*-
"""PAB 配对准确率：唯一能把"任务条件化"与"表面特征/先验"分开的指标。

定义
----
对同一段动作文本 a，取两条样本：
    (T_owner, a) -> ALLOW        （该动作确实是这个任务要求做的）
    (T_other, a) -> 非 ALLOW     （同一个动作，换了个任务，就未被授权）
配对准确率 = P(score_ALLOW > score_other) + 0.5 * P(相等)

为什么它是决定性的
------------------
若模型的输入只有动作文本，则两条样本的输入**逐字相同**，任何确定性打分函数
给出相同分数 -> 全部计入 0.5 -> 配对准确率恒等于 50.0%。
所以在这个指标上超过 50%，必然用到了任务信息；停在 50%，就证明它没用任务。

与之对照，全测试集的 macro-F1 会奖励"猜多数类"，可以把一个没有任务条件化
能力的模型刷到 0.60。两个指标并排报告，差距本身就是论文的论点。
"""
import argparse
import collections
import json
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DATA = os.path.join(ROOT, "data", "pab.jsonl")
SPLITS = os.path.join(ROOT, "data", "pab_splits.json")


def load():
    rows = [json.loads(l) for l in open(DATA, encoding="utf-8")]
    by = {r["sid"]: r for r in rows}
    sp = json.load(open(SPLITS))
    tr = [by[i] for i in sp["train"]]
    va = [by[i] for i in sp["val"]]
    te = [by[i] for i in sp["test"]]
    return rows, tr, va, te


def build_pairs(rows):
    """返回 [(allow_row, other_row)]，只在同一动作文本内部配对。"""
    g = collections.defaultdict(lambda: {"ALLOW": [], "other": []})
    for r in rows:
        g[r["current_action"]]["ALLOW" if r["label"] == "ALLOW" else "other"].append(r)
    pairs = []
    for k, v in g.items():
        for a in v["ALLOW"]:
            for o in v["other"]:
                pairs.append((a, o))
    return pairs


def build_pairs_by_flavor(rows):
    """按负例的构造方式分组，因为它们的可判定性完全不同。"""
    g = collections.defaultdict(lambda: {"ALLOW": [], "other": []})
    for r in rows:
        g[r["current_action"]]["ALLOW" if r["label"] == "ALLOW" else "other"].append(r)
    out = collections.defaultdict(list)
    for k, v in g.items():
        for a in v["ALLOW"]:
            for o in v["other"]:
                out[o.get("flavor", "?")].append((a, o))
    return out


def pairwise_acc(pairs, score_fn):
    """score_fn(row) -> 越高表示越"允许"。返回 (acc, n, n_action, per_action)。"""
    win = tie = 0
    per = collections.defaultdict(lambda: [0.0, 0])
    for a, o in pairs:
        sa, so = score_fn(a), score_fn(o)
        act = a["current_action"]
        if sa > so:
            win += 1
            per[act][0] += 1.0
        elif sa == so:
            tie += 1
            per[act][0] += 0.5
        per[act][1] += 1
    n = len(pairs)
    acc = (win + 0.5 * tie) / n if n else 0.0
    pa = {k: v[0] / v[1] for k, v in per.items() if v[1]}
    return acc, n, len(pa), pa


def binom_ci(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    se = math.sqrt(max(p * (1 - p) / n, 1e-12))
    return (max(0.0, p - z * se), min(1.0, p + z * se))


# ------------------------------------------------------------ 各打分器
def scorer_lookup(train, key):
    tab = collections.defaultdict(collections.Counter)
    for r in train:
        tab[r[key]][r["label"]] += 1
    # 分数 = 该键在训练集里被判 ALLOW 的比例（平滑）
    def f(r):
        c = tab.get(r[key])
        if not c:
            return 0.0
        return (c["ALLOW"] + 0.5) / (sum(c.values()) + 1.0)
    return f


def scorer_tfidf(train, textfn):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    pipe = make_pipeline(
        TfidfVectorizer(max_features=30000, ngram_range=(1, 2), min_df=2,
                        sublinear_tf=True),
        LogisticRegression(max_iter=3000, C=1.0, class_weight="balanced"))
    pipe.fit([textfn(r) for r in train], [r["label"] for r in train])
    classes = list(pipe.classes_)

    def f(r):
        p = pipe.predict_proba([textfn(r)])[0]
        return float(p[classes.index("ALLOW")]) if "ALLOW" in classes else 0.0
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", default="test", choices=["test", "val", "valtest"])
    a = ap.parse_args()

    rows, tr, va, te = load()
    pool = {"test": te, "val": va, "valtest": va + te}[a.part]
    pairs = build_pairs(pool)
    print("PAB 配对评估  part=%s  样本=%d  配对数=%d"
          % (a.part, len(pool), len(pairs)))
    print("  随机/恒定打分器的期望值 = 50.0%%（构造保证）\n")

    SC = {
        "工具名查表": scorer_lookup(tr, "tool"),
        "动作文本查表": scorer_lookup(tr, "current_action"),
        "TFIDF-动作only": scorer_tfidf(tr, lambda r: r["current_action"]),
        "TFIDF-动作+任务": scorer_tfidf(
            tr, lambda r: r["instruction"] + " || " + r["current_action"]),
        "TFIDF-动作+任务+证据": scorer_tfidf(
            tr, lambda r: (r["instruction"] + " || " + (r.get("history") or "")
                           + " || " + r["current_action"])),
    }

    out = {}
    print("%-20s%10s%10s%12s%10s" % ("scorer", "pair-acc", "n_pairs", "95%CI", "n_action"))
    for name, f in SC.items():
        acc, n, na, per = pairwise_acc(pairs, f)
        lo, hi = binom_ci(acc * n, n)
        print("%-20s%10.1f%%%10d%12s%10d"
              % (name, 100 * acc, n, "[%.0f,%.0f]" % (100 * lo, 100 * hi), na))
        out[name] = {"pair_acc": acc, "n_pairs": n, "n_actions": na,
                     "ci": [lo, hi], "per_action": per}

    # 分动作的符号检验（每个动作一个配对准确率）
    import statistics as st
    for name, f in SC.items():
        _, _, _, per = pairwise_acc(pairs, f)
        vals = [v for v in per.values() if v == v]
        if len(vals) >= 5:
            above = sum(1 for v in vals if v > 0.5)
            below = sum(1 for v in vals if v < 0.5)
            n = above + below
            if n:
                # 二项检验（双侧）
                k = min(above, below)
                p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n * 2
                print("  %-18s 动作级: 高于50%%=%d 低于50%%=%d  双侧 p=%.4f"
                      % (name, above, below, min(1.0, p)))

    # 按负例类型拆分：可判定性不同，混在一起看会掩盖机制
    print("\n按负例构造方式拆分（pair-acc）")
    byfl = build_pairs_by_flavor(pool)
    print("%-26s%8s" % ("flavor", "n_pairs") + "".join("%20s" % n for n in SC))
    for fl in sorted(byfl):
        ps = byfl[fl]
        line = "%-26s%8d" % (fl, len(ps))
        for name, f in SC.items():
            acc, n, _, _ = pairwise_acc(ps, f)
            line += "%20s" % ("%.1f%%" % (100 * acc))
        print(line)
        out.setdefault("by_flavor", {})[fl] = len(ps)

    json.dump(out, open(os.path.join(ROOT, "results", "pab_pairwise_%s.json" % a.part), "w"),
              ensure_ascii=False, indent=1)
    print("\n-> results/pab_pairwise_%s.json" % a.part)


if __name__ == "__main__":
    main()
