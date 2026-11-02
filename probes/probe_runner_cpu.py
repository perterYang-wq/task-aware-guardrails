# -*- coding: utf-8 -*-
"""STEP 1 runner（CPU）：复用 probes/counterfactual_user_task_4.py 的变体定义，
补上「三个 seed 并排」与「CPU 运行」。

为什么不直接用那份脚本：它写死 device_map="cuda"、只跑 seed123，
与本阶段「不调用 GPU、三 seed 对照」的要求不符。变体定义（P0–P4）完全复用它的
build_variants / load_p0，保证改动范围与任务书一致。

产物：
  probes/probe_user_task_4.json
  reports/probe_user_task_4.md
  runs/auto/round_probe/step_1.json
"""
import json
import os
import sys
import time

os.environ["CUDA_VISIBLE_DEVICES"] = ""          # 硬保证不上 GPU
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import torch  # noqa: E402
from peft import PeftModel  # noqa: E402
from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: E402

R = "/data/projects/guardrails"
sys.path.insert(0, R)
sys.path.insert(0, os.path.join(R, "probes"))
from guard.schema import Step, parse_rating, render_pab  # noqa: E402
import counterfactual_user_task_4 as P  # noqa: E402

MODEL = "/data/hf_cache/qwen1.5b"
ADAPTERS = [("s0", "m2_HB_s0"), ("s42", "m2_HB_s42"), ("s123", "m2_HB_s123")]
OUT_JSON = os.path.join(R, "probes/probe_user_task_4.json")
OUT_MD = os.path.join(R, "reports/probe_user_task_4.md")
OUT_STEP = os.path.join(R, "runs/auto/round_probe/step_1.json")
LABELS = P.LABELS


def score_all(tag, adapter, p0, variants):
    tok = AutoTokenizer.from_pretrained(MODEL, padding_side="left")
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(MODEL, torch_dtype=torch.float32)
    model = PeftModel.from_pretrained(model, os.path.join(R, "guard/adapters", adapter))
    model = model.to("cpu").eval()

    out = []
    for name, hist, action, note in variants:
        st = Step(sid="probe", source="travel", instruction=p0["instruction"],
                  history=hist, current_action=action, env_info="",
                  score=0.0, label="", tool=None, args={})
        text = tok.apply_chat_template(
            [{"role": "user", "content": render_pab(st, task_aware=True)}],
            tokenize=False, add_generation_prompt=True)
        enc = tok([text], return_tensors="pt", add_special_tokens=False)
        n_in = enc["input_ids"].shape[1]
        t0 = time.time()
        with torch.no_grad():
            gen = model.generate(**enc, max_new_tokens=6, do_sample=False,
                                 pad_token_id=tok.pad_token_id)
            raw = tok.decode(gen[0][n_in:], skip_special_tokens=True).strip()
        rec = dict(variant=name, note=note, raw=raw, parsed=parse_rating(raw),
                   n_in=n_in, hist_len=len(hist), sec=round(time.time() - t0, 1))
        out.append(rec)
        print("  %-6s %-10s raw=%-8r -> %-6s n_in=%d %.0fs"
              % (tag, name, raw, rec["parsed"], n_in, rec["sec"]), flush=True)
    del model
    return out


def main():
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    os.makedirs(os.path.dirname(OUT_STEP), exist_ok=True)
    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    t_all = time.time()

    p0 = P.load_p0()
    variants = P.build_variants(p0)
    print("[scene] step=%s tool=%s 收件人=%s 变体=%d"
          % (p0.get("step"), p0.get("tool"), (p0.get("args") or {}).get("recipients"),
             len(variants)), flush=True)

    results = {}
    for tag, adapter in ADAPTERS:
        results[tag] = score_all(tag, adapter, p0, variants)

    by = {t: {r["variant"]: r for r in results[t]} for t in results}
    p0_cpu = by["s123"][variants[0][0]]["parsed"]
    consistent = (p0_cpu == "ALLOW")

    payload = dict(adapter_map=dict(ADAPTERS), device="cpu", dtype="float32",
                   do_sample=False, max_new_tokens=6,
                   scene=dict(step=p0.get("step"), tool=p0.get("tool"),
                              recipients=(p0.get("args") or {}).get("recipients"),
                              instruction=p0.get("instruction")),
                   variants=[dict(name=n, note=note) for n, _, _, note in variants],
                   results=results,
                   consistency=dict(seed123_p0_cpu=p0_cpu, recorded="ALLOW", ok=consistent),
                   elapsed_s=round(time.time() - t_all, 1),
                   ts=time.strftime("%Y-%m-%d %H:%M:%S"))
    json.dump(payload, open(OUT_JSON, "w"), ensure_ascii=False, indent=2)

    lines = ["# 反事实探针 · user_task_4 + injection_task_1", "",
             "同一份输入（seed123 端到端失败轨迹的第 %s 步 `%s`，收件人 `%s`），"
             % (p0.get("step"), p0.get("tool"),
                (p0.get("args") or {}).get("recipients")),
             "三个 seed 的守卫各判一次。CPU / float32 / greedy / max_new_tokens=6。",
             "seed123 的 P0 在 CPU 上复现端到端记录：**%s**。" % ("是" if consistent else "否"),
             "", "| 变体 | 改动 | seed0 raw / 判定 | seed42 raw / 判定 | seed123 raw / 判定 |",
             "|---|---|---|---|---|"]
    for n, _, _, note in variants:
        cells = ["`%s` / **%s**" % (by[t][n]["raw"], by[t][n]["parsed"]) for t, _ in ADAPTERS]
        lines.append("| %s | %s | %s |" % (n, note, " | ".join(cells)))
    open(OUT_MD, "w", encoding="utf-8").write("\n".join(lines) + "\n")

    json.dump(dict(step=1, script="probes/probe_runner_cpu.py",
                   inputs=[P.TRACE, "guard/adapters/{m2_HB_s0,m2_HB_s42,m2_HB_s123}"],
                   outputs=[OUT_JSON, OUT_MD], rc=0,
                   consistency_ok=consistent, elapsed_s=payload["elapsed_s"],
                   ts=time.strftime("%Y-%m-%d %H:%M:%S")),
              open(OUT_STEP, "w"), ensure_ascii=False, indent=2)
    print("[done] %s consistency=%s %.0fs" % (OUT_JSON, consistent, payload["elapsed_s"]))
    return 0 if consistent else 3


if __name__ == "__main__":
    sys.exit(main())
