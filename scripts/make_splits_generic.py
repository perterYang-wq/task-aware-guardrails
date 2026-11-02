# -*- coding: utf-8 -*-
"""通用按任务分组的划分器：--data / --out / --key。"""
import argparse, collections, json, os, random, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--train", type=float, default=0.65)
    ap.add_argument("--val", type=float, default=0.10)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.data, encoding="utf-8")]
    g = collections.defaultdict(list)
    for r in rows:
        g[(r["suite"], r["task_id"])].append(r)
    keys = sorted(g)
    random.Random(a.seed).shuffle(keys)
    n = len(keys); ntr = int(a.train * n); nva = int(a.val * n)
    out = {"train": [], "val": [], "test": []}
    for i, k in enumerate(keys):
        part = "train" if i < ntr else ("val" if i < ntr + nva else "test")
        out[part].extend(r["sid"] for r in g[k])
    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=0)
    by = {r["sid"]: r for r in rows}
    print("n=%d  tasks=%d  train/val/test = %d/%d/%d"
          % (len(rows), n, len(out["train"]), len(out["val"]), len(out["test"])))
    for p in ("train", "val", "test"):
        c = collections.Counter(by[i]["label"] for i in out[p])
        print("  %-6s ALLOW=%d REVIEW=%d DENY=%d" % (p, c["ALLOW"], c["REVIEW"], c["DENY"]))

if __name__ == "__main__":
    main()
