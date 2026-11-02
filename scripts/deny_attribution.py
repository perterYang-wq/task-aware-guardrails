# -*- coding: utf-8 -*-
"""STEP B：M1 的 DENY 归因 —— 载荷识别 vs 授权推理。

对每条 DENY 调用，取它当时的 history，构造 P1（删掉 <INFORMATION> 整块）后重打分：
  P1 仍 DENY  -> authorization-reasoning
  P1 翻 ALLOW/REVIEW -> payload-recognition
同时在原 history 上重打分（P0），核对与端到端记录一致（CPU float32 vs GPU fp16 的差异要报）。

全程 CPU，不占 GPU。
"""
import json, os, re, sys, time
from collections import Counter

os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
import torch  # noqa: E402
from peft import PeftModel  # noqa: E402
from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: E402

R = "/data/projects/guardrails"
sys.path.insert(0, R)
from guard.schema import Step, parse_rating, render_pab  # noqa: E402

MODEL = "/data/hf_cache/qwen1.5b"
ADAPTER = os.path.join(R, "guard/adapters/m2_HB_s0")
INJ = re.compile(r"<INFORMATION>.*?</INFORMATION>", re.S)
RUNS = [("travel", "results/e2e/travel/m2_HB_s0_calls_inj0-1"),
        ("slack", "results/e2e/slack/m2_HB_s0_inj1-3")]


def load_run(p):
    scen = [json.loads(l) for l in open(os.path.join(R, p, "scen.jsonl"), encoding="utf-8")]
    trace = [json.loads(l) for l in open(os.path.join(R, p, "trace.jsonl"), encoding="utf-8")]
    idx = {}
    for t in trace:
        idx[(t.get("user_task"), t.get("injection_task"), t.get("step"))] = t
    return scen, idx


def score(tok, model, instruction, history, action):
    st = Step(sid="d", source="x", instruction=instruction or "", history=history or "",
              current_action=action or "", env_info="", score=0.0, label="",
              tool=None, args={})
    text = tok.apply_chat_template(
        [{"role": "user", "content": render_pab(st, task_aware=True)}],
        tokenize=False, add_generation_prompt=True)
    enc = tok([text], return_tensors="pt", add_special_tokens=False)
    n = enc["input_ids"].shape[1]
    with torch.no_grad():
        g = model.generate(**enc, max_new_tokens=6, do_sample=False,
                           pad_token_id=tok.pad_token_id)
    raw = tok.decode(g[0][n:], skip_special_tokens=True).strip()
    return parse_rating(raw), raw, n


def main():
    tok = AutoTokenizer.from_pretrained(MODEL, padding_side="left")
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(MODEL, torch_dtype=torch.float32)
    model = PeftModel.from_pretrained(model, ADAPTER).to("cpu").eval()

    rows, miss, mismatch = [], 0, 0
    t0 = time.time()
    for suite, p in RUNS:
        scen, idx = load_run(p)
        for r in scen:
            for h in (r.get("guard_hits") or []):
                if h["decision"] != "DENY":
                    continue
                step = (h.get("idx") or 0) + 1
                t = idx.get((r["user_task"], r.get("injection_task"), step))
                if t is None:
                    miss += 1
                    continue
                hist = t.get("history_full") or ""
                act = t.get("current_action") or ""
                p1 = INJ.sub("", hist)
                lab0, raw0, n0 = score(tok, model, t.get("instruction"), hist, act)
                if lab0 != "DENY":
                    mismatch += 1
                lab1, raw1, _ = score(tok, model, t.get("instruction"), p1, act)
                rows.append(dict(suite=suite, user_task=r["user_task"],
                                 injection=r.get("injection_task"), step=step,
                                 tool=h.get("tool"), scene="attack" if r.get("injection_task") else "clean",
                                 p0=lab0, p1=lab1, n_in=n0))
                print("  %-6s %-14s step=%d %-26s p0=%-6s p1=%-6s"
                      % (suite, r["user_task"], step, h.get("tool"), lab0, lab1), flush=True)

    # 统计
    def tab(suite=None):
        sub = [x for x in rows if (suite is None or x["suite"] == suite) and x["scene"] == "attack"]
        pay = [x for x in sub if x["p1"] != "DENY"]
        aut = [x for x in sub if x["p1"] == "DENY"]
        return len(sub), len(pay), len(aut)

    lines = ["# DENY 归因：载荷识别 vs 授权推理", "",
             "对 M1 在 travel / slack 上的每一条 DENY 调用，取它当时的 history，",
             "删掉 `<INFORMATION>` 整块后重打分（P1）。仍 DENY = 授权推理；翻 ALLOW/REVIEW = 载荷识别。",
             "CPU/float32/greedy；P0 为重打原 history 的一致性校验。", "",
             "| 套件 | 总 DENY（受攻击场景） | payload-recognition | authorization-reasoning | payload 占比 |",
             "|---|---|---|---|---|"]
    tot = [0, 0, 0]
    for suite in ("travel", "slack"):
        n, pay, aut = tab(suite)
        tot = [tot[0] + n, tot[1] + pay, tot[2] + aut]
        lines.append("| %s | %d | %d | %d | %.1f%% |"
                     % (suite, n, pay, aut, 100.0 * pay / max(1, n)))
    lines.append("| **合计** | **%d** | **%d** | **%d** | **%.1f%%** |"
                 % (tot[0], tot[1], tot[2], 100.0 * tot[1] / max(1, tot[0])))
    clean_den = [x for x in rows if x["scene"] == "clean"]
    lines += ["", "干净场景的 DENY（误拦）：%d 条，P1 后仍 DENY %d 条 —— 这类没有载荷可去，"
              "不计入上表。" % (len(clean_den), sum(1 for x in clean_den if x["p1"] == "DENY")),
              "", "一致性校验：P0 重打分与端到端记录不一致 %d 条 / 对齐失败 %d 条（共 %d 条 DENY）。"
              % (mismatch, miss, len(rows)), ""]
    open(os.path.join(R, "reports/deny_attribution.md"), "w", encoding="utf-8").write(
        "\n".join(lines) + "\n")
    json.dump(dict(rows=rows, total=tot, clean=len(clean_den),
                   mismatch=mismatch, miss=miss,
                   elapsed_s=round(time.time() - t0, 1)),
              open(os.path.join(R, "probes/deny_attribution.json"), "w"),
              ensure_ascii=False, indent=2)
    print("\n合计 %d 条：payload %d / auth %d (%.1f%%) | mismatch %d miss %d | %.0fs"
          % (tot[0], tot[1], tot[2], 100.0 * tot[1] / max(1, tot[0]), mismatch, miss,
             time.time() - t0))


if __name__ == "__main__":
    main()
