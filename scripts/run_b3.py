# -*- coding: utf-8 -*-
"""B3：Qwen2.5-1.5B-Instruct zero-shot 作为 step-level guard。

两种条件：
  默认      —— 使用 ToolSafe 官方 TS-Guard prompt（含 user request）
  --no-task —— 把 user request 替换为 (not provided)，测任务信息的边际贡献

输出：results/b3_<tag>.jsonl（逐条预测）+ 控制台指标。
"""
import argparse
import collections
import json
import os
import sys
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from guard.schema import (CLASSES, Step, parse_rating, render_prompt,  # noqa: E402
                          render_prompt_short)


def load(path):
    out = []
    for line in open(path, encoding="utf-8"):
        d = json.loads(line)
        out.append(Step(**d))
    return out


def metrics(gold, pred, tag):
    """gold/pred 都是标签字符串；pred 为 None 表示解析失败（计为错误）。"""
    n = len(gold)
    ok = sum(1 for g, p in zip(gold, pred) if g == p)
    print("\n[%s] n=%d  acc=%.4f  解析失败=%d (%.1f%%)"
          % (tag, n, ok / n, sum(1 for p in pred if p is None),
             100 * sum(1 for p in pred if p is None) / n))
    res = {"n": n, "acc": ok / n}
    print("%-8s%8s%8s%8s%8s" % ("class", "P", "R", "F1", "support"))
    f1s = []
    for c in CLASSES:
        tp = sum(1 for g, p in zip(gold, pred) if g == c and p == c)
        fp = sum(1 for g, p in zip(gold, pred) if g != c and p == c)
        fn = sum(1 for g, p in zip(gold, pred) if g == c and p != c)
        sup = sum(1 for g in gold if g == c)
        P = tp / (tp + fp) if tp + fp else 0.0
        R = tp / (tp + fn) if tp + fn else 0.0
        F = 2 * P * R / (P + R) if P + R else 0.0
        f1s.append(F)
        res[c] = {"P": P, "R": R, "F1": F, "support": sup}
        print("%-8s%8.3f%8.3f%8.3f%8d" % (c, P, R, F, sup))
    res["macro_f1"] = sum(f1s) / len(f1s)
    print("macro-F1 = %.4f" % res["macro_f1"])
    cm = collections.Counter((g, p) for g, p in zip(gold, pred))
    print("混淆（行=gold, 列=pred）:")
    print("        " + "".join("%9s" % c for c in CLASSES + ["None"]))
    for g in CLASSES:
        print("%-8s" % g + "".join("%9d" % cm.get((g, p), 0) for p in CLASSES + [None]))
    res["confusion"] = {"%s|%s" % k: v for k, v in cm.items()}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="/data/hf_cache/qwen1.5b")
    ap.add_argument("--data", default=os.path.join(ROOT, "data", "tsbench_unified.jsonl"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--shuffle", type=int, default=-1,
                    help="打散种子；>=0 时先按该种子洗牌再取 limit")
    ap.add_argument("--sources", default="", help="逗号分隔的子集名，空=全部")
    ap.add_argument("--no-task", action="store_true")
    ap.add_argument("--bs", type=int, default=8)
    ap.add_argument("--max-new", type=int, default=160)
    ap.add_argument("--max-in", type=int, default=2048)
    ap.add_argument("--tag", default="")
    ap.add_argument("--prompt-style", default="official",
                    choices=["official", "short"])
    a = ap.parse_args()

    tag = a.tag or ("%s_%s%s" % (a.prompt_style, "notask" if a.no_task else "task",
                                 "" if a.prompt_style == "official" else ""))
    steps = load(a.data)
    if a.sources:
        keep = set(a.sources.split(","))
        steps = [s for s in steps if s.source in keep]
    if a.shuffle >= 0:
        import random
        random.Random(a.shuffle).shuffle(steps)
    if a.limit:
        steps = steps[:a.limit]
    print("model=%s  style=%s  cond=%s  n=%d" % (
        a.model, a.prompt_style, "NO-TASK" if a.no_task else "TASK", len(steps)))

    tok = AutoTokenizer.from_pretrained(a.model, padding_side="left")
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        a.model, torch_dtype=torch.float16, device_map="cuda").eval()

    prompts = []
    for s in steps:
        fn = render_prompt if a.prompt_style == "official" else render_prompt_short
        user = fn(s, task_aware=not a.no_task)
        prompts.append(tok.apply_chat_template(
            [{"role": "user", "content": user}],
            tokenize=False, add_generation_prompt=True))

    preds, raws = [], []
    t0 = time.time()
    with torch.no_grad():
        for i in range(0, len(prompts), a.bs):
            chunk = prompts[i:i + a.bs]
            enc = tok(chunk, return_tensors="pt", padding=True, truncation=True,
                      max_length=a.max_in).to("cuda")
            out = model.generate(**enc, max_new_tokens=a.max_new, do_sample=False,
                                 temperature=None, top_p=None, top_k=None,
                                 pad_token_id=tok.pad_token_id)
            gen = out[:, enc["input_ids"].shape[1]:]
            texts = tok.batch_decode(gen, skip_special_tokens=True)
            for t in texts:
                raws.append(t)
                preds.append(parse_rating(t))
            if (i // a.bs) % 20 == 0:
                done = min(i + a.bs, len(prompts))
                print("  %d/%d  %.1fs" % (done, len(prompts), time.time() - t0), flush=True)

    out_p = os.path.join(ROOT, "results", "%s.jsonl" % tag)
    os.makedirs(os.path.dirname(out_p), exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        for s, p, r in zip(steps, preds, raws):
            f.write(json.dumps(dict(sid=s.sid, source=s.source, gold=s.label,
                                    pred=p, raw=r[:800]), ensure_ascii=False) + "\n")

    gold = [s.label for s in steps]
    res = metrics(gold, preds, tag)
    res["elapsed_s"] = round(time.time() - t0, 1)
    res["cond"] = "no_task" if a.no_task else "task"
    res["prompt_style"] = a.prompt_style
    json.dump(res, open(os.path.join(ROOT, "results", "%s_metrics.json" % tag), "w"),
              ensure_ascii=False, indent=1)

    # 样例输出，便于人工检查格式是否真的遵守
    print("\n前 2 条原始输出：")
    for k in range(min(2, len(raws))):
        print("--- gold=%s pred=%s ---" % (steps[k].label, preds[k]))
        print(raws[k][:500])


if __name__ == "__main__":
    main()
