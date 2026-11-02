# -*- coding: utf-8 -*-
"""阶段 2：分类器评测补齐（M0/M1 同一协议）。

做三件事，全部只读冻结划分、不调参、不改阈值：
  1. 在**冻结的 PAB-RD test**（335 条 / 25 个任务组）上重算逐类 P/R/F1、support、混淆矩阵；
  2. 同一硬件/同一测量协议下测延迟（冷启动、单样本 P50/P95、吞吐、显存峰值）；
  3. 截断审计：输入 token 分布，以及若按 512 截断会丢掉哪个字段。

M0 = m2_HBnt_s0（训练与推理都不给用户请求）
M1 = m2_HB_s0  （训练与推理都给）
两者骨干、数据、划分、超参、预算完全相同（见 runs/experiment_manifest.json 与 train_*.json）。
"""
import argparse
import json
import os
import statistics as st
import sys
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

ROOT = "/data/projects/guardrails"
sys.path.insert(0, ROOT)
from guard.schema import render_pab, parse_rating  # noqa: E402

OUT = os.path.join(ROOT, "results/classifier")
LABELS = ("ALLOW", "REVIEW", "DENY")
ARMS = {"M0": dict(tag="m2_HBnt_s0", task_aware=False),
        "M1": dict(tag="m2_HB_s0", task_aware=True)}


def ids_of(tok, s):
    return tok(s, add_special_tokens=False)["input_ids"]


def load_split():
    sp = json.load(open(os.path.join(ROOT, "data/pab_rd_splits.json")))
    rows = {r["sid"]: r for r in (json.loads(l) for l in
                                  open(os.path.join(ROOT, "data/pab_rd.jsonl"), encoding="utf-8"))}
    from guard.schema import Step
    steps = []
    for sid in sp["test"]:
        r = rows[sid]
        steps.append(Step(sid=r["sid"], source=r.get("source") or "pab_rd",
                          instruction=r.get("instruction") or "",
                          history=r.get("history") or "",
                          current_action=r.get("current_action") or "",
                          env_info=r.get("env_info") or "", score=0.0,
                          label=r["label"], tool=r.get("tool"),
                          args=r.get("args") or {}, meta=r.get("meta") or {}))
    return steps


def prf(gold, pred):
    out, conf = {}, {}
    for g in LABELS:
        tp = sum(1 for a, b in zip(gold, pred) if a == g and b == g)
        fp = sum(1 for a, b in zip(gold, pred) if a != g and b == g)
        fn = sum(1 for a, b in zip(gold, pred) if a == g and b != g)
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f = 2 * p * r / (p + r) if p + r else 0.0
        out[g] = dict(P=round(p, 4), R=round(r, 4), F1=round(f, 4),
                      support=sum(1 for a in gold if a == g))
    for g in LABELS:
        for q in LABELS:
            conf["%s|%s" % (g, q)] = sum(1 for a, b in zip(gold, pred) if a == g and b == q)
    return out, conf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="M0,M1")
    ap.add_argument("--bs", type=int, default=16)
    ap.add_argument("--max-new", type=int, default=6)
    ap.add_argument("--warmup", type=int, default=20)
    ap.add_argument("--lat-n", type=int, default=150)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    tok = AutoTokenizer.from_pretrained("/data/hf_cache/qwen1.5b", padding_side="left")
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    steps = load_split()
    print("test 划分：%d 条 / %d 个任务组"
          % (len(steps), len({(s.meta or {}).get("task_id") for s in steps})))

    report = dict(test_split=dict(n=len(steps),
                                  task_groups=len({(s.meta or {}).get("task_id") for s in steps}),
                                  source="data/pab_rd_splits.json::test（冻结）"),
                  arms={})

    for name in a.arms.split(","):
        spec = ARMS[name]
        t0 = time.time()
        tok_ = tok
        model = AutoModelForCausalLM.from_pretrained("/data/hf_cache/qwen1.5b",
                                                     torch_dtype=torch.float16,
                                                     device_map="cuda").eval()
        model = PeftModel.from_pretrained(model, os.path.join(ROOT, "guard/adapters",
                                                              spec["tag"])).eval()
        cold = time.time() - t0

        texts, ntok, trunc = [], [], []
        for s in steps:
            txt = render_pab(s, task_aware=spec["task_aware"])
            ids = tok_.apply_chat_template([{"role": "user", "content": txt}],
                                           tokenize=True, add_generation_prompt=True,
                                           return_dict=False)
            ntok.append(len(ids))
            # 512 截断后关键字段是否还在
            head = tok_.decode(ids[:512], skip_special_tokens=True)
            trunc.append(dict(task="Task:" in head, action="Action:" in head,
                              args="Action Input" in head, rating="Rating" in head))
            texts.append(txt)

        preds, raws = [], []
        t0 = time.time()
        with torch.no_grad():
            for i in range(0, len(texts), a.bs):
                enc = tok_([tok_.apply_chat_template(
                    [{"role": "user", "content": t}], tokenize=False,
                    add_generation_prompt=True) for t in texts[i:i + a.bs]],
                    return_tensors="pt", padding=True, add_special_tokens=False).to("cuda")
                n_in = enc["input_ids"].shape[1]
                g = model.generate(**enc, max_new_tokens=a.max_new, do_sample=False,
                                   temperature=None, top_p=None, top_k=None,
                                   pad_token_id=tok_.pad_token_id)
                for t in tok_.batch_decode(g[:, n_in:], skip_special_tokens=True):
                    preds.append(parse_rating(t))
                    raws.append(t.strip()[:20])
        inf_s = time.time() - t0

        gold = [s.label for s in steps]
        pf, conf = prf(gold, preds)
        macro = round(sum(v["F1"] for v in pf.values()) / 3, 4)
        acc = round(sum(1 for x, y in zip(gold, preds) if x == y) / len(gold), 4)

        # ---------- 延迟 ----------
        torch.cuda.reset_peak_memory_stats()
        with torch.no_grad():
            for _ in range(a.warmup):
                enc = tok_([texts[0]], return_tensors="pt").to("cuda")
                model.generate(**enc, max_new_tokens=a.max_new, do_sample=False,
                               pad_token_id=tok_.pad_token_id)
            lat = []
            for j in range(a.lat_n):
                enc = tok_([texts[j % len(texts)]], return_tensors="pt").to("cuda")
                t1 = time.time()
                model.generate(**enc, max_new_tokens=a.max_new, do_sample=False,
                               pad_token_id=tok_.pad_token_id)
                lat.append((time.time() - t1) * 1000)
            # 吞吐 bs=8
            t2 = time.time()
            n_bs = 8
            for i in range(0, min(len(texts), 80), n_bs):
                enc = tok_(texts[i:i + n_bs], return_tensors="pt", padding=True,
                           add_special_tokens=False).to("cuda")
                model.generate(**enc, max_new_tokens=a.max_new, do_sample=False,
                               pad_token_id=tok_.pad_token_id)
            thr = min(len(texts), 80) / (time.time() - t2)
        lat.sort()
        peak = torch.cuda.max_memory_allocated() / 2**20

        # ---------- REVIEW 的误判方向 ----------
        rev = [(g, p) for g, p in zip(gold, preds) if g == "REVIEW"]
        rev_stats = dict(n=len(rev),
                         to_ALLOW=sum(1 for g, p in rev if p == "ALLOW"),
                         to_DENY=sum(1 for g, p in rev if p == "DENY"),
                         to_REVIEW=sum(1 for g, p in rev if p == "REVIEW"))

        rec = dict(tag=spec["tag"], task_aware=spec["task_aware"],
                   cold_start_s=round(cold, 2), infer_s=round(inf_s, 1),
                   acc=acc, macro_f1=macro, per_class=pf, confusion=conf,
                   parse_fail=sum(1 for p in preds if p not in LABELS),
                   review_handling=rev_stats,
                   latency_ms=dict(mean=round(st.mean(lat), 1), p50=round(lat[len(lat)//2], 1),
                                   p95=round(lat[int(0.95 * len(lat))], 1), n=len(lat)),
                   throughput_bs8=round(thr, 2), gpu_peak_mib=round(peak, 0),
                   tokens=dict(mean=round(st.mean(ntok), 0), p50=sorted(ntok)[len(ntok)//2],
                               p95=sorted(ntok)[int(0.95 * len(ntok))], max=max(ntok),
                               over_1024=sum(1 for x in ntok if x > 1024),
                               over_512=sum(1 for x in ntok if x > 512)),
                   trunc512=dict(loses_action=sum(1 for t in trunc if not t["action"]),
                                 loses_args=sum(1 for t in trunc if not t["args"]),
                                 loses_task=sum(1 for t in trunc if not t["task"])))
        report["arms"][name] = rec
        with open(os.path.join(OUT, "%s_test.jsonl" % spec["tag"]), "w", encoding="utf-8") as f:
            for s, p, r in zip(steps, preds, raws):
                f.write(json.dumps(dict(sid=s.sid, gold=s.label, pred=p, raw=r),
                                   ensure_ascii=False) + "\n")

        print("\n== %s (%s) ==" % (name, spec["tag"]))
        print("  acc %.4f  macro-F1 %.4f  parse_fail %d" % (acc, macro, rec["parse_fail"]))
        for g in LABELS:
            v = pf[g]
            print("    %-6s P %.3f  R %.3f  F1 %.3f  n=%d" % (g, v["P"], v["R"], v["F1"], v["support"]))
        print("  REVIEW: %d 条 → ALLOW %d / DENY %d / REVIEW %d"
              % (rev_stats["n"], rev_stats["to_ALLOW"], rev_stats["to_DENY"], rev_stats["to_REVIEW"]))
        print("  latency mean %.0fms p50 %.0f p95 %.0f | bs8 %.1f/s | peak %.0fMiB | cold %.1fs"
              % (st.mean(lat), lat[len(lat)//2], lat[int(0.95*len(lat))], thr, peak, cold))
        print("  tokens mean %.0f p95 %d max %d | >1024 %d | >512 %d | 512 截断丢 action %d"
              % (st.mean(ntok), sorted(ntok)[int(0.95*len(ntok))], max(ntok),
                 rec["tokens"]["over_1024"], rec["tokens"]["over_512"], rec["trunc512"]["loses_action"]))
        del model
        torch.cuda.empty_cache()

    json.dump(report, open(os.path.join(OUT, "phase2_clf.json"), "w"),
              ensure_ascii=False, indent=2)
    print("\n-> %s/phase2_clf.json" % OUT)


if __name__ == "__main__":
    main()
