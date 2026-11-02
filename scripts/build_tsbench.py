# -*- coding: utf-8 -*-
"""把 TS-Bench 归一成 data/tsbench_unified.jsonl，并输出标签/混淆诊断。"""
import collections
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from guard.schema import CLASSES, LABELS, load_tsbench  # noqa: E402

TSBENCH = os.path.join(ROOT, "repos", "toolsafe", "TS-Bench")
OUT = os.path.join(ROOT, "data", "tsbench_unified.jsonl")


def main():
    steps = load_tsbench(TSBENCH)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for s in steps:
            f.write(json.dumps(s.to_dict(), ensure_ascii=False) + "\n")

    print("total = %d  -> %s" % (len(steps), OUT))
    print("\n%-22s%6s%8s%8s%8s" % ("source", "n", "ALLOW", "REVIEW", "DENY"))
    by = collections.defaultdict(list)
    for s in steps:
        by[s.source].append(s)
    for k in sorted(by):
        c = collections.Counter(x.label for x in by[k])
        print("%-22s%6d%8d%8d%8d" % (k, len(by[k]), c["ALLOW"], c["REVIEW"], c["DENY"]))
    c = collections.Counter(s.label for s in steps)
    print("%-22s%6d%8d%8d%8d" % ("TOTAL", len(steps), c["ALLOW"], c["REVIEW"], c["DENY"]))

    # 字段完整性与 action 解析率
    n_tool = sum(1 for s in steps if s.tool)
    n_args = sum(1 for s in steps if s.meta is not None and
                 isinstance(s.args, (dict, list)))
    print("\naction 解析：tool=%d/%d (%.1f%%)  args=json=%d (%.1f%%)"
          % (n_tool, len(steps), 100 * n_tool / len(steps),
             n_args, 100 * n_args / len(steps)))
    empty = [s.sid for s in steps if not s.instruction or not s.current_action]
    print("空 instruction/action 记录：%d" % len(empty))

    # 混淆诊断：只看工具名能到多少（多数类基线）
    print("\n【混淆诊断】仅用工具名的预测上限（训练/测试同分布，过于乐观）")
    tool_label = collections.defaultdict(collections.Counter)
    for s in steps:
        if s.tool:
            tool_label[s.tool][s.label] += 1
    hit = sum(max(v.values()) for v in tool_label.values())
    n_tool_only = sum(sum(v.values()) for v in tool_label.values())
    if n_tool_only:
        print("  以工具名映射到其最常见标签：acc = %.3f (n=%d, 工具种类=%d)"
              % (hit / n_tool_only, n_tool_only, len(tool_label)))
    print("  多数类基线 acc = %.3f" % (c.most_common(1)[0][1] / len(steps)))

    # 同一工具跨标签的情况（越小说明越依赖工具名）
    mixed = {k: v for k, v in tool_label.items() if len(v) > 1}
    print("  出现多种标签的工具：%d/%d" % (len(mixed), len(tool_label)))


if __name__ == "__main__":
    main()
