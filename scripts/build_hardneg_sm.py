# -*- coding: utf-8 -*-
"""HB-sm：size-matched 对照 —— 只打散「正例所处的污染上下文」。

要排除的解释
------------
HB 的效果可能只是「加了正例、类别更平衡」，而不是「在**被污染的上下文**里看到
合法对照」。HB 的正例全部来自含注入载荷的场景（131 条 legit-in-injected
+ 29 条同场景干净替代），这是它最核心的设计。

HB-sm 的做法（只改一个变量）
--------------------------
负例、正例的数量、比例、工具分布、标签、参数全部不变，唯一改动是：
把每条正例的 history 换成同一条调用的 `hist_noinj`（删掉 <INFORMATION> 载荷，
证据块不变）。于是

    HB    : 正例 = 合法调用 + 含注入的上下文 -> ALLOW
    HB-sm : 正例 = 同一个调用 + 不含注入的上下文 -> ALLOW

如果 HB-sm 与 HB 相当，说明「污染上下文里的合法对照」不是有效成分，只是类别平衡；
如果 HB-sm 明显更差，说明这条设计确实是机制的一部分。

（--mode random 给一个更朴素的对照：正例全换成干净场景的随机合法调用，
工具分布无法完全对齐，仅作补充。）

输出 ``data/hardneg_sm.jsonl``。
"""
import argparse
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict

R = "/data/projects/guardrails"
sys.path.insert(0, R)
from guard.router import gamma_of  # noqa: E402

HB = os.path.join(R, "data/hardneg_bal.jsonl")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(R, "data/hardneg_sm.jsonl"))
    ap.add_argument("--mode", default="deinj", choices=["deinj", "random"])
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    hb = [json.loads(l) for l in open(HB, encoding="utf-8")]
    steps = {r["sid"]: r for r in
             (json.loads(l) for l in open(os.path.join(R, "results/diag/steps.jsonl"),
                                          encoding="utf-8"))}
    negs = [x for x in hb if x["label"] == "DENY"]
    poss = [x for x in hb if x["label"] == "ALLOW"]
    print("HB: DENY %d / ALLOW %d" % (len(negs), len(poss)))

    out = list(negs)
    n_changed = 0
    if a.mode == "deinj":
        for x in poss:
            sid = x["sid"].split("#", 1)[1]
            st = steps.get(sid)
            y = dict(x)
            if st is not None and st["hist_noinj"] != st["hist_full"]:
                y["history"] = st["hist_noinj"]
                n_changed += 1
            y["sid"] = "sm#" + x["sid"]
            y["source"] = "legit_deinj"
            y["meta"] = dict(x["meta"], kind="legit_deinj")
            out.append(y)
    else:
        need = Counter(x["tool"] for x in poss)
        pool = defaultdict(list)
        for r in steps.values():
            if r["label"] == "ALLOW" and not r["in_attacked_scenario"]:
                pool[r["tool"]].append(r)
        for t in pool:
            pool[t].sort(key=lambda z: hashlib.md5(
                ("%d|" % a.seed + z["sid"]).encode()).hexdigest())
        used, chosen = set(), []
        for tool, n in need.most_common():
            for r in [z for z in pool.get(tool, []) if z["sid"] not in used][:n]:
                used.add(r["sid"])
                chosen.append(r)
        rest = [r for t in pool for r in pool[t] if r["sid"] not in used]
        rest.sort(key=lambda z: hashlib.md5(("r%d|" % a.seed + z["sid"]).encode()).hexdigest())
        chosen += rest[:max(0, len(poss) - len(chosen))]
        for r in chosen[:len(poss)]:
            out.append(dict(sid="sm#%s" % r["sid"], source="legit_clean",
                            instruction=r["instruction"], history=r["hist_full"],
                            current_action=r["current_action"], env_info="", score=0.0,
                            label="ALLOW", tool=r["tool"], args=r["args"],
                            meta=dict(kind="legit_clean", suite=r["suite"],
                                      task_id=r["task_id"], injection_task=None,
                                      step_idx=r["step_idx"], gamma=gamma_of(r["tool"]))))
            n_changed += 1

    with open(a.out, "w", encoding="utf-8") as f:
        for x in out:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")

    lab = Counter(x["label"] for x in out)
    pos_tools = Counter(x["tool"] for x in out if x["label"] == "ALLOW")
    inj = sum(1 for x in out if x["label"] == "ALLOW" and "<INFORMATION>" in (x["history"] or ""))
    meta = dict(mode=a.mode, n=len(out), labels=dict(lab),
                balance=round(lab["ALLOW"] / max(1, lab["DENY"]), 3),
                pos_tools=dict(pos_tools), n_modified=n_changed,
                pos_with_inj_mark=inj)
    json.dump(meta, open(os.path.join(R, "results/m2/hardneg_sm_stats.json"), "w"),
              ensure_ascii=False, indent=2)
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print("->", a.out)


if __name__ == "__main__":
    main()
