# -*- coding: utf-8 -*-
"""P1 的载荷去除是否彻底：字块 vs 语义。

背景：deny_attribution 的 P1 只是用正则删掉 <INFORMATION>...</INFORMATION> 整块。
但 agent 可能在**自己的 assistant 消息里复述**注入要求（实测样例：
"as requested by Emma Johnson"）。若复述普遍存在，P1 后仍 DENY 就不能叫
"不依赖载荷"，只能叫"不依赖载荷原文"。

本脚本对 M1 的 34 条 DENY 逐条量化三件事（纯文本，无模型）：
  1. 原文残留：载荷里 60 字符片段是否仍出现在 P1 history
  2. 实体残留：载荷里的邮箱 / URL 是否仍出现在 P1 history
  3. 实体复述：载荷里的专名 token 在 P1 history 的召回率（>0.5 记为"被复述"）

产物：probes/p1_residual.json
"""
import json
import re

R = "/data/projects/guardrails"
INJ = re.compile(r"<INFORMATION>.*?</INFORMATION>", re.S)
EMAIL = re.compile(r"[\w.\-+]+@[\w.\-]+\.\w+")
URL = re.compile(r"(?:https?://|www\.)[^\s\"'<>)]+")
TOK = re.compile(r"\b[A-Z][a-zA-Z]{3,}\b")
STOP = {"The", "This", "That", "Your", "Please", "Note", "Send", "From", "Subject",
        "Hotel", "Message", "Information", "Important", "Action", "Task", "User"}
RUNS = [("travel", "results/e2e/travel/m2_HB_s0_calls_inj0-1"),
        ("slack", "results/e2e/slack/m2_HB_s0_inj1-3")]


def main():
    d = json.load(open(R + "/probes/deny_attribution.json", encoding="utf-8"))
    rows = [r for r in d["rows"] if r["scene"] == "attack"]
    tr = {}
    for s, p in RUNS:
        for line in open(R + "/" + p + "/trace.jsonl", encoding="utf-8"):
            t = json.loads(line)
            tr[(s, t["user_task"], t.get("injection_task"), t["step"])] = t

    out = []
    for r in rows:
        t = tr.get((r["suite"], r["user_task"], r.get("injection"), r["step"]))
        if not t:
            continue
        h = t.get("history_full") or ""
        m = INJ.search(h)
        if not m:
            continue
        span, p1 = m.group(0), INJ.sub("", h)
        frags = [span[i:i + 60] for i in range(0, max(1, len(span) - 60), 60)]
        raw_res = any(f.strip() and f in p1 for f in frags)
        ents = set(EMAIL.findall(span)) | set(URL.findall(span))
        ent_res = sorted(e for e in ents if e in p1)
        toks = {x for x in TOK.findall(span) if x not in STOP}
        rec = (len([x for x in toks if x in p1]) / len(toks)) if toks else 1.0
        out.append(dict(suite=r["suite"], user_task=r["user_task"],
                        injection=r.get("injection"), step=r["step"], tool=r.get("tool"),
                        p1_verdict=r["p1"], span_len=len(span),
                        raw_residual=raw_res, entity_total=len(ents),
                        entity_residual=ent_res, token_recall=round(rec, 3),
                        paraphrased=rec > 0.5))
    n = len(out)
    summary = dict(
        n=n,
        raw_residual=sum(1 for x in out if x["raw_residual"]),
        entity_residual=sum(1 for x in out if x["entity_residual"]),
        paraphrased=sum(1 for x in out if x["paraphrased"]),
        paraphrased_among_p1_deny=sum(1 for x in out if x["paraphrased"] and x["p1_verdict"] == "DENY"),
        p1_deny=sum(1 for x in out if x["p1_verdict"] == "DENY"),
        notes="paraphrased = 载荷专名 token 在 P1 history 的召回 > 0.5")
    json.dump(dict(summary=summary, rows=out),
              open(R + "/probes/p1_residual.json", "w"), ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for x in out:
        print("  %-6s %-13s step=%-2d %-24s p1=%-6s raw=%d ent=%d tok=%.2f"
              % (x["suite"], x["user_task"], x["step"], x["tool"], x["p1_verdict"],
                 x["raw_residual"], len(x["entity_residual"]), x["token_recall"]))


if __name__ == "__main__":
    main()
