# -*- coding: utf-8 -*-
"""诊断数据集逐调用打分：同一 checkpoint × 五档 history 视图。

对每个 (arm, view) 产出一份 results/diag/preds/{arm}__{view}.jsonl，
每条 {sid, pred, score, raw, ntok}。渲染、解码、解析与线上 inline guard
**完全同一套**（render_pab → apply_chat_template → greedy 6 token → parse_rating），
所以离线数字与在线行为可比。

用法
----
    python scripts/diag_score.py --arms all --views none,last1,last3,full,noinj
    python scripts/diag_score.py --arms p1_15b_task_s0 --views full --limit 40   # 冒烟
"""
import argparse
import json
import os
import sys
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

R = "/data/projects/guardrails"
sys.path.insert(0, R)
from guard.schema import Step, parse_rating, render_pab  # noqa: E402

DIAG = os.environ.get("GUARD_DIAG_DIR") or os.path.join(R, "results/diag")
PRED = os.path.join(DIAG, "preds")
STEPS = os.path.join(DIAG, "steps.jsonl")

BASE = {"15b": "/data/hf_cache/qwen1.5b", "3b": "/data/hf_cache/qwen3b",
        "05b": "/data/hf_cache/qwen0.5b"}


def _arm(size, adapter):
    return (BASE[size], os.path.join(R, "guard/adapters", adapter) if adapter else None)


ARMS = {
    # --- 部署尺寸（1.5B）：3 seed task-aware，先跑
    "p1_15b_task_s0": _arm("15b", "p1_15b_task_l2_s0"),
    "p1_15b_task_s42": _arm("15b", "p1_15b_task_l2_s42"),
    "p1_15b_task_s123": _arm("15b", "p1_15b_task_l2_s123"),
    # 对照：不含用户请求训练（只有动作/历史，无法判授权）
    "p1_15b_nt_s0": _arm("15b", "p1_15b_nt_l2_s0"),
    # zero-shot 参照：直接把基座当 guard 用
    "zs_15b": _arm("15b", None),
    "zs_05b": _arm("05b", None),
    "m2_HB05_s0": _arm("05b", "m2_HB05_s0"),
    # --- 3B：看规模方向（视图少一档，控制 GPU 预算）
    "p1_3b_task_s0": _arm("3b", "p1_3b_task_l2_s0"),
    "p1_3b_task_s42": _arm("3b", "p1_3b_task_l2_s42"),
    "p1_3b_task_s123": _arm("3b", "p1_3b_task_l2_s123"),
    # --- M1/M2 阶梯（本轮训练产出，训练完成后再评）
    "m2_S_s0": _arm("15b", "m2_S_s0"),
    "m2_H_s0": _arm("15b", "m2_H_s0"),
    "m2_HV_s0": _arm("15b", "m2_HV_s0"),
    "m2_HP_s0": _arm("15b", "m2_HP_s0"),
    "m2_SM_s0": _arm("15b", "m2_SM_s0"),
    "m2_S_s42": _arm("15b", "m2_S_s42"),
    "m2_S_s123": _arm("15b", "m2_S_s123"),
    "m2_H_s42": _arm("15b", "m2_H_s42"),
    "m2_H_s123": _arm("15b", "m2_H_s123"),
    "m2_HB_s0": _arm("15b", "m2_HB_s0"),
    "m2_HBmeta_s0": _arm("15b", "m2_HBmeta_s0"),
    "m2_HBnt_s0": _arm("15b", "m2_HBnt_s0"),
    "m2_HB_s42": _arm("15b", "m2_HB_s42"),
    "m2_HB_s123": _arm("15b", "m2_HB_s123"),
}

VIEWS = ("none", "last1", "last3", "full", "noinj")


def load_rows(limit=0, suites=""):
    rows = [json.loads(l) for l in open(STEPS, encoding="utf-8")]
    if suites:
        want = set(suites.split(","))
        rows = [r for r in rows if r["suite"] in want]
    if limit:
        rows = rows[:limit]
    return rows


def to_step(r, view):
    return Step(sid=r["sid"], source=r["suite"], instruction=r["instruction"],
                history=r.get("hist_" + view) or "", current_action=r["current_action"],
                env_info="", score=0.0, label="", tool=r["tool"], args=r["args"] or {})


def run(rows, model_path, adapter, views, bs, max_new, out_paths=None,
        task_aware=True, quiet=False):
    """一次加载模型，跑完该 arm 的所有视图；每个视图算完立即落盘（便于中断续跑）。"""
    tok = AutoTokenizer.from_pretrained(model_path, padding_side="left")
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        model_path, torch_dtype=torch.float16, device_map="cuda").eval()
    if adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, adapter).eval()

    out = {}
    for view in views:
        texts = [tok.apply_chat_template(
            [{"role": "user", "content": render_pab(to_step(r, view), task_aware=task_aware)}],
            tokenize=False, add_generation_prompt=True) for r in rows]
        res = []
        t0 = time.time()
        with torch.no_grad():
            for i in range(0, len(texts), bs):
                enc = tok(texts[i:i + bs], return_tensors="pt", padding=True,
                          add_special_tokens=False).to("cuda")
                n_in = enc["input_ids"].shape[1]
                g = model.generate(**enc, max_new_tokens=max_new, do_sample=False,
                                   temperature=None, top_p=None, top_k=None,
                                   pad_token_id=tok.pad_token_id)
                for j, t in enumerate(tok.batch_decode(g[:, n_in:], skip_special_tokens=True)):
                    res.append(dict(sid=rows[i + j]["sid"], pred=parse_rating(t),
                                    raw=t.strip()[:40], ntok=int(n_in)))
                if not quiet and (i // bs) % 40 == 0:
                    print("    %-6s %5d/%d  %.1fs" % (view, min(i + bs, len(texts)),
                                                      len(texts), time.time() - t0), flush=True)
        out[view] = res
        c = {}
        for x in res:
            c[x["pred"]] = c.get(x["pred"], 0) + 1
        print("        %-22s %-6s %s max_tok=%d %.0fs"
              % (os.path.basename(adapter or "zs"), view, c,
                 max(x["ntok"] for x in res), time.time() - t0), flush=True)
        if out_paths and view in out_paths:
            tmp = out_paths[view] + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                for x in res:
                    f.write(json.dumps(x, ensure_ascii=False) + "\n")
            os.replace(tmp, out_paths[view])       # 原子替换：不会留半截文件
    del model
    torch.cuda.empty_cache()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="all")
    ap.add_argument("--views", default="none,last3,full,noinj")
    ap.add_argument("--drop-3b", default="last3", help="3B 臂跳过的视图（省 GPU 预算）")
    ap.add_argument("--bs", type=int, default=32)
    ap.add_argument("--bs-3b", type=int, default=12)
    ap.add_argument("--max-new", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--suites", default="")
    ap.add_argument("--no-task", action="store_true", help="抹掉用户请求（对照臂）")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    os.makedirs(PRED, exist_ok=True)

    arms = list(ARMS) if a.arms == "all" else [x.strip() for x in a.arms.split(",")]
    views = [x.strip() for x in a.views.split(",")]
    rows = load_rows(a.limit, a.suites)
    print("steps=%d arms=%d views=%d no_task=%s" % (len(rows), len(arms), len(views), a.no_task),
          flush=True)

    for arm in arms:
        model_path, adapter = ARMS[arm]
        tag = arm + ("_notask" if a.no_task else "")
        arm_views = [v for v in views
                     if not ("3b" in arm and v in a.drop_3b.split(","))]
        todo = []
        for view in arm_views:
            out = os.path.join(PRED, "%s__%s.jsonl" % (tag, view))
            if os.path.exists(out) and not a.force:
                n = sum(1 for _ in open(out))
                if n == len(rows):
                    continue
            todo.append(view)
        if not todo:
            print("[skip] %s 全部已完成" % tag, flush=True)
            continue
        bs = a.bs_3b if "3b" in arm else a.bs
        print("[run ] %-22s views=%s bs=%d" % (tag, todo, bs), flush=True)
        paths = {v: os.path.join(PRED, "%s__%s.jsonl" % (tag, v)) for v in todo}
        run(rows, model_path, adapter, todo, bs, a.max_new, out_paths=paths,
            task_aware=not a.no_task)


if __name__ == "__main__":
    main()
