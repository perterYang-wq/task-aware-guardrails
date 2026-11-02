# -*- coding: utf-8 -*-
"""把已有预测（run_b3 输出的 jsonl）按指定划分的 test 子集重新算指标。

用途：B3 是在全量 7182 上跑的，而 O1 只在 split 的 test 上评测。
必须能事后把 B3 限制到同一个 test 子集，否则两行数字不可比。
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from guard.metrics import evaluate  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True, nargs="+")
    ap.add_argument("--split", default="")
    ap.add_argument("--part", default="test", choices=["test", "val", "train"])
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    keep = None
    if a.split:
        keep = set(json.load(open(os.path.join(ROOT, "data", "splits.json")))[a.split][a.part])
        print("限制到 split=%s/%s  n=%d" % (a.split, a.part, len(keep)))

    allres = {}
    for p in a.pred:
        rows = [json.loads(l) for l in open(p, encoding="utf-8")]
        if keep is not None:
            rows = [r for r in rows if r["sid"] in keep]
        tag = os.path.basename(p).replace(".jsonl", "")
        allres[tag] = evaluate([r["gold"] for r in rows],
                               [r["pred"] for r in rows], tag)
    if a.out:
        json.dump(allres, open(a.out, "w"), ensure_ascii=False, indent=1)
        print("-> %s" % a.out)


if __name__ == "__main__":
    main()
