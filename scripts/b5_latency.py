# -*- coding: utf-8 -*-
"""B5：0.5B 守卫的 CPU 单次延迟（batch=1，100 次，warmup 5 次）。"""
import json, os, sys, time
os.environ["CUDA_VISIBLE_DEVICES"] = ""
import torch
sys.path.insert(0, "/data/projects/guardrails")
from guard.schema import Step, render_pab
from guard_inline import InlineGuard
R = "/data/projects/guardrails"
rows = [json.loads(l) for l in open(os.path.join(R, "results/diag/steps.jsonl"), encoding="utf-8")]
rows = rows[::max(1, len(rows) // 100)][:100]
g = InlineGuard(model_path="/data/hf_cache/qwen0.5b",
                adapter=os.path.join(R, "guard/adapters/m2_HB05_s0"), max_new=6, device="cpu")
lat = []
for i, r in enumerate(rows):
    action = ("(1) Thought: (omitted)\n(2) Action: %s\n(3) Action Input: %s"
              % (r["tool"], json.dumps(r.get("args") or {}, ensure_ascii=False)))
    t0 = time.time()
    g.decide(r["instruction"], r["hist_full"], action)
    if i >= 5:                       # 前 5 次算 warmup
        lat.append((time.time() - t0) * 1000)
lat.sort()
out = dict(n=len(lat), mean=round(sum(lat) / len(lat), 1),
           p50=round(lat[len(lat) // 2], 1), p95=round(lat[int(0.95 * len(lat))], 1),
           max=round(lat[-1], 1), device="cpu", batch=1)
json.dump(out, open(os.path.join(R, "results/classifier/latency_05b_cpu.json"), "w"),
          ensure_ascii=False, indent=2)
print(json.dumps(out, ensure_ascii=False))
