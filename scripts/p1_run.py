# -*- coding: utf-8 -*-
"""P1 多随机种子复现（Guard 只用 1.5B / 3B；7B 是 Agent，不参与）。

统一训练协议（预先固定，不看测试集）
------------------------------------
    epochs   = 4            （旧 3B 用 3、旧 1.5B 用 4 -> 不一致，故 seed=0 也要重跑）
    bs,accum = 4, 4         （有效 batch 16，两个模型相同）
    max_len  = 1024         （PAB-RD 最长 989 token，不截断；旧 1.5B 用 1280 -> 不一致）
    lora     = r16 / alpha32 / dropout0.05
    lr 搜索  = {1e-4, 2e-4}
    seeds    = {0, 42, 123}

搜索预算（两个模型完全相同）
--------------------------
    Stage A：每个模型 × 2 臂 × 2 个 lr × seed 0  = 4 个 run/模型
    lr 选择：per model，取 **两臂 val macro-F1 的均值** 最大者
             （按臂选 lr 会破坏 full/nt 的可比性，故不这么做）
    Stage B：所选 lr 下，两臂 × seeds {42,123}  = 4 个 run/模型
    合计 16 个 run，其中 12 个进入最终评估（所选 lr × 3 seeds × 2 臂 × 2 模型）

checkpoint 选择只发生在验证集（train_lora.py 内部逐轮评估 val macro-F1 并保存最优轮）。
测试集只在最后 eval 一次，不参与任何选择。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = "/data/projects/guardrails"
PY = "/data/conda/envs/guard/bin/python"
DATA = "data/pab_rd.jsonl"
SPLITS = "data/pab_rd_splits.json"
OUT = os.path.join(ROOT, "results", "p1")
LOGD = os.path.join(OUT, "logs")

MODELS = [("15b", "/data/hf_cache/qwen1.5b", 16),
          ("3b", "/data/hf_cache/qwen3b", 12)]
LRS = [("l1", 1e-4), ("l2", 2e-4)]
SEEDS = [0, 42, 123]
ARMS = [("task", False), ("nt", True)]
HP = ["--epochs", "4", "--bs", "4", "--accum", "4", "--max-len", "1024", "--lora-r", "16"]
ENV = dict(os.environ, HF_HUB_OFFLINE="1",
           PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True")


def sh(cmd, log):
    t0 = time.time()
    with open(log, "a", encoding="utf-8") as f:
        f.write("\n$ " + " ".join(cmd) + "\n")
        f.flush()
        r = subprocess.run(cmd, cwd=ROOT, env=ENV, stdout=f,
                           stderr=subprocess.STDOUT)
    return r.returncode, time.time() - t0


def tag_of(model, arm, lrkey, seed):
    return "p1_%s_%s_%s_s%d" % (model, arm, lrkey, seed)


def train(model, mpath, arm, no_task, lrkey, lr, seed, force=False):
    tag = tag_of(model, arm, lrkey, seed)
    tj = os.path.join(ROOT, "results", "train_%s.json" % tag)
    ad = os.path.join(ROOT, "guard", "adapters", tag)
    if not force and os.path.exists(tj) and os.path.isdir(ad):
        d = json.load(open(tj, encoding="utf-8"))
        print("  [skip] %-22s best=%d val=%.4f" % (tag, d["best_epoch"], d["best_val_macro_f1"]),
              flush=True)
        return d
    cmd = [PY, "scripts/train_lora.py", "--data", DATA, "--splits", SPLITS,
           "--split", "pab", "--style", "pab", "--model", mpath,
           "--lr", str(lr), "--seed", str(seed), "--tag", tag] + HP
    if no_task:
        cmd.append("--no-task")
    log = os.path.join(LOGD, "%s.log" % tag)
    print("  [train] %-22s lr=%g seed=%d" % (tag, lr, seed), flush=True)
    rc, dt = sh(cmd, log)
    if rc != 0 or not os.path.exists(tj):
        print("  [FAIL ] %s rc=%d  %.0fs  log=%s" % (tag, rc, dt, log), flush=True)
        return None
    d = json.load(open(tj, encoding="utf-8"))
    d["_seconds"] = round(dt, 1)
    print("  [done ] %-22s best=%d val=%.4f  %.0fs"
          % (tag, d["best_epoch"], d["best_val_macro_f1"], dt), flush=True)
    return d


def evaluate(model, mpath, bs, arm, no_task, lrkey, seed):
    tag = tag_of(model, arm, lrkey, seed)
    pdir = os.path.join(OUT, "preds")
    os.makedirs(pdir, exist_ok=True)
    dst = os.path.join(pdir, "%s_%s.jsonl" % (tag, arm))
    if os.path.exists(dst):
        print("  [skip-eval] %s" % os.path.basename(dst), flush=True)
        return dst
    cmd = [PY, "scripts/run_guard.py", "--data", DATA, "--splits", SPLITS,
           "--split", "", "--part", "test", "--style", "pab",
           "--model", mpath, "--bs", str(bs),
           "--adapter", "guard/adapters/%s" % tag, "--tag", tag]
    if no_task:
        cmd.append("--no-task")
    log = os.path.join(LOGD, "%s_eval.log" % tag)
    rc, dt = sh(cmd, log)
    # run_guard.py 落盘名带 "_<part>" 后缀（内部 tag = tag + "_" + part），
    # 这里必须一致；旧命名作为兜底保留。
    src = os.path.join(ROOT, "results", "%s_test.jsonl" % tag)
    if not os.path.exists(src):
        src = os.path.join(ROOT, "results", "%s.jsonl" % tag)
    if rc != 0 or not os.path.exists(src):
        print("  [FAIL-eval] %s rc=%d" % (tag, rc), flush=True)
        return None
    shutil.copyfile(src, dst)
    print("  [eval ] %-28s %.0fs" % (os.path.basename(dst), dt), flush=True)
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all", choices=["a", "b", "eval", "all"])
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    os.makedirs(LOGD, exist_ok=True)

    rec = {"protocol": {"epochs": 4, "bs": 4, "accum": 4, "max_len": 1024,
                        "lora_r": 16, "lora_alpha": 32, "lora_dropout": 0.05,
                        "lrs": [1e-4, 2e-4], "seeds": SEEDS,
                        "effective_batch": 16,
                        "lr_selection": "per model, argmax of mean(val macro-F1) over the two arms"},
           "stage_a": {}, "lr_choice": {}, "stage_b": {}, "evals": {}}

    # ---------------- Stage A：lr 搜索（seed 0）
    if a.stage in ("a", "all"):
        print("=" * 78, "\nStage A: lr search on seed 0 (2 lr x 2 arms x 2 models)", flush=True)
        for model, mpath, _ in MODELS:
            for lrkey, lr in LRS:
                for arm, no_task in ARMS:
                    d = train(model, mpath, arm, no_task, lrkey, lr, 0, a.force)
                    rec["stage_a"][tag_of(model, arm, lrkey, 0)] = d and {
                        "best_epoch": d["best_epoch"], "val_macro_f1": d["best_val_macro_f1"],
                        "seconds": d.get("_seconds")}

        # lr 选择：per model，两臂 val 均值
        for model, _, _ in MODELS:
            scores = {}
            for lrkey, _ in LRS:
                vals = [rec["stage_a"].get(tag_of(model, arm, lrkey, 0), {}) or {}
                        for arm, _ in ARMS]
                f1 = [v.get("val_macro_f1") for v in vals]
                if all(x is not None for x in f1):
                    scores[lrkey] = sum(f1) / len(f1)
            if scores:
                best = max(scores, key=scores.get)
                rec["lr_choice"][model] = {"lrkey": best,
                                           "lr": dict(LRS)[best],
                                           "mean_val_by_lr": scores,
                                           "rule": "argmax of mean(val macro-F1) over arms"}
                print("\n[LR] %-4s -> %s (lr=%g)  means=%s"
                      % (model, best, dict(LRS)[best],
                         {k: round(v, 4) for k, v in scores.items()}), flush=True)
        json.dump(rec, open(os.path.join(OUT, "p1_record.json"), "w"),
                  ensure_ascii=False, indent=1)

    # ---------------- Stage B：其余种子
    if a.stage in ("b", "all"):
        rp = os.path.join(OUT, "p1_record.json")
        if os.path.exists(rp):
            rec = json.load(open(rp, encoding="utf-8"))
        print("\n" + "=" * 78 + "\nStage B: seeds 42/123 at the selected lr", flush=True)
        for model, mpath, _ in MODELS:
            ch = rec["lr_choice"].get(model)
            if not ch:
                print("  [skip] %s 没有 lr 选择" % model, flush=True)
                continue
            for arm, no_task in ARMS:
                for seed in SEEDS[1:]:
                    d = train(model, mpath, arm, no_task, ch["lrkey"], ch["lr"], seed, a.force)
                    rec["stage_b"][tag_of(model, arm, ch["lrkey"], seed)] = d and {
                        "best_epoch": d["best_epoch"], "val_macro_f1": d["best_val_macro_f1"],
                        "seconds": d.get("_seconds")}
        json.dump(rec, open(rp, "w"), ensure_ascii=False, indent=1)

    # ---------------- 评估（只用所选 lr）
    if a.stage in ("eval", "all"):
        rp = os.path.join(OUT, "p1_record.json")
        rec = json.load(open(rp, encoding="utf-8"))
        print("\n" + "=" * 78 + "\neval: 3 seeds x 2 arms x 2 models = 12", flush=True)
        for model, mpath, bs in MODELS:
            ch = rec["lr_choice"][model]
            for arm, no_task in ARMS:
                for seed in SEEDS:
                    p = evaluate(model, mpath, bs, arm, no_task, ch["lrkey"], seed)
                    rec["evals"][tag_of(model, arm, ch["lrkey"], seed)] = p
        json.dump(rec, open(rp, "w"), ensure_ascii=False, indent=1)
        print("\nP1_DONE", flush=True)


if __name__ == "__main__":
    main()
