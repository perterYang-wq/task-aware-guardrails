# -*- coding: utf-8 -*-
"""M1/M2 的离线评测：PAB-RD test 上重算 PRA，并拆出「与 hardneg 任务不重叠」的子集。

为什么还要离线评测
------------------
本文的主张是「离线目标与线上攻击错位」，所以在换掉目标之后必须同时报告：
(a) 线上攻击拦截有没有涨（diag_score/diag_metrics 给）；
(b) 原来的离线目标有没有塌（本脚本给）。
只报 (a) 会被质疑「你只是把模型调成了更爱 DENY」；只报 (b) 等于没做事。

为什么要分子集
--------------
hardneg 的训练任务与 PAB-RD 有 24 个同名任务（都源自 AgentDojo 环境）。
为了区分「真学到授权边界」与「记住了任务」，这里同时报
PRA(all) 与 PRA(test \\ hardneg 任务)，后者不含任何训练期见过的任务。
"""
import argparse
import json
import os
import sys

ROOT = "/data/projects/guardrails"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from run_guard import pairwise  # noqa: E402

OUT = os.path.join(ROOT, "results/m2")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", nargs="+", required=True)
    ap.add_argument("--out", default=os.path.join(OUT, "offline_eval.json"))
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    pab = [json.loads(l) for l in open(os.path.join(ROOT, "data/pab_rd.jsonl"),
                                      encoding="utf-8")]
    by = {x["sid"]: x for x in pab}
    sp = json.load(open(os.path.join(ROOT, "data/pab_rd_splits.json")))
    sp = sp["pab"] if "pab" in sp else sp
    test_ids = sp["test"]

    hn_tasks = set()
    la = os.path.join(OUT, "leak_audit.json")
    if os.path.exists(la):
        d = json.load(open(la))
        hn_tasks = {tuple(x.split("/", 1)) for x in d.get("hardneg_tasks", [])}
    excl = {s for s in test_ids
            if (by[s].get("suite"), by[s].get("task_id")) in hn_tasks}

    rows = []
    for tag in a.tags:
        fn = os.path.join(ROOT, "results", "%s_test.jsonl" % tag)
        if not os.path.exists(fn):
            print("[skip] %s 缺预测 %s" % (tag, fn))
            continue
        preds = [json.loads(l) for l in open(fn, encoding="utf-8")]

        class R:
            __slots__ = ("label", "current_action", "pred")

        def pack(sel_ids=None):
            out, ids = [], []
            for i, p in enumerate(preds):
                sid = p.get("sid", test_ids[i] if i < len(test_ids) else None)
                if sel_ids is not None and sid not in sel_ids:
                    continue
                r = R()
                r.label = p["gold"]
                r.current_action = p.get("action") or ""
                r.pred = p["pred"]
                out.append(r)
                ids.append(sid)
            return out, ids

        def pra(rs):
            acc, n, n_act, _ = pairwise(rs, [x.pred for x in rs],
                                        key_fn=lambda x: x.current_action)
            from run_guard import SCORE
            w = t = l = 0
            g = {}
            for x in rs:
                g.setdefault(x.current_action, {"ALLOW": [], "other": []})[
                    "ALLOW" if x.label == "ALLOW" else "other"].append(x.pred)
            for v in g.values():
                for pa_ in v["ALLOW"]:
                    for po in v["other"]:
                        sa, so = SCORE[pa_], SCORE[po]
                        if sa > so:
                            w += 1
                        elif sa == so:
                            t += 1
                        else:
                            l += 1
            return dict(wins=w, ties=t, losses=l, n=n, n_actions=n_act,
                        PRA=round(acc, 4) if n else None)

        allr, _ = pack()
        subr, _ = pack(set(test_ids) - excl)
        rows.append(dict(tag=tag, n_test=len(test_ids), n_excl=len(excl),
                         all=pra(allr), clean=pra(subr)))

    json.dump(rows, open(a.out, "w"), ensure_ascii=False, indent=2)
    print("%-16s %-28s %-28s" % ("tag", "PRA(all)", "PRA(排除重叠任务)"))
    for r in rows:
        print("%-16s %-28s %-28s" % (
            r["tag"],
            "%.3f  (%d/%d/%d, n=%d)" % (r["all"]["PRA"], r["all"]["wins"],
                                        r["all"]["ties"], r["all"]["losses"], r["all"]["n"]),
            "%.3f  (n=%d)" % (r["clean"]["PRA"], r["clean"]["n"])))
    print("\n排除 %d/%d 条（落在 hardneg 见过的任务上）" % (len(excl), len(test_ids)))
    print("-> %s" % a.out)


if __name__ == "__main__":
    main()
