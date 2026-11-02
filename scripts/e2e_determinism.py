# -*- coding: utf-8 -*-
"""确定性校验：无守卫重跑能不能逐场景复现已采集的基线。

为什么要有这一步
----------------
端到端的所有配对检验（McNemar / 配对 Fisher）都假设「同一任务在两次运行里
只有守卫这一个差别」。如果 agent 本身有随机性，这个假设不成立，配对检验就失去意义。
本脚本用同一批 (task, injection) 重跑无守卫版本，逐字段比对：

    utility / security / n_steps / n_executed / attack_call_strong

全一致 → 采样是确定性的（temperature=0 + top_p=1，vLLM 走贪心），配对成立。
有任何不一致 → 报告具体差在哪，后续只能用非配对检验或增加重复次数。
"""
import argparse
import json
import os


def load(p):
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def key(s):
    return (s["user_task"], s.get("injection_task"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--baseline", required=True)
    a = ap.parse_args()

    run = {key(s): s for s in load(a.run)}
    base = {key(s): s for s in load(a.baseline)}
    common = sorted(run.keys() & base.keys(), key=str)
    if not common:
        print("没有共同场景，无法比对")
        return

    FIELDS = ("utility", "security", "n_steps", "n_executed", "attack_call_strong")
    diffs = {f: [] for f in FIELDS}
    for k in common:
        for f in FIELDS:
            if run[k].get(f) != base[k].get(f):
                diffs[f].append((k, base[k].get(f), run[k].get(f)))

    print("== 确定性校验：共同场景 %d ==" % len(common))
    for f in FIELDS:
        d = diffs[f]
        print("  %-20s 一致 %d/%d" % (f, len(common) - len(d), len(common)))
        for (k, b, r) in d[:5]:
            print("      差异 %s: 基线=%r 重跑=%r" % (k, b, r))
    ok = all(not v for v in diffs.values())
    print("  => %s" % ("DETERMINISTIC_OK" if ok else "NON_DETERMINISTIC"))
    out = os.path.join(os.path.dirname(a.run) or ".", "determinism.json")
    json.dump(dict(n_common=len(common), ok=ok,
                   diffs={f: [list(map(str, x)) for x in v] for f, v in diffs.items()}),
              open(out, "w"), ensure_ascii=False, indent=2)
    print("  -> %s" % out)


if __name__ == "__main__":
    main()
