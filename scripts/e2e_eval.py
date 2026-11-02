# -*- coding: utf-8 -*-
"""端到端结果汇总：Benign Utility / ASR / 守卫成本，同一套定义。

指标（与 AgentDojo 官方口径一致，不做二次发明）
--------------------------------------------
Benign Utility : 干净场景（无注入）中，user task 的 utility 判定为真的比例。
ASR            : 受攻击场景中 security 判定为「被攻破」的比例。**越低越好**。
ScenDef        : 受攻击场景中攻击未得手的比例 = 1 − ASR。
Guard calls    : 守卫实际被调用的次数（= 执行边界上的工具调用数）。
BlockRate      : 守卫判 DENY 的比例；ReviewRate 单列（REVIEW 也会拦下执行）。
Latency        : 单次守卫判定的毫秒数（均值 / P95）。
Fallback       : 被守卫拦下后 agent 是否绕道成功——用 ASR 与 BlockRate 的差间接反映，
                 不做额外估计。
"""
import argparse
import glob
import json
import os
from collections import Counter

R = "/data/projects/guardrails"


def load(p):
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def pct(x, n):
    return round(100.0 * x / n, 1) if n else None


def summarize(suite, tag, d):
    scen = load(os.path.join(d, "scen.jsonl"))
    clean = [s for s in scen if not s.get("injection_present")]
    atk = [s for s in scen if s.get("injection_present")]
    hits = [h for s in scen for h in (s.get("guard_hits") or [])]
    ms = sorted(h.get("ms", 0) for h in hits if h.get("ms") is not None)
    dec = Counter(h.get("decision") for h in hits)
    util_clean = sum(1 for s in clean if s.get("utility"))
    util_atk = sum(1 for s in atk if s.get("utility"))
    broke = sum(1 for s in atk if s.get("security"))
    return dict(
        suite=suite, tag=tag, dir=d,
        n_clean=len(clean), n_attack=len(atk),
        benign_utility=pct(util_clean, len(clean)),
        utility_under_attack=pct(util_atk, len(atk)),
        ASR=broke, ASR_pct=pct(broke, len(atk)),
        scen_def=pct(len(atk) - broke, len(atk)),
        guard_calls=len(hits),
        deny_rate=pct(dec.get("DENY", 0), len(hits)),
        review_rate=pct(dec.get("REVIEW", 0), len(hits)),
        allow_rate=pct(dec.get("ALLOW", 0), len(hits)),
        decision_mix=dict(dec),
        ms_mean=round(sum(ms) / len(ms), 1) if ms else None,
        ms_p95=ms[int(0.95 * len(ms))] if ms else None,
        agent_fail=dict(Counter(s.get("agent_failure") for s in scen)),
        exposed=pct(sum(1 for s in atk if s.get("injection_exposed")), len(atk)),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True,
                    help="形如 banking:none:/path 或直接给目录（自动从路径推 suite/tag）")
    ap.add_argument("--out", default=os.path.join(R, "results/e2e/summary.json"))
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)

    rows = []
    for spec in a.runs:
        if spec.count(":") >= 2 and os.path.isdir(spec.split(":", 2)[2]):
            suite, tag, d = spec.split(":", 2)
        elif os.path.isdir(spec):
            parts = spec.rstrip("/").split("/")
            tag, suite, d = parts[-1], parts[-2], spec
        else:
            raise SystemExit("无法解析: %s" % spec)
        if not os.path.exists(os.path.join(d, "scen.jsonl")):
            print("[skip] %s 没有 scen.jsonl" % d)
            continue
        rows.append(summarize(suite, tag, d))

    json.dump(rows, open(a.out, "w"), ensure_ascii=False, indent=2)
    print("%-9s %-22s %5s %5s %7s %7s %6s %8s %6s %6s"
          % ("suite", "tag", "nCl", "nAtk", "Util", "ASR", "ScenD", "Blk%", "ms", "p95"))
    for r in rows:
        print("%-9s %-22s %5d %5d %7s %7s %6s %8s %6s %6s" % (
            r["suite"], r["tag"], r["n_clean"], r["n_attack"],
            r["benign_utility"], r["ASR_pct"], r["scen_def"],
            r["deny_rate"] if r["guard_calls"] else "-",
            r["ms_mean"] if r["ms_mean"] else "-", r["ms_p95"] if r["ms_p95"] else "-"))
    print("\n-> %s" % a.out)


if __name__ == "__main__":
    main()
