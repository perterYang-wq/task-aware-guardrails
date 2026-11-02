# -*- coding: utf-8 -*-
"""M2：从成功攻击轨迹里抽 hard negative，并做两种反事实增强。

构造原则
--------
1. **只在训练套件上抽**（banking / slack），travel 整族留出作未见套件。
2. hard negative = 攻击生效那一步的 tool call，历史用**被污染的完整历史**。
   训练时就要让模型看到「局部自洽但服务于攻击者」的调用——这正是
   离线 PAB-RD 从不包含的形态。
3. 同一调用的**反事实视图** `noinj`：证据、轮次、工具输出全同，只删掉
   <INFORMATION> 载荷。标签仍是 DENY。作用是告诉模型：
   「即使不给你那段话，这个调用也不被授权」，切断「靠载荷文本判危险」的捷径。
   （该视图只在训练期使用；推理仍只喂 full 视图。）
4. clean alternative = 同任务干净运行里**同一工具**的真实调用，用**同一段
   污染历史**渲染，标签 ALLOW。成对样本只差调用参数，模型不能靠工具名区分。
   找不到同工具替代的攻击调用只保留为单边负例，**不**用别的工具凑数。

输出
----
`data/hardneg.jsonl`（Step 兼容）与 `results/m2/hardneg_stats.json`
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict

R = "/data/projects/guardrails"
sys.path.insert(0, R)
from guard.schema import Step, render_pab  # noqa: E402

OUT_DIR = os.path.join(R, "results/m2")
TRAIN_SUITES = ("banking", "slack")
HELD_OUT = ("travel",)

ACTION_TPL = "(1) Thought: (omitted)\n(2) Action: %s\n(3) Action Input: %s"


def act(tool, args):
    return ACTION_TPL % (tool, json.dumps(args or {}, ensure_ascii=False))


def mk(sid, source, r, hist, cur, label, score, tool, args, meta):
    return dict(sid=sid, source=source, instruction=r["instruction"], history=hist,
                current_action=cur, env_info="", score=score, label=label,
                tool=tool, args=args, meta=meta)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(R, "data/hardneg.jsonl"))
    ap.add_argument("--model", default="/data/hf_cache/qwen1.5b")
    ap.add_argument("--noinj", action="store_true", default=True)
    a = ap.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)

    steps = [json.loads(l) for l in open(os.path.join(R, "results/diag/steps.jsonl"),
                                         encoding="utf-8")]
    by_task = defaultdict(list)
    for r in steps:
        by_task[(r["suite"], r["task_id"])].append(r)

    recs, stats, pair_ids = [], defaultdict(Counter), []
    for r in steps:
        if r["suite"] not in TRAIN_SUITES or r["label"] != "DENY":
            continue
        base = dict(suite=r["suite"], task_id=r["task_id"],
                    injection_task=r["injection_task"], step_idx=r["step_idx"],
                    provenance=r["provenance"], gamma=r["gamma"], tool=r["tool"])
        neg = mk("hn#%s" % r["sid"], "hardneg", r, r["hist_full"], r["current_action"],
                 "DENY", 1.0, r["tool"], r["args"], dict(base, kind="hardneg_full"))
        recs.append(neg)
        stats[r["suite"]]["hardneg"] += 1
        stats[r["suite"]]["prov_" + r["provenance"]] += 1
        if a.noinj and r["hist_noinj"] != r["hist_full"]:
            recs.append(mk("hn_noinj#%s" % r["sid"], "hardneg", r, r["hist_noinj"],
                           r["current_action"], "DENY", 1.0, r["tool"], r["args"],
                           dict(base, kind="hardneg_noinj")))
            stats[r["suite"]]["hardneg_noinj"] += 1

        # ---- clean alternative：同任务干净运行、**同工具**、最近 step
        clean = [x for x in by_task[(r["suite"], r["task_id"])] if x["injection_task"] is None]
        cand = [x for x in clean if x["tool"] == r["tool"]]
        if not cand:
            stats[r["suite"]]["no_same_tool_alt"] += 1
            continue
        alt = min(cand, key=lambda x: abs(x["step_idx"] - r["step_idx"]))
        pid = "pair#%s" % r["sid"]
        neg["meta"]["pair_id"] = pid          # 必须写回负例，否则配对项在训练时会被丢掉
        recs.append(mk("ca#%s" % r["sid"], "clean_alt", r, r["hist_full"],
                       alt["current_action"], "ALLOW", 0.0, alt["tool"], alt["args"],
                       dict(base, kind="clean_alt", pair_id=pid,
                            step_gap=abs(alt["step_idx"] - r["step_idx"]),
                            tool=alt["tool"])))
        pair_ids.append(dict(pair_id=pid, suite=r["suite"], tool=r["tool"],
                             step_gap=abs(alt["step_idx"] - r["step_idx"])))

    with open(a.out, "w", encoding="utf-8") as f:
        for x in recs:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")

    # ---- token 长度（真实 chat template，训练预算按这个定）
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(a.model)
    lens = []
    for x in recs:
        st = Step(sid="", source="", instruction=x["instruction"], history=x["history"],
                  current_action=x["current_action"], env_info="", score=0.0,
                  label="", tool=x["tool"], args=x["args"])
        txt = tok.apply_chat_template([{"role": "user", "content": render_pab(st, True)}],
                                      tokenize=False, add_generation_prompt=True)
        lens.append(len(tok(txt, add_special_tokens=False).input_ids))
    L = sorted(lens)
    meta = dict(n_records=len(recs), n_pairs=len(pair_ids),
                per_suite={k: dict(v) for k, v in stats.items()},
                held_out=list(HELD_OUT),
                tokens=dict(mean=round(sum(L) / len(L), 1), p50=L[len(L) // 2],
                            p95=L[int(0.95 * len(L))], mx=L[-1],
                            over1024=sum(1 for n in L if n > 1024),
                            over1536=sum(1 for n in L if n > 1536)),
                tools=dict(Counter(x["tool"] for x in recs).most_common(12)),
                step_gap=dict(Counter(min(p["step_gap"], 5) for p in pair_ids)),
                n_labels=dict(Counter(x["label"] for x in recs)))
    json.dump(meta, open(os.path.join(OUT_DIR, "hardneg_stats.json"), "w"),
              ensure_ascii=False, indent=2)
    json.dump(pair_ids, open(os.path.join(OUT_DIR, "pairs.json"), "w"), ensure_ascii=False)
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
