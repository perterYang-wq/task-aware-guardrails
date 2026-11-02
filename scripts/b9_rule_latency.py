# -*- coding: utf-8 -*-
"""纯规则臂的单次判定延迟（CPU，无模型）。

与 B10-1 的纯硬规则臂同一协议：取 slack 63 场景里的全部真实调用，
逐条喂给 RuleGuard(mode="gamma")，测 decide() 的墙钟时间。
同时给 M1 / Task-Shield 的端到端判定延迟做同一张表的口径说明（那两个数
来自 reports/b3_tshield.md 的 e2e 计时，本脚本只读取不改写）。

产物：results/classifier/latency_rule_cpu.json
"""
import json
import os
import statistics
import sys
import time

R = "/data/projects/guardrails"
sys.path.insert(0, R)
sys.path.insert(0, os.path.join(R, "scripts"))
from rule_guard import RuleGuard  # noqa: E402

RUN = "results/e2e/slack/hard_b10_inj1-3"
OUT = os.path.join(R, "results/classifier/latency_rule_cpu.json")


def main():
    rows = [json.loads(l) for l in open(os.path.join(R, RUN, "scen.jsonl"), encoding="utf-8")]
    g = RuleGuard(mode="gamma")
    items = []
    for r in rows:
        for c in (r.get("calls") or []):
            items.append((r.get("instruction") or "", c.get("history_full") or "",
                          c.get("current_action") or ""))
    # 历史可能不存在 calls 的 history_full，退化为空 history（规则不看 history）
    times = []
    for _ in range(3):  # warmup
        for it in items[:20]:
            g.decide(*it)
    for it in items:
        t0 = time.perf_counter()
        g.decide(*it)
        times.append((time.perf_counter() - t0) * 1000.0)
    times.sort()
    rec = dict(n=len(times), mean=round(statistics.mean(times), 4),
               p50=round(statistics.median(times), 4),
               p95=round(times[int(0.95 * (len(times) - 1))], 4),
               max=round(times[-1], 4), device="cpu", unit="ms",
               run=RUN, note="RuleGuard(mode=gamma) 纯字符串规则，无模型")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(rec, open(OUT, "w"), ensure_ascii=False, indent=2)
    print(json.dumps(rec, ensure_ascii=False))


if __name__ == "__main__":
    main()
