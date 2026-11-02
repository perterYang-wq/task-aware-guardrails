# -*- coding: utf-8 -*-
"""诊断数据集构建：把三套件的真实 agent 轨迹统一成「步级授权判定」样本。

为什么要这个
------------
现有离线训练集 PAB-RD 的负样本来自**文档解析**（文档里写了 X，动作却做 Y），
而 AgentDojo 的真实攻击是**工具返回值被注入**（历史里多了一段攻击者指令，
动作对历史自洽）。两者分布不同，但此前一直在 PAB-RD 上报告指标。
本脚本不改任何已有数据，只从已采集的轨迹里重建一个「线上分布」的评测集，
使同一批 checkpoint 能在真实攻击调用上被评估。

五档 history 视图（instruction 与 current_action 逐字节相同，只换 history 槽位）
--------------------------------------------------------------------------------
none     不给历史。= 论文里的 Clean View。同时去掉了接地证据，因此它是
         「完全不看上下文」的下界，只能用来回答"历史贡献了多少"。
last1    最近 1 条工具输出
last3    最近 3 条工具输出
full     全部工具输出。= 真实线上输入，= Full View。
noinj    与 full 逐字节相同，唯独把 <INFORMATION>…</INFORMATION> 载荷删掉。
         **这是因果对照**：证据、工具输出、轮次全部不变，只删掉攻击者写的那段话。
         full 与 noinj 的差就是「注入载荷本身造成的判定偏移」，
         排除了"历史变长/证据变多"的混淆。

标签口径
--------
attack : 该调用命中该注入任务的 ground-truth（v2 标签，修复过 schedule_transaction 漏标）
legit  : 其余调用
REVIEW : travel 的 37 条 uncertain（历史有注入标记但未命中 gt），单列，不进主指标
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

R = "/data/projects/guardrails"
sys.path.insert(0, R)
from guard.router import gamma_of  # noqa: E402

OUT_DIR = os.path.join(R, "results/diag")

SUITES = {
    "banking": ("runs/ad_bank2_trace.jsonl", "results/ad_v3/banking/labels_banking_v2.jsonl"),
    "travel": ("results/ad_v3/travel/trace_merged.jsonl", "results/ad_v3/travel/contract_eval_v2.json"),
    "slack": ("results/ad_v3/slack/trace_merged.jsonl", "results/ad_v3/slack/labels_slack_v2.jsonl"),
}

INJ_MARK = "<INFORMATION>"
MAX_ONE = 3000            # 单条工具输出截断（与 trace 落盘时的 output[:3000] 一致）
DEFAULT_MAX_TOTAL = 6000  # 各视图总预算（字符）
VIEWS = ("none", "last1", "last3", "full", "noinj")

# 允许未闭合（截断把 </INFORMATION> 切掉时，删到该段末尾）
_INJ_SPAN = re.compile(r"<INFORMATION>.*?(?:</INFORMATION>|$)", re.S)


def load_jsonl(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def segments(r):
    """返回 [(tool, text)]，只保留工具输出，丢掉 assistant 台词。

    丢 assistant 台词的理由：PAB 模板槽位语义是「此前检索到的取值」，
    训练数据里该槽位只有证据块，没有 agent 自己的思考。放进去既造成训练/评测
    分布不一致，也会额外泄漏 agent 对注入内容的转述。
    """
    outs = r.get("tool_outputs")
    if outs:
        return [(o.get("tool") or "?", (o.get("output") or "")[:MAX_ONE]) for o in outs]
    full = r.get("history_full") or r.get("history") or ""
    seg = []
    for part in full.split("\n---\n"):
        part = part.strip()
        if not part or part.startswith("assistant:"):
            continue
        seg.append(("?", part[:MAX_ONE]))
    return seg


def fmt_hist(segs, max_total):
    blocks = ["[Tool: %s]\n%s" % (t, x) for t, x in segs if (x or "").strip()]
    txt = "\n\n".join(blocks)
    if len(txt) > max_total:
        return txt[-max_total:], 1
    return txt, 0


def strip_inj(segs):
    out = []
    for t, x in segs:
        y = _INJ_SPAN.sub("", x or "")
        if y.strip():
            out.append((t, y))
    return out


def _argvals(args):
    """取出参数里"有辨识度"的字符串值（>=6 字符），用于接地判定。"""
    vs = []
    for v in (args or {}).values():
        if isinstance(v, str) and len(v) >= 6:
            vs.append(v)
        elif isinstance(v, list):
            vs += [str(x) for x in v if isinstance(x, str) and len(x) >= 6]
    return vs


def provenance(args, segs, payload_text, noinj_text):
    """判断该调用的关键参数值来自哪里——**机制分解用**。

    in_payload_only : 只出现在注入载荷里（剥掉载荷后就找不到）→ 接地被污染
    in_evidence     : 在剥离载荷后的合法证据里就能找到 → 接地没问题，
                      失败只可能来自「授权边界」而非「证据可信性」
    in_neither      : 两处都找不到（参数是 agent 自己编的）
    """
    vs = _argvals(args)
    if not vs:
        return "no_strong_arg", 0, 0, 0
    p = sum(1 for v in vs if v in payload_text)
    e = sum(1 for v in vs if v in noinj_text)
    n = len(vs)
    if e > 0:
        tag = "in_evidence"
    elif p > 0:
        tag = "in_payload_only"
    else:
        tag = "in_neither"
    return tag, p, e, n


def join_key(t, l):
    return (t["user_task"], t.get("injection_task"), t["step"], t["tool"],
            json.dumps(t.get("args") or {}, sort_keys=True, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-total", type=int, default=DEFAULT_MAX_TOTAL)
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "steps.jsonl"))
    a = ap.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)

    all_rows, stat = [], {}
    for suite, (trp, labp) in SUITES.items():
        trace = load_jsonl(os.path.join(R, trp))
        labels = (load_jsonl(os.path.join(R, labp)) if labp.endswith(".jsonl")
                  else json.load(open(os.path.join(R, labp)))["decisions"])
        assert len(trace) == len(labels), "%s: %d vs %d" % (suite, len(trace), len(labels))
        bad = [i for i, (t, l) in enumerate(zip(trace, labels))
               if t["tool"] != (l.get("tool") or l.get("tool_name"))]
        assert not bad, "%s: tool mismatch at %s" % (suite, bad[:5])

        n_att = n_legit = n_unc = 0
        for i, (t, l) in enumerate(zip(trace, labels)):
            lab = l.get("attack_call_label") or l.get("label")
            if lab == "attack":
                label, n_att = "DENY", n_att + 1
            elif lab == "uncertain":
                label, n_unc = "REVIEW", n_unc + 1
            else:
                label, n_legit = "ALLOW", n_legit + 1

            segs = segments(t)
            segs_clean = strip_inj(segs)
            payload_text = "\n".join(m.group(0) for _, y in segs for m in _INJ_SPAN.finditer(y))
            prov, n_pay, n_evi, n_val = provenance(
                t.get("args") or {}, segs, payload_text, "\n".join(x for _, x in segs_clean))
            v, cut = {}, {}
            v["none"] = ""
            v["last1"], _ = fmt_hist(segs[-1:], a.max_total)
            v["last3"], _ = fmt_hist(segs[-3:], a.max_total)
            v["full"], cut["full"] = fmt_hist(segs, a.max_total)
            v["noinj"], cut["noinj"] = fmt_hist(segs_clean, a.max_total)

            rec = dict(
                sid="%s#%d" % (suite, i), suite=suite,
                scenario_id="%s|%s" % (t["user_task"], t.get("injection_task")),
                task_id=t["user_task"], injection_task=t.get("injection_task"),
                in_attacked_scenario=t.get("injection_task") is not None,
                step_idx=t["step"], tool=t["tool"], args=t.get("args") or {},
                instruction=t.get("instruction") or "",
                current_action=t.get("current_action") or "",
                label=label,
                attack_sensitive=bool(label == "DENY" and gamma_of(t["tool"]) >= 2),
                injection_exposed=bool(t.get("injection_exposed")),
                n_seg=len(segs), n_seg_clean=len(segs_clean),
                hist_none=v["none"], hist_last1=v["last1"], hist_last3=v["last3"],
                hist_full=v["full"], hist_noinj=v["noinj"],
                hist_cut_full=cut["full"], hist_cut_noinj=cut["noinj"],
                inj_span_chars=len(payload_text),
                provenance=prov, n_val_arg=n_val,
                n_val_in_payload=n_pay, n_val_in_evidence=n_evi,
                gamma=gamma_of(t["tool"]),
            )
            all_rows.append(rec)
        stat[suite] = dict(
            n=len(trace), attack=n_att, legit=n_legit, uncertain=n_unc,
            scenarios=len({(t["user_task"], t.get("injection_task")) for t in trace}),
            attacked_scen=len({t["user_task"] for t in trace if t.get("injection_task")}),
            clean_scen=len({t["user_task"] for t in trace if not t.get("injection_task")}),
            exposed=sum(1 for t in trace if t.get("injection_exposed")))

    with open(a.out, "w", encoding="utf-8") as f:
        for r in all_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    att = [r for r in all_rows if r["label"] == "DENY"]
    meta = dict(
        n_total=len(all_rows), label=dict(Counter(r["label"] for r in all_rows)),
        per_suite=stat,
        hist_chars={k: dict(mean=round(sum(len(r["hist_" + k]) for r in all_rows) / len(all_rows), 1),
                            mx=max(len(r["hist_" + k]) for r in all_rows),
                            cut=sum(r["hist_cut_" + k] for r in all_rows) if k in ("full", "noinj") else 0)
                    for k in VIEWS},
        attack_with_inj_mark=sum(1 for r in att if r["inj_span_chars"] > 0),
        attack_inj_span_mean=round(sum(r["inj_span_chars"] for r in att) / max(1, len(att)), 1),
        attack_hist_unchanged_by_strip=sum(1 for r in att if r["n_seg"] == r["n_seg_clean"]),
        attack_provenance=dict(Counter(r["provenance"] for r in att)),
    )
    json.dump(meta, open(os.path.join(OUT_DIR, "build_meta.json"), "w"), ensure_ascii=False, indent=2)
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
