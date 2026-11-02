# -*- coding: utf-8 -*-
"""P2 零样本评测：严格最小对（action 与 evidence 逐字相同，仅 task 不同）。

要点
----
因为配对的两条记录 current_action 与 history 完全相同，任何只依赖 (action, evidence)
的打分函数在每一对上必得**相同**分数 => PRA 恒为 0.500、SPA 恒为 0.000。
所以这个集合上唯一可能的信号来源就是 instruction。我们据此衡量 P1 模型是否真的
用上了任务信息，而不是又在做接地检查。

分层报告：
    strict_test   正负任务都在 test（P1 从未见过）—— 主指标
    unseen        都在 val∪test
    contains_train 至少一方在 train（参考）
"""
import argparse
import collections
import json
import os
import re
import sys

import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from guard.schema import Step, parse_rating, render_pab  # noqa: E402
from unified_eval_v2 import macro_f1  # noqa: E402

PAIRS = os.path.join(ROOT, "data", "p2_pairs.jsonl")
P1 = os.path.join(ROOT, "results", "p1")
SC = {"ALLOW": 1.0, "REVIEW": 0.5, "DENY": 0.0}


def to_step(r):
    return Step(sid="%s|%s" % (r["pair_id"], r["pair_role"]), source="p2",
                instruction=r["instruction"], history=r["history"][:1200],
                current_action=r["current_action"], env_info="",
                score=SC[r["label"]], label=r["label"], tool=r["tool"],
                args={}, meta={"tier": tier_of(r), "reason": r["label_reason"],
                               "suite": r["suite"], "pair_id": r["pair_id"],
                               "role": r["pair_role"]})


def tier_of(r):
    ps = {r["part_auth"], r["part_deny"]}
    if ps == {"test"}:
        return "strict_test"
    if ps <= {"val", "test"}:
        return "unseen"
    return "contains_train"


def run_arm(model_path, adapter, rows, no_task, bs, max_new):
    tok = AutoTokenizer.from_pretrained(model_path, padding_side="left")
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        model_path, torch_dtype=torch.float16, device_map="cuda").eval()
    if adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, adapter).eval()
    texts = [tok.apply_chat_template(
        [{"role": "user", "content": render_pab(to_step(r), task_aware=not no_task)}],
        tokenize=False, add_generation_prompt=True) for r in rows]
    preds, raws = [], []
    with torch.no_grad():
        for i in range(0, len(texts), bs):
            enc = tok(texts[i:i + bs], return_tensors="pt", padding=True,
                      add_special_tokens=False).to("cuda")
            out = model.generate(**enc, max_new_tokens=max_new, do_sample=False,
                                 temperature=None, top_p=None, top_k=None,
                                 pad_token_id=tok.pad_token_id)
            for t in tok.batch_decode(out[:, enc["input_ids"].shape[1]:],
                                      skip_special_tokens=True):
                raws.append(t)
                preds.append(parse_rating(t))
    del model
    torch.cuda.empty_cache()
    return preds, raws


def pair_metrics(rows, preds, subset=None):
    by = collections.defaultdict(dict)
    for r, p in zip(rows, preds):
        by[r["pair_id"]][r["pair_role"]] = p
    w = t = l = 0
    for pid, d in by.items():
        if "positive" not in d or "negative" not in d:
            continue
        if subset is not None and not subset(pid):
            continue
        sp = SC.get(d["positive"], 0.5)
        sn = SC.get(d["negative"], 0.5)
        if sp > sn:
            w += 1
        elif sp == sn:
            t += 1
        else:
            l += 1
    n = w + t + l
    return ({"wins": w, "ties": t, "losses": l, "n_pairs": n,
             "PRA": (w + 0.5 * t) / n if n else float("nan"),
             "SPA": w / n if n else float("nan"),
             "TieRate": t / n if n else float("nan")}, by)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bs", type=int, default=16)
    ap.add_argument("--max-new", type=int, default=6)
    ap.add_argument("--models", default="15b,3b")
    ap.add_argument("--out", default=os.path.join(ROOT, "results", "p2", "p2_eval.json"))
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(PAIRS, encoding="utf-8")]
    print("P2 记录 %d 条 / 配对 %d 组"
          % (len(rows), len({r["pair_id"] for r in rows})), flush=True)
    tiers = collections.defaultdict(set)
    for r in rows:
        tiers[tier_of(r)].add(r["pair_id"])
    print("分层: %s" % {k: len(v) for k, v in tiers.items()}, flush=True)

    rec = json.load(open(os.path.join(P1, "p1_record.json"), encoding="utf-8"))
    M = {"15b": "/data/hf_cache/qwen1.5b", "3b": "/data/hf_cache/qwen3b"}

    # 确定性对照：只依赖 (action, evidence) 的打分器
    res = {"n_records": len(rows), "n_pairs": len({r["pair_id"] for r in rows}),
           "tiers": {k: len(v) for k, v in tiers.items()}, "arms": {}}
    for name, fn in (("const_ALLOW", lambda s: 1.0),
                     ("len(action+evidence)", lambda s: 1.0 / (1.0 + len(
                         s.current_action + s.history)))):
        preds = ["ALLOW" if fn(to_step(r)) > 0.5 else "DENY" for r in rows]
        m, _ = pair_metrics(rows, preds)
        res["arms"][name] = {"surface_only": True, **m}
        print("  [%-22s] PRA=%.3f SPA=%.3f" % (name, m["PRA"], m["SPA"]), flush=True)

    for model in a.models.split(","):
        model = model.strip()
        if model not in M:
            continue
        lrkey = rec["lr_choice"][model]["lrkey"]
        arms = [("zero-shot", "", False),
                ("task s0", "guard/adapters/p1_%s_task_%s_s0" % (model, lrkey), False),
                ("no-task s0", "guard/adapters/p1_%s_nt_%s_s0" % (model, lrkey), True)]
        for label, adapter, no_task in arms:
            ap_ = os.path.join(ROOT, adapter) if adapter else ""
            if adapter and not os.path.isdir(ap_):
                print("  [skip] %s %s adapter 不存在" % (model, label), flush=True)
                continue
            print("\n[%s | %s]" % (model, label), flush=True)
            preds, raws = run_arm(M[model], ap_, rows, no_task, a.bs, a.max_new)
            m, by = pair_metrics(rows, preds)
            unparsed = sum(1 for p in preds if p is None)
            out = {"surface_only": False, **m, "unparsed": unparsed / len(preds),
                   "by_tier": {}}
            for tname, pids in tiers.items():
                mt, _ = pair_metrics(rows, preds, subset=lambda pid, s=pids: pid in s)
                out["by_tier"][tname] = mt
            # 按负例理由与域分开
            for key, field in (("by_reason", "reason"), ("by_suite", "suite")):
                out[key] = {}
                groups = collections.defaultdict(set)
                for r in rows:
                    groups[r[field]].add(r["pair_id"])
                for g, pids in groups.items():
                    mt, _ = pair_metrics(rows, preds, subset=lambda pid, s=pids: pid in s)
                    if mt["n_pairs"] >= 5:
                        out[key][g] = mt
            # 逐条落盘，供失败分类
            pd = os.path.join(ROOT, "results", "p2", "preds")
            os.makedirs(pd, exist_ok=True)
            fn = os.path.join(pd, "%s_%s.jsonl" % (model, label.replace(" ", "_")))
            with open(fn, "w", encoding="utf-8") as f:
                for r, pr_, rw in zip(rows, preds, raws):
                    f.write(json.dumps(dict(
                        pair_id=r["pair_id"], role=r["pair_role"], gold=r["label"],
                        pred=pr_, raw=rw[:120], tier=tier_of(r),
                        suite=r["suite"], reason=r["label_reason"],
                        tool=r["tool"], task_id=r["task_id"],
                        instruction=r["instruction"][:200]), ensure_ascii=False) + "\n")
            out["pred_file"] = os.path.relpath(fn, ROOT)
            model_key = "%s|%s" % (model, label)
            res["arms"][model_key] = out
            print("  PRA=%.3f SPA=%.3f Tie=%.3f macroF1=%.3f unparsed=%.3f"
                  % (m["PRA"], m["SPA"], m["TieRate"],
                     macro_f1([r["label"] for r in rows], [p or "REVIEW" for p in preds]),
                     unparsed / len(preds)), flush=True)
            for tname in ("strict_test", "unseen", "contains_train"):
                if tname in out["by_tier"] and out["by_tier"][tname]["n_pairs"]:
                    mt = out["by_tier"][tname]
                    print("    %-14s n=%-3d PRA=%.3f SPA=%.3f"
                          % (tname, mt["n_pairs"], mt["PRA"], mt["SPA"]), flush=True)

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n-> %s" % a.out)


if __name__ == "__main__":
    main()
