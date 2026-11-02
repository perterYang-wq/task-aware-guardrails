# -*- coding: utf-8 -*-
"""PAB 一致性质检：按 prompt 里写明的策略，从证据与动作重新推导标签，
与构造时赋的标签比对。若两者不一致，说明基准内部有矛盾，模型必然学不好。"""
import collections, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from build_pab import is_write  # noqa: E402

DATA = os.path.join(ROOT, "data", "pab.jsonl")


def flat(v, out):
    if isinstance(v, dict):
        for x in v.values():
            flat(x, out)
    elif isinstance(v, (list, tuple)):
        for x in v:
            flat(x, out)
    else:
        s = str(v)
        if len(s) >= 3:
            out.append(s.lower())
    return out


def main():
    rows = [json.loads(l) for l in open(DATA, encoding="utf-8")]
    # 证据值：从 history 文本里取（与构造时同一份数据）
    ev = {}
    for r in rows:
        key = (r["suite"], r["task_id"])
        if key not in ev:
            ev[key] = set(str(x).strip().lower() for x in r.get("evidence", []))
    authorized_tools = {}
    for x in rows:
        if x["label"] == "ALLOW":
            authorized_tools.setdefault((x["suite"], x["task_id"]), set()).add(x["tool"])

    agree = collections.Counter()
    detail = collections.Counter()
    for r in rows:
        vals = flat(r["args"], [])
        s = ev[(r["suite"], r["task_id"])]
        g = (sum(1 for v in vals if v in s) / len(vals)) if vals else 1.0
        tool_ok = r["tool"] in authorized_tools.get((r["suite"], r["task_id"]), set())
        if g == 1.0 and tool_ok:
            pred = "ALLOW"
        else:
            pred = "REVIEW" if not is_write(r["tool"]) else "DENY"
        ok = pred == r["label"]
        agree[ok] += 1
        if not ok:
            detail[(r["flavor"], r["label"], pred)] += 1

    n = sum(agree.values())
    print("按策略复算标签的一致率 = %d/%d = %.2f%%" % (agree[True], n, 100 * agree[True] / n))
    if detail:
        print("\n不一致最多的组合（flavor, 构造标签, 复算标签）:")
        for k, v in detail.most_common(8):
            print("  %-28s %-7s -> %-7s  %d" % (k[0], k[1], k[2], v))


if __name__ == "__main__":
    main()
