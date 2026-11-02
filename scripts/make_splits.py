# -*- coding: utf-8 -*-
"""构造无泄漏划分，供所有臂共用同一套 train/val/test。

为什么不能按样本随机划分
------------------------
TS-Bench 的一个 interaction 会产生多个 step，且同一个 instruction 会反复出现
（ASB 里同一任务配不同攻击步）。按样本随机切分会让同一任务、同一工具同时出现在
训练和测试里，模型只需记住"这个任务/这个工具平时是安全的"就能得高分——
这正是我们要证明它没学到的东西。

三种划分，各自回答一个问题：
  grouped   —— 按 instruction 分组切分：对**未见任务**的泛化
  unseen_tool —— 整类工具留出：对**未见工具**的泛化
  cross_source —— 整个子集留出（默认 asb）：对**未见攻击分布**的泛化
"""
import collections
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from guard.schema import CLASSES, Step  # noqa: E402

DATA = os.path.join(ROOT, "data", "tsbench_unified.jsonl")
OUT = os.path.join(ROOT, "data", "splits.json")


def norm_task(s: str) -> str:
    return " ".join((s or "").lower().split())[:300]


def greedy_assign(groups, ratios, seed=0):
    """按组分配，尽量让各 split 的类别比例贴近全局。

    groups: list of (key, [steps])
    """
    total = collections.Counter()
    for _, g in groups:
        for st in g:
            total[st.label] += 1
    grand = sum(total.values())
    target = {k: {c: ratios[k] * total[c] for c in CLASSES} for k in ratios}
    cur = {k: collections.Counter() for k in ratios}
    out = {k: [] for k in ratios}
    order = sorted(groups, key=lambda kv: -len(kv[1]))
    rnd = random.Random(seed)
    rnd.shuffle(order)
    order.sort(key=lambda kv: -len(kv[1]))
    for key, g in order:
        gl = collections.Counter(st.label for st in g)
        best, best_score = None, None
        for k in ratios:
            # 缺口越大越优先
            score = sum((target[k][c] - cur[k][c]) / max(target[k][c], 1e-9) * gl[c]
                        for c in CLASSES)
            if best_score is None or score > best_score:
                best, best_score = k, score
        out[best].extend(st.sid for st in g)
        cur[best].update(gl)
    return out, total


def summarize(name, splits, by_sid):
    print("\n[%s]" % name)
    print("%-8s%7s%8s%8s%8s" % ("split", "n", "ALLOW", "REVIEW", "DENY"))
    for k, sids in splits.items():
        c = collections.Counter(by_sid[i].label for i in sids)
        print("%-8s%7d%8d%8d%8d" % (k, len(sids), c["ALLOW"], c["REVIEW"], c["DENY"]))


def main():
    steps = [Step(**json.loads(l)) for l in open(DATA, encoding="utf-8")]
    by_sid = {s.sid: s for s in steps}
    out = {}

    # ---- grouped：按 instruction 分组
    grp = collections.OrderedDict()
    for s in steps:
        grp.setdefault(norm_task(s.instruction), []).append(s)
    groups = list(grp.items())
    print("instruction 组数 = %d（样本 %d）" % (len(groups), len(steps)))
    splits, _ = greedy_assign(groups, {"train": 0.7, "val": 0.1, "test": 0.2})
    out["grouped"] = splits
    summarize("grouped（未见任务）", splits, by_sid)

    # 泄漏自检：三集合的 instruction 交集必须为空
    sets = {k: {norm_task(by_sid[i].instruction) for i in v} for k, v in splits.items()}
    print("  instruction 交集 train∩test=%d  train∩val=%d  val∩test=%d"
          % (len(sets["train"] & sets["test"]), len(sets["train"] & sets["val"]),
             len(sets["val"] & sets["test"])))

    # ---- unseen_tool：留出"同一工具既可能安全也可能不安全"的那批工具
    #
    # 规则（在看任何模型结果之前确定）：
    #   工具样本量 >= 60，且**少数类占比 >= 10%**。
    # 为什么要这条规则：
    #   a) 随机留出高频工具会让测试集 89% 是 ALLOW（良性工具样本多），
    #      "永远答 ALLOW" 就有 89%，测不出任何东西；
    #   b) 只要求"出现过两种标签"会把 medical_database(278:1) 这类
    #      近乎纯良性的工具也算进来，等于用噪声稀释测试；
    #   c) 真正的考点是工具名先验失效的地方：同一个工具在不同任务下
    #      既可能被授权也可能不被授权。
    # 另外排除 tool=None（343 条无 action 的步，是解析产物而非工具）。
    tc = collections.defaultdict(collections.Counter)
    for s in steps:
        if s.tool and s.tool != "None":
            tc[s.tool][s.label] += 1
    held = set()
    for t, c in tc.items():
        n = sum(c.values())
        if n < 60:
            continue
        present = [v for v in c.values() if v > 0]
        if len(present) < 2:            # 只有单一标签的工具不是"混合"
            continue
        if min(present) / n >= 0.10:
            held.add(t)
    te = [s.sid for s in steps if s.tool in held]
    print("\nunseen_tool: 留出 %d 类工具 -> %s" % (len(held), sorted(held)))
    sub = [(k, v) for k, v in groups if all(s.tool not in held for s in v)]
    sp2, _ = greedy_assign(sub, {"train": 0.875, "val": 0.125})
    out["unseen_tool"] = {"train": sp2["train"], "val": sp2["val"], "test": te}
    summarize("unseen_tool（未见工具）", out["unseen_tool"], by_sid)

    # ---- cross_source：整个子集留出
    for hold in ("asb", "agentdojo", "agentharm"):
        tr = [s.sid for s in steps if not s.source.startswith(hold)]
        te = [s.sid for s in steps if s.source.startswith(hold)]
        sub = [(k, v) for k, v in groups
               if all(not s.source.startswith(hold) for s in v)]
        sp3, _ = greedy_assign(sub, {"train": 0.875, "val": 0.125})
        out["cross_%s" % hold] = {"train": sp3["train"], "val": sp3["val"], "test": te}
        summarize("cross_source = %s（留出整个来源）" % hold, out["cross_%s" % hold], by_sid)

    json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=0)
    print("\n写出 %s（%d 套划分）" % (OUT, len(out)))


if __name__ == "__main__":
    main()
