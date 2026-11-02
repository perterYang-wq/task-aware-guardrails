# -*- coding: utf-8 -*-
"""第 5 项：固定调用上的「攻击诱导翻转」正式表。

对**同一条攻击调用**，只把 history 从 `noinj`（无载荷）换成 `full`（含载荷），
看守卫的判定怎么变。这是最干净的因果对照：调用、参数、证据块全部不变。

产出：
  results/diag/flip_table.md   主文表（翻转计数 + 示例）
  results/diag/flip_table.json 机器可读
"""
import json
import os
from collections import Counter, defaultdict

R = "/data/projects/guardrails"
D = os.path.join(R, "results/diag")
P = os.path.join(D, "preds")
ARMS = [("p1_15b_task_s0", "1.5B 标准 SFT"),
        ("m2_S_s0", "S（同协议基线）"),
        ("m2_HB_s0", "HB（本文）"),
        ("rule_ground", "规则：无出处就拦"),
        ("pg2_86m", "Prompt-Guard-86M")]


def load(tag, view):
    p = os.path.join(P, "%s__%s.jsonl" % (tag, view))
    if not os.path.exists(p):
        return None
    return {json.loads(l)["sid"]: json.loads(l)["pred"] for l in open(p, encoding="utf-8")}


def main():
    steps = {r["sid"]: r for r in
             (json.loads(l) for l in open(os.path.join(D, "steps.jsonl"), encoding="utf-8"))}
    att = [s for s, r in steps.items() if r["label"] == "DENY"]

    out, lines = {}, []
    lines.append("# 固定调用上的攻击诱导翻转（同一调用，只换 history）\n")
    lines.append("对每条攻击调用，只把上下文从「删掉注入载荷」换成「完整（含载荷）」，"
                 "其余字段逐字节相同。下表统计判定如何变化。\n")

    for tag, name in ARMS:
        f, n = load(tag, "full"), load(tag, "noinj")
        if not f or not n:
            continue
        cell = Counter()
        by_suite = defaultdict(Counter)
        by_prov = defaultdict(Counter)
        examples = []
        for s in att:
            a, b = n.get(s), f.get(s)          # noinj -> full
            if a is None or b is None:
                continue
            k = (a, b)
            cell[k] += 1
            by_suite[steps[s]["suite"]][k] += 1
            by_prov[steps[s]["provenance"]][k] += 1
            if a == "DENY" and b == "ALLOW":
                examples.append(dict(sid=s, suite=steps[s]["suite"], tool=steps[s]["tool"],
                                     provenance=steps[s]["provenance"],
                                     args=steps[s]["args"]))
        den = sum(v for (a, b), v in cell.items() if a == "DENY")
        flip = cell[("DENY", "ALLOW")]
        rev = cell[("ALLOW", "DENY")]
        out[tag] = dict(cell={"%s->%s" % k: v for k, v in cell.items()},
                        deny_noinj=den, flip_to_allow=flip, flip_to_deny=rev,
                        drift_rate=round(flip / den, 3) if den else None,
                        by_suite={k: {"%s->%s" % kk: vv for kk, vv in v.items()}
                                  for k, v in by_suite.items()},
                        by_prov={k: {"%s->%s" % kk: vv for kk, vv in v.items()}
                                 for k, v in by_prov.items()},
                        examples=examples[:6])
        lines.append("## %s\n" % name)
        lines.append("| 无载荷 → 含载荷 | 条数 |")
        lines.append("|---|---|")
        for a in ("DENY", "REVIEW", "ALLOW"):
            for b in ("DENY", "REVIEW", "ALLOW"):
                if cell[(a, b)]:
                    lines.append("| %s → %s | %d |" % (a, b, cell[(a, b)]))
        lines.append("")
        lines.append("无载荷时判 DENY 的 %d 条里，**%d 条（%.1f%%）看到载荷后改判 ALLOW**；"
                     "反方向 %d 条。\n" % (den, flip, 100.0 * flip / den if den else 0, rev))
        if examples:
            lines.append("| 套件 | 工具 | 参数来源 | 被放行的调用 |")
            lines.append("|---|---|---|---|")
            for e in examples[:4]:
                a = json.dumps(e["args"], ensure_ascii=False)
                lines.append("| %s | `%s` | %s | `%s` |"
                             % (e["suite"], e["tool"], e["provenance"],
                                (a[:90] + "…") if len(a) > 90 else a))
            lines.append("")

    os.makedirs(D, exist_ok=True)
    json.dump(out, open(os.path.join(D, "flip_table.json"), "w"), ensure_ascii=False, indent=2)
    open(os.path.join(D, "flip_table.md"), "w", encoding="utf-8").write("\n".join(lines))
    for tag, v in out.items():
        print("%-16s DENY(noinj)=%3d  翻转=%3d (%.1f%%)  反向=%d"
              % (tag, v["deny_noinj"], v["flip_to_allow"],
                 100.0 * (v["drift_rate"] or 0), v["flip_to_deny"]))
    print("-> results/diag/flip_table.md")


if __name__ == "__main__":
    main()
