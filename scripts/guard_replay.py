# -*- coding: utf-8 -*-
"""把外部基线在诊断集上回放一遍，产出与 diag_score 同格式的预测。

这样 `diag_metrics.py` 不用改一行就能把规则 / PG2 和训练过的守卫放在同一张表里比较
（ACB / CCB / 场景防御 / dInj 全部同一套定义）。

注意：这是**离线回放**，只用已采集轨迹里的调用序列，不重跑 agent；
所以它衡量的是"这些基线在同样这些调用上会怎么判"，不是端到端 ASR。
端到端由 e2e_guard.sh 真跑。

    python scripts/guard_replay.py --guard rule:gamma
    python scripts/guard_replay.py --guard rule:ground
    python scripts/guard_replay.py --guard pg2
"""
import argparse
import json
import os
import sys

R = "/data/projects/guardrails"
sys.path.insert(0, R)
sys.path.insert(0, os.path.join(R, "scripts"))

DIAG = os.path.join(R, "results/diag")
PRED = os.path.join(DIAG, "preds")
VIEWS = ("none", "last3", "full", "noinj")


def make(spec):
    if spec.startswith("rule:"):
        from rule_guard import RuleGuard
        g = RuleGuard(spec.split(":", 1)[1])
        return g, spec.split(":", 1)[1].replace("ground", "ground")
    if spec == "pg2":
        from pg2_guard import PG2Guard
        return PG2Guard(), "pg2"
    raise SystemExit("未知基线: %s" % spec)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--guard", required=True)
    ap.add_argument("--tag", default="")
    ap.add_argument("--views", default="none,last3,full,noinj")
    a = ap.parse_args()
    os.makedirs(PRED, exist_ok=True)

    guard, name = make(a.guard)
    tag = a.tag or ("rule_" + name if not a.guard.startswith("rule:") or True else name)
    if a.guard == "pg2":
        tag = "pg2_86m"
    elif a.guard.startswith("rule:"):
        tag = "rule_" + a.guard.split(":", 1)[1]

    rows = [json.loads(l) for l in open(os.path.join(DIAG, "steps.jsonl"), encoding="utf-8")]
    for view in [v.strip() for v in a.views.split(",")]:
        out = []
        for r in rows:
            # 规则/PG2 都要用渲染后的动作文本，与训练过的守卫保持同一输入构造
            lab, raw = guard.decide(r["instruction"], r.get("hist_" + view) or "",
                                    r["current_action"])
            out.append(dict(sid=r["sid"], pred=lab, raw=raw, ntok=0))
        p = os.path.join(PRED, "%s__%s.jsonl" % (tag, view))
        with open(p, "w", encoding="utf-8") as f:
            for x in out:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
        c = {}
        for x in out:
            c[x["pred"]] = c.get(x["pred"], 0) + 1
        print("%-14s %-6s %s -> %s" % (tag, view, c, os.path.basename(p)))


if __name__ == "__main__":
    main()
