# -*- coding: utf-8 -*-
"""P2：任务信息到底有没有用？三组廉价但决定性的检验。

检验 1  同工具不同标签的可分性
       在留出的 5 个工具内部，标签是否仍有多样性。若某个工具 100% 单标签，
       那么"未见工具"的测试对该工具就是退化的。

检验 2  最小对（minimal pair）统计
       同一工具 + 同一参数，但标签不同 —— 这类样本只能靠任务/历史区分，
       工具名与参数都提供不了信息。数量决定"任务感知"这件事有多少真实样本支撑。

检验 3  TF-IDF 词袋基线：动作-only vs 动作+任务
       按 instruction 分组交叉验证（避免同任务泄漏）。
       - 动作-only 高     => 模型只需读动作，任务信息多余
       - 动作-only 低而 动作+任务 高 => 任务信息确实不可替代
       这是对"task-aware"最直接、最不依赖大模型的经验证据。
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
from guard.metrics import evaluate  # noqa: E402
from guard.schema import Step, build_agent_log  # noqa: E402

DATA = os.path.join(ROOT, "data", "tsbench_unified.jsonl")
SPLITS = os.path.join(ROOT, "data", "splits.json")


def norm_task(s):
    return " ".join((s or "").lower().split())[:300]


def arg_key(st):
    a = st.args
    if isinstance(a, dict):
        return json.dumps(a, sort_keys=True, ensure_ascii=False)
    return "" if a is None else str(a)[:200]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="unseen_tool")
    a = ap.parse_args()

    steps = [Step(**json.loads(l)) for l in open(DATA, encoding="utf-8")]
    by = {s.sid: s for s in steps}
    sp = json.load(open(SPLITS))[a.split]
    train = [by[i] for i in sp["train"]]
    test = [by[i] for i in sp["test"]]
    print("split=%s train=%d test=%d" % (a.split, len(train), len(test)))

    # ---------- 检验 1：留出工具内部的标签多样性
    print("\n" + "=" * 74)
    print("检验 1  留出工具内部的标签分布（测试集）")
    print("%-24s%6s%8s%8s%8s%10s" % ("tool", "n", "ALLOW", "REVIEW", "DENY", "熵(bit)"))
    per_tool = collections.defaultdict(list)
    for s in test:
        per_tool[s.tool or "None"].append(s)
    for t in sorted(per_tool, key=lambda k: -len(per_tool[k])):
        g = per_tool[t]
        c = collections.Counter(x.label for x in g)
        ps = np.array([v / len(g) for v in c.values()])
        ent = float(-(ps * np.log2(ps)).sum())
        print("%-24s%6d%8d%8d%8d%10.2f" % (t, len(g), c["ALLOW"], c["REVIEW"],
                                           c["DENY"], ent))

    # ---------- 检验 2：最小对
    print("\n" + "=" * 74)
    print("检验 2  最小对统计")
    print("(a) 同工具 + 同参数，标签不同：")
    key = collections.defaultdict(set)
    for s in steps:
        if s.tool:
            key[(s.tool, arg_key(s))].add(s.label)
    conflict = {k: v for k, v in key.items() if len(v) > 1}
    print("    组数 = %d / %d (%.2f%%)"
          % (len(conflict), len(key), 100 * len(conflict) / max(len(key), 1)))
    for k, v in list(conflict.items())[:3]:
        print("      %s %s -> %s" % (k[0], k[1][:90], sorted(v)))

    print("(b) 同工具，参数不同且标签不同（可归因于任务/参数）：")
    bytool = collections.defaultdict(set)
    for s in steps:
        if s.tool:
            bytool[s.tool].add(s.label)
    mixed = {t: v for t, v in bytool.items() if len(v) > 1}
    print("    跨标签工具 = %d / %d" % (len(mixed), len(bytool)))
    n_mixed_steps = sum(1 for s in steps if s.tool in mixed)
    print("    落在跨标签工具上的样本 = %d / %d (%.1f%%)"
          % (n_mixed_steps, len(steps), 100 * n_mixed_steps / len(steps)))

    # 在测试集里，同工具同任务不同标签的例子（真正的上下文依赖）
    grp = collections.defaultdict(list)
    for s in test:
        grp[(s.tool, norm_task(s.instruction))].append(s)
    ctx_conf = [(k, v) for k, v in grp.items() if len({x.label for x in v}) > 1]
    print("(c) 测试集内 同工具+同任务 但标签不同：%d 组（这些只能靠历史/参数区分）"
          % len(ctx_conf))
    for k, v in ctx_conf[:2]:
        print("      %s | %s" % (k[0], k[1][:70]))
        for x in v[:3]:
            print("         gold=%-7s args=%s" % (x.label, arg_key(x)[:100]))

    # ---------- 检验 3：TF-IDF 词袋基线
    print("\n" + "=" * 74)
    print("检验 3  TF-IDF 逻辑回归：动作-only vs 动作+任务（按 instruction 分组 CV）")
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline

    def txt_action(s):
        return (s.current_action or "") + " " + arg_key(s)[:600]

    def txt_both(s):
        return (s.instruction or "") + " || " + (s.current_action or "") + " " + arg_key(s)[:600]

    def cv_eval(textfn, name, folds=5):
        # 按 instruction 分组分折（同任务的样本必须同折，否则指标虚高）
        groups = sorted({norm_task(s.instruction) for s in train})
        gfold = {g: i % folds for i, g in enumerate(groups)}
        preds = {}
        for f in range(folds):
            tr = [s for s in train if gfold[norm_task(s.instruction)] != f]
            te = [s for s in train if gfold[norm_task(s.instruction)] == f]
            if not tr or not te:
                continue
            pipe = make_pipeline(
                TfidfVectorizer(max_features=20000, ngram_range=(1, 2), min_df=2),
                LogisticRegression(max_iter=2000, C=1.0, class_weight="balanced"))
            pipe.fit([textfn(s) for s in tr], [s.label for s in tr])
            for s, y in zip(te, pipe.predict([textfn(s) for s in te])):
                preds[s.sid] = y
        ev = [s for s in train if s.sid in preds]
        r = evaluate([s.label for s in ev], [preds[s.sid] for s in ev],
                     "TFIDF " + name, verbose=True)
        return r

    r1 = cv_eval(txt_action, "动作-only")
    r2 = cv_eval(txt_both, "动作+任务")
    print("\n增益：macro-F1 %.4f -> %.4f  (Δ=%+.4f)"
          % (r1["macro_f1"], r2["macro_f1"], r2["macro_f1"] - r1["macro_f1"]))

    json.dump({"split": a.split, "tfidf_action_only": r1, "tfidf_action_task": r2,
               "n_conflict_same_tool_args": len(conflict),
               "n_cross_label_tools": len(mixed)},
              open(os.path.join(ROOT, "results", "pairs_%s.json" % a.split), "w"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
