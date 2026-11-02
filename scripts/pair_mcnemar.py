# -*- coding: utf-8 -*-
"""对任意两臂做配对单元 McNemar。用法：python pair_mcnemar.py <aware.jsonl> <blind.jsonl>"""
import collections
import json
import math
import sys

ROOT = "/data/projects/guardrails"
SC = {"ALLOW": 1.0, "REVIEW": 0.5, "DENY": 0.0, None: -1.0}


def load(p):
    d = {}
    for l in open(p, encoding="utf-8"):
        x = json.loads(l)
        d[x["sid"]] = x["pred"]
    return d


def main(pa, pb):
    rows = {json.loads(l)["sid"]: json.loads(l)
            for l in open(f"{ROOT}/data/pab_rd.jsonl", encoding="utf-8")}
    sp = json.load(open(f"{ROOT}/data/pab_rd_splits.json"))
    te = [rows[i] for i in sp["test"]]
    A, B = load(pa), load(pb)
    g = collections.defaultdict(lambda: {"ALLOW": [], "other": []})
    for r in te:
        g[r["current_action"]]["ALLOW" if r["label"] == "ALLOW" else "other"].append(r)
    b = c = both = neither = 0
    for k, v in g.items():
        for a in v["ALLOW"]:
            for o in v["other"]:
                okA = SC[A.get(a["sid"])] > SC[A.get(o["sid"])]
                okB = SC[B.get(a["sid"])] > SC[B.get(o["sid"])]
                if okA and not okB:
                    b += 1
                elif okB and not okA:
                    c += 1
                elif okA:
                    both += 1
                else:
                    neither += 1
    n = b + c + both + neither
    k = min(b, c)
    m = b + c
    p = min(1.0, 2 * sum(math.comb(m, i) for i in range(k + 1)) / 2 ** m) if m else 1.0
    d = 100.0 * (b - c) / n
    se = 100.0 * math.sqrt(max(m - (b - c) ** 2 / n, 1e-9)) / n
    print("%s vs %s" % (pa.split("/")[-1], pb.split("/")[-1]))
    print("  both %d | aware-only %d | blind-only %d | neither %d  (n=%d)"
          % (both, b, c, neither, n))
    print("  Δ = %+.1f pp  95%%CI [%+.1f,%+.1f]  McNemar p = %.4f"
          % (d, d - 1.96 * se, d + 1.96 * se, p))
    print("  acc: aware %.1f%%  blind %.1f%%"
          % (100 * (both + b) / n, 100 * (both + c) / n))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
