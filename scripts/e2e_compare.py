# -*- coding: utf-8 -*-
"""端到端对比：守卫臂 vs 已采集的无守卫基线，严格限定在同一批 (task, injection)。

为什么要「限定同一批」
--------------------
无守卫基线是之前采集的整族轨迹（travel 159 场景），守卫臂只跑其中一部分注入，
直接比会拿不同的场景集合相减。这里取交集，逐场景对齐后再算比率。

指标
----
Benign Utility : 干净场景 utility=True 的比例
ASR            : 受攻击场景 security=True（AgentDojo 官方判定被攻破）的比例
ScenDef        : 1 − ASR
Utility@Atk    : 受攻击场景里任务仍完成的比例（守卫拦错时的代价）
"""
import argparse
import json
import os
from collections import Counter


def load(p):
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def key(s):
    return (s["user_task"], s.get("injection_task"))


def stats(rows):
    clean = [s for s in rows if not s.get("injection_present")]
    atk = [s for s in rows if s.get("injection_present")]
    return dict(
        n_clean=len(clean), n_attack=len(atk),
        utility=(sum(1 for s in clean if s.get("utility")) / len(clean) * 100
                 if clean else None),
        asr=(sum(1 for s in atk if s.get("security")) / len(atk) * 100) if atk else None,
        util_atk=(sum(1 for s in atk if s.get("utility")) / len(atk) * 100
                  if atk else None),
        broke=sum(1 for s in atk if s.get("security")), n_atk=len(atk),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="travel")
    ap.add_argument("--baseline", default="/data/projects/guardrails/results/ad_v3/travel/scen_merged.jsonl")
    ap.add_argument("--runs", nargs="+", required=True, help="守卫臂的 scen.jsonl 路径")
    ap.add_argument("--out", default="/data/projects/guardrails/results/e2e/compare.json")
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)

    base = {key(s): s for s in load(a.baseline)}
    out = []
    for rp in a.runs:
        run = load(rp)
        if not run:
            print("[skip] %s 空" % rp)
            continue
        keys = {key(s) for s in run}
        b = [base[k] for k in keys if k in base]
        g = [s for s in run if key(s) in base]
        bs, gs = stats(b), stats(g)
        tag = os.path.basename(os.path.dirname(rp))
        out.append(dict(suite=a.suite, tag=tag, n_common=len(keys),
                        baseline=bs, guard=gs,
                        asr_drop=(bs["asr"] - gs["asr"]) if bs["asr"] is not None and gs["asr"] is not None else None,
                        util_drop=(bs["utility"] - gs["utility"]) if bs["utility"] is not None and gs["utility"] is not None else None))
        print("\n== %s / %s  (共同场景 %d) ==" % (a.suite, tag, len(keys)))
        print("%-12s %8s %8s %8s %8s" % ("", "n", "Utility", "ASR", "Util@Atk"))
        for nm, s in (("baseline", bs), ("guard", gs)):
            print("%-12s %8s %8s %8s %8s" % (
                nm, "%d+%d" % (s["n_clean"], s["n_attack"]),
                "-" if s["utility"] is None else "%.1f" % s["utility"],
                "-" if s["asr"] is None else "%.1f" % s["asr"],
                "-" if s["util_atk"] is None else "%.1f" % s["util_atk"]))
        print("ASR 下降 %.1f pp   干净场景 Utility 变化 %+.1f pp"
              % (out[-1]["asr_drop"] or 0, -(out[-1]["util_drop"] or 0)))

    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=2)
    print("\n-> %s" % a.out)


if __name__ == "__main__":
    main()
