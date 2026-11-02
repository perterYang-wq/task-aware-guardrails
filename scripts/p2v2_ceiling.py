# -*- coding: utf-8 -*-
"""P2-v2 任务 1：测算 AgentDojo 现有数据能支持多少"授权关系明确"的
(Action, Evidence) 场景。

口径
----
**场景 (scenario)** = 一个 (tool, args) 动作 + 一份证据包。同一场景下换任务不换场景。
之所以把 evidence 纳入场景定义：README 要求统计独立场景而不是配对数，
而同一个动作在同一份证据上无论配几个任务，都只提供一条关于"任务是否改变授权"的独立证据。

判定"可用场景"的三个必要条件：
    C1  该动作在某个任务下被策略 A 判 ALLOW（有正面授权依据）
    C2  至少存在另一个任务被策略 A 判 DENY（有反面依据）
    C3  证据包非空且包含 grounding 依据（doc 命中，或不含文档但记录含参数）

C1 决定了上限：ALLOW 侧必须来自 task.ground_truth()，不能编造任务文本。
"""
import collections
import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from agentdojo.task_suite.load_suites import get_suite  # noqa: E402
import build_p2 as P  # noqa: E402

SUITES = ["banking", "slack", "travel", "workspace"]


def main():
    rows = [json.loads(l) for l in open(os.path.join(ROOT, "data", "pab_rd.jsonl"),
                                        encoding="utf-8")]
    sp = json.load(open(os.path.join(ROOT, "data", "pab_rd_splits.json"), encoding="utf-8"))
    sid2task = {r["sid"]: (r["suite"], r["task_id"]) for r in rows}
    part = {}
    for k in ("train", "val", "test"):
        for sid in sp[k]:
            part[sid2task[sid]] = k

    total = collections.Counter()
    print("%-11s%7s%9s%9s%9s%10s%10s%12s" %
          ("suite", "tasks", "GT调用", "读调用", "写调用", "不同写动作", "可用场景", "strict场景"))

    detail = {}
    for suite in SUITES:
        s = get_suite("v1", suite)
        env = s.load_and_inject_default_environment({})
        docs = P.docs_for(suite, env)

        tasks = {}
        for tid, t in s.user_tasks.items():
            try:
                gt = t.ground_truth(copy.deepcopy(env))
            except Exception:
                continue
            tasks[tid] = {"prompt": t.PROMPT, "cls": type(t).__name__,
                          "part": part.get((suite, tid), "?"),
                          "calls": [(g.function, dict(g.args)) for g in gt]}

        n_calls = sum(len(v["calls"]) for v in tasks.values())
        n_read = sum(1 for v in tasks.values() for f, _ in v["calls"]
                     if P.effect_of(f) == "READ")
        n_write = n_calls - n_read

        # 收集所有"写动作"及其被授权的任务
        acts = collections.defaultdict(lambda: {"allow": [], "deny": [], "fn": None,
                                                "args": None, "ev": None})
        for tid, v in tasks.items():
            for fn, args in v["calls"]:
                if P.effect_of(fn) == "READ":
                    continue
                key = (fn, json.dumps(args, sort_keys=True, default=str))
                a = acts[key]
                a["fn"], a["args"] = fn, args
                lab, _ = P.policy_A(v["prompt"], fn, args, "", docs)
                if lab == "ALLOW":
                    a["allow"].append((tid, v["part"]))
                else:
                    a["deny"].append((tid, v["part"]))

        # 为每个写动作补上 evidence，并统计可用场景
        n_usable = 0
        n_strict = 0
        usable_detail = []
        for key, a in acts.items():
            if not a["allow"]:
                continue
            ev = P.build_evidence(suite, docs, a["fn"], a["args"])
            a["ev"] = ev
            # DENY 侧：任意其它任务
            deny_any = [t for t in tasks if t not in {x for x, _ in a["allow"]}]
            deny_ok = [t for t in deny_any
                       if P.policy_A(tasks[t]["prompt"], a["fn"], a["args"], ev, docs)[0] == "DENY"]
            if not deny_ok:
                continue
            n_usable += 1
            # strict：ALLOW 与 DENY 两侧都在 test
            allow_test = [t for t, p_ in a["allow"] if p_ == "test"]
            deny_test = [t for t in deny_ok if tasks[t]["part"] == "test"]
            strict = bool(allow_test and deny_test)
            n_strict += strict
            usable_detail.append({
                "fn": a["fn"], "allow": a["allow"], "n_deny": len(deny_ok),
                "strict": strict, "has_doc": bool(ev and ev.startswith("[")),
                "n_doc_blocks": ev.count("\n\n[") + 1 if ev.startswith("[") else 0})

        print("%-11s%7d%9d%9d%9d%10d%10d%12d" %
              (suite, len(tasks), n_calls, n_read, n_write, len(acts), n_usable, n_strict))
        for k in ("tasks", "calls", "read", "write", "acts", "usable", "strict"):
            total[k] += {"tasks": len(tasks), "calls": n_calls, "read": n_read,
                         "write": n_write, "acts": len(acts), "usable": n_usable,
                         "strict": n_strict}[k]
        detail[suite] = usable_detail

    print("-" * 78)
    print("%-11s%7d%9d%9d%9d%10d%10d%12d" %
          ("TOTAL", total["tasks"], total["calls"], total["read"], total["write"],
           total["acts"], total["usable"], total["strict"]))

    print("\n== 场景多样性 ==")
    allf = collections.Counter()
    for suite, ds in detail.items():
        for d in ds:
            allf[d["fn"]] += 1
    print("可用场景按工具: %s" % dict(allf.most_common()))
    print("按域 × 是否有真实文档证据:")
    for suite, ds in detail.items():
        nd = sum(1 for d in ds if d["has_doc"])
        print("  %-10s 有文档 %d / 无文档 %d" % (suite, nd, len(ds) - nd))

    print("\n== 上限判定 ==")
    print("可用场景 %d（目标 80–100）" % total["usable"])
    print("其中 strict_test（正负都在 test）%d" % total["strict"])
    if total["usable"] < 80:
        print("-> 不达标。瓶颈：ALLOW 侧只能来自 ground_truth 的写调用，")
        print("   现有 97 个任务里被策略认可的写动作只有 %d 个不同 (tool,args)。" % total["acts"])
        print("   要把场景数抬到 80+，只能：(a) 允许同一动作配多份证据包；")
        print("   (b) 引入读调用的授权判定（隐私口径）；(c) 新建环境场景（需你批准）。")

    out = os.path.join(ROOT, "results", "audit", "p2v2_ceiling.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({"total": total, "detail": detail,
               "tool_hist": dict(allf)}, open(out, "w"), ensure_ascii=False, indent=1)
    print("\n-> %s" % out)


if __name__ == "__main__":
    main()
