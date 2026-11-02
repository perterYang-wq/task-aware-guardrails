# -*- coding: utf-8 -*-
"""通用推理 + 评测：任意数据集 / 划分 / prompt 风格 / LoRA adapter。

同时报告两个指标：
  macro-F1        全测试集，会被"猜多数类"抬高
  配对准确率      只比较同一动作文本的 ALLOW vs 非 ALLOW，恒等输入必定 50%
两者的差距就是"表面拟合"与"任务条件化"的差距。
"""
import argparse
import collections
import json
import math
import os
import sys

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from guard.metrics import evaluate  # noqa: E402
from guard.schema import parse_rating, render_fitted, step_from_dict  # noqa: E402

SCORE = {"ALLOW": 1.0, "REVIEW": 0.5, "DENY": 0.0, None: -1.0}


def load_part(data_p, splits_p, split, part):
    """split 为空时把 splits 文件的顶层当作 train/val/test。"""
    rows = [step_from_dict(json.loads(l)) for l in open(data_p, encoding="utf-8")]
    if splits_p:
        sp = json.load(open(splits_p))
        sp = sp[split] if split else sp
        keep = set(sp[part])
        rows = [r for r in rows if r.sid in keep]
    return rows


def pairwise(rows, preds, key_fn):
    """按 key 分组配对：同一 key 内的 ALLOW 与非 ALLOW 各取一条比较。"""
    g = collections.defaultdict(lambda: {"ALLOW": [], "other": []})
    for r, p in zip(rows, preds):
        g[key_fn(r)]["ALLOW" if r.label == "ALLOW" else "other"].append(p)
    win = tie = n = 0
    per = collections.defaultdict(lambda: [0.0, 0])
    for k, v in g.items():
        for a in v["ALLOW"]:
            for o in v["other"]:
                sa, so = SCORE[a], SCORE[o]
                if sa > so:
                    win += 1
                    per[k][0] += 1.0
                elif sa == so:
                    tie += 1
                    per[k][0] += 0.5
                per[k][1] += 1
                n += 1
    acc = (win + 0.5 * tie) / n if n else 0.0
    pa = [v[0] / v[1] for v in per.values() if v[1]]
    return acc, n, len(pa), pa


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(ROOT, "data", "pab.jsonl"))
    ap.add_argument("--splits", default=os.path.join(ROOT, "data", "pab_splits.json"))
    ap.add_argument("--split", default="")
    ap.add_argument("--part", default="test", choices=["test", "val", "train"])
    ap.add_argument("--style", default="pab", choices=["pab", "short", "official"])
    ap.add_argument("--model", default="/data/hf_cache/qwen1.5b")
    ap.add_argument("--adapter", default="")
    ap.add_argument("--no-task", action="store_true")
    ap.add_argument("--bs", type=int, default=12)
    ap.add_argument("--max-new", type=int, default=6)
    ap.add_argument("--max-len", type=int, default=1280)
    ap.add_argument("--tag", required=True)
    a = ap.parse_args()

    rows = load_part(a.data, a.splits, a.split, a.part)
    tag = "%s_%s" % (a.tag, a.part)
    print("n=%d  style=%s  adapter=%s  task_aware=%s"
          % (len(rows), a.style, a.adapter or "-", not a.no_task), flush=True)

    tok = AutoTokenizer.from_pretrained(a.model, padding_side="left")
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        a.model, torch_dtype=torch.float16, device_map="cuda").eval()
    if a.adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, a.adapter).eval()

    texts = [tok.apply_chat_template(
        [{"role": "user", "content": render_fitted(
            tok, r, a.max_len - 8, style=a.style, task_aware=not a.no_task)}],
        tokenize=False, add_generation_prompt=True) for r in rows]

    preds, raws = [], []
    with torch.no_grad():
        for i in range(0, len(texts), a.bs):
            enc = tok(texts[i:i + a.bs], return_tensors="pt", padding=True,
                      add_special_tokens=False).to("cuda")
            out = model.generate(**enc, max_new_tokens=a.max_new, do_sample=False,
                                 temperature=None, top_p=None, top_k=None,
                                 pad_token_id=tok.pad_token_id)
            for t in tok.batch_decode(out[:, enc["input_ids"].shape[1]:],
                                      skip_special_tokens=True):
                raws.append(t)
                preds.append(parse_rating(t))
            if (i // a.bs) % 10 == 0:
                print("  %d/%d" % (min(i + a.bs, len(texts)), len(texts)), flush=True)

    gold = [r.label for r in rows]
    res = evaluate(gold, preds, tag)
    out_p = os.path.join(ROOT, "results", "%s.jsonl" % tag)
    with open(out_p, "w", encoding="utf-8") as f:
        for r, p, raw in zip(rows, preds, raws):
            f.write(json.dumps(dict(sid=r.sid, gold=r.label, pred=p, raw=raw[:300],
                                    action=r.current_action, flavor=r.meta.get("flavor")),
                               ensure_ascii=False) + "\n")

    # 配对准确率：同动作文本
    acc, n, na, per = pairwise(rows, preds, lambda r: r.current_action)
    print("\n配对准确率（同动作文本）= %.1f%%  配对数=%d  动作数=%d" % (100 * acc, n, na))
    if n:
        se = math.sqrt(max(acc * (1 - acc) / n, 1e-12))
        print("  95%% CI = [%.1f%%, %.1f%%]" % (100 * max(0, acc - 1.96 * se),
                                               100 * min(1, acc + 1.96 * se)))
    if per:
        above = sum(1 for v in per if v > 0.5)
        below = sum(1 for v in per if v < 0.5)
        k, m = min(above, below), above + below
        p = (sum(math.comb(m, i) for i in range(k + 1)) / 2 ** m * 2) if m else 1.0
        print("  动作级: 高于50%%=%d 低于50%%=%d 双侧 p=%.4f"
              % (above, below, min(1.0, p)))

    res.update({"pair_acc": acc, "n_pairs": n, "n_actions": na})
    json.dump(res, open(os.path.join(ROOT, "results", "%s_metrics.json" % tag), "w"),
              ensure_ascii=False, indent=1)
    print("-> results/%s.jsonl" % tag)


if __name__ == "__main__":
    main()
