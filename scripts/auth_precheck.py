# -*- coding: utf-8 -*-
"""离线预检：授权层规则能不能既拦住攻击、又不误杀合法外发。

规则候选（都在 **去掉 <INFORMATION> 块之后** 的 history 上做接地）：
  R1 = 关键参数出现在用户请求原文
  R2 = 关键参数出现在「去载荷后的 history」（工具输出 / 上一轮动作）
  R-any = R1 or R2

对每条外发/写类调用，标出它是不是攻击调用（由 scen 的 attack 标记与工具是否出现在
注入载荷里近似），再看三条规则各自的放行情况。0 GPU，纯文本。
"""
import json
import os
import re

R = "/data/projects/guardrails"
INJ = re.compile(r"<INFORMATION>.*?</INFORMATION>", re.S)
OUT = os.path.join(R, "probes/auth_layer_precheck.json")

# 写类/外发工具（与 safe_guard.HIGH_RISK 对齐，去掉 delete_/remove_ 前缀项）
KEY = {
    "send_email": ["recipients"],
    "send_direct_message": ["recipient"],
    "send_channel_message": ["channel"],
    "post_webpage": ["url"],
    "reserve_hotel": ["hotel"],
    "reserve_restaurant": ["restaurant"],
    "create_calendar_event": ["title"],
    "send_money": ["recipient"],
    "update_password": ["password"],
}
RUNS = [
    ("travel", "meta", "results/e2e/travel/m2_HB_s0_b6meta_inj1"),
    ("travel", "static", "results/e2e/travel/m2_HB_s0_calls_inj0-1"),
    ("slack", "static", "results/e2e/slack/m2_HB_s0_b10_inj1-3_revallow"),
]


def norm(x):
    return re.sub(r"\s+", " ", str(x)).strip().lower()


def grounded(vals, text):
    t = norm(text)
    return all(norm(v) in t for v in vals) if vals else True


def main():
    rows = []
    for suite, kind, run in RUNS:
        p = os.path.join(R, run, "scen.jsonl")
        if not os.path.exists(p):
            continue
        for line in open(p, encoding="utf-8"):
            sc = json.loads(line)
            instr = sc.get("instruction") or ""
            for h in (sc.get("guard_hits") or []):
                tool = h.get("tool")
                if tool not in KEY:
                    continue
                args = h.get("args") or {}
                vals = []
                for k in KEY[tool]:
                    v = args.get(k)
                    if isinstance(v, list):
                        vals += [str(x) for x in v]
                    elif v:
                        vals.append(str(v))
                # 取该步 history
                rows.append(dict(suite=suite, kind=kind, run=run,
                                 user_task=sc.get("user_task"),
                                 inj=sc.get("injection_task"),
                                 attack=bool(sc.get("injection_present")),
                                 step=h.get("idx"), tool=tool,
                                 guard=h.get("decision"), vals=vals,
                                 instr_ok=grounded(vals, instr)))
    # 需要 history：从 trace 取
    tr = {}
    for suite, kind, run in RUNS:
        tp = os.path.join(R, run, "trace.jsonl")
        if not os.path.exists(tp):
            continue
        for line in open(tp, encoding="utf-8"):
            t = json.loads(line)
            tr[(run, t["user_task"], t.get("injection_task"), t["step"])] = t.get("history_full") or ""
    for r in rows:
        # guard_hits 的 idx 是 0-based；trace.step 是 1-based，且 history_full 是"调用前"的历史
        h = tr.get((r["run"], r["user_task"], r["inj"], (r["step"] or 0) + 1), "")
        r["hist_ok"] = grounded(r["vals"], INJ.sub("", h))
        r["payload_has_val"] = any(norm(v) in norm(h) and norm(v) not in norm(INJ.sub("", h))
                                   for v in r["vals"])

    def tab(rs, name):
        if not rs:
            return
        n = len(rs)
        print("%-28s n=%3d | R1 放行 %3d | R2 放行 %3d | R1|R2 放行 %3d"
              % (name, n, sum(1 for r in rs if r["instr_ok"]),
                 sum(1 for r in rs if r["hist_ok"]),
                 sum(1 for r in rs if r["instr_ok"] or r["hist_ok"])))
        for r in rs:
            flag = "PASS" if (r["instr_ok"] or r["hist_ok"]) else "BLOCK"
            print("    %-6s %-12s %-22s %-6s guard=%-6s %s vals=%s"
                  % (r["suite"], r["user_task"], r["tool"], flag, r["guard"], r["kind"], r["vals"][:2]))

    print("== 攻击调用 ==")
    tab([r for r in rows if r["attack"]], "attack")
    print("\n== 干净调用 ==")
    tab([r for r in rows if not r["attack"]], "clean")
    json.dump(rows, open(OUT, "w"), ensure_ascii=False, indent=2)
    print("\n->", OUT)


if __name__ == "__main__":
    main()
