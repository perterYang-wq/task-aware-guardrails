# -*- coding: utf-8 -*-
"""M2 平衡版：hard negative + **同工具、同被污染上下文**的合法正例。

为什么需要这一版
----------------
`data/hardneg.jsonl` 里 DENY 188 条（94 full + 94 noinj）、ALLOW 只有 29 条。
用这份数据训练出的 HV 臂退化成了**动作先验**：DENY 率从 6.6% 涨到 27.5%，
干净场景误拦截 31.3%、零打扰率 0，`dInj` 恰好为 0（不再看载荷，也不再看请求）。
机制很清楚：noinj 视图把「载荷」这条线索抽掉了，模型只剩「动作本身可疑」可学。

这一版的做法
------------
1. **去掉 noinj**（它是动作先验的来源），保留 full 视图的 hard negative。
2. 为每个攻击工具补**同工具**的合法正例，且这些正例本身来自**被注入的场景**
   （历史同样被污染），标签 ALLOW。这样模型要区分的是同一工具、同一污染上下文下
   「谁授权了这次调用」，而不是「这个工具危险不危险」。
3. 按攻击的工具分布配比 ×2 采样，工具内去重，跨任务优先。

输出 `data/hardneg_bal.jsonl`，其余字段与原版一致（Step 兼容）。
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

TRAIN = {"banking", "slack"}
ACT = "(1) Thought: (omitted)\n(2) Action: %s\n(3) Action Input: %s"


def act(t, a):
    return ACT % (t, json.dumps(a or {}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(R, "data/hardneg.jsonl"))
    ap.add_argument("--out", default=os.path.join(R, "data/hardneg_bal.jsonl"))
    ap.add_argument("--per-attack", type=int, default=2)
    a = ap.parse_args()

    base = [json.loads(l) for l in open(a.src, encoding="utf-8")]
    keep = [x for x in base if x["meta"].get("kind") != "hardneg_noinj"]
    drop_noinj = len(base) - len(keep)

    steps = [json.loads(l) for l in open(os.path.join(R, "results/diag/steps.jsonl"),
                                         encoding="utf-8")]
    att = [r for r in steps if r["suite"] in TRAIN and r["label"] == "DENY"]
    pool = defaultdict(list)
    for r in steps:
        if (r["suite"] in TRAIN and r["label"] == "ALLOW"
                and r["in_attacked_scenario"]):
            pool[r["tool"]].append(r)
    for t in pool:
        pool[t].sort(key=lambda x: hashlib.md5(x["sid"].encode()).hexdigest())

    need = Counter(r["tool"] for r in att)
    chosen, seen = [], set()
    for tool, n in need.items():
        want = a.per_attack * n
        for r in pool.get(tool, [])[:want]:
            if r["sid"] in seen:
                continue
            seen.add(r["sid"])
            chosen.append(dict(
                sid="li#%s" % r["sid"], source="legit_inj", instruction=r["instruction"],
                history=r["hist_full"], current_action=r["current_action"],
                env_info="", score=0.0, label="ALLOW", tool=r["tool"], args=r["args"],
                meta=dict(kind="legit_inj", suite=r["suite"], task_id=r["task_id"],
                          injection_task=r["injection_task"], step_idx=r["step_idx"],
                          gamma=gamma_of(r["tool"]))))

    out = keep + chosen
    with open(a.out, "w", encoding="utf-8") as f:
        for x in out:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")

    lab = Counter(x["label"] for x in out)
    tools = Counter(x["tool"] for x in out if x["meta"].get("kind") == "legit_inj")
    print(json.dumps(dict(
        n=len(out), drop_noinj=drop_noinj, labels=dict(lab),
        added_legit_inj=len(chosen), per_tool=dict(tools),
        balance=round(lab["ALLOW"] / max(1, lab["DENY"]), 3),
    ), ensure_ascii=False, indent=2))
    print("->", a.out)


if __name__ == "__main__":
    main()
