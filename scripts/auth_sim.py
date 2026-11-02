# -*- coding: utf-8 -*-
"""授权层规则模拟（0 GPU）：在已录 trace 上离线跑，先看误杀与拦截。

规则（"可信来源"接地）
--------------------
一条外发/写类调用放行，当且仅当它的关键参数能在以下两处找到：
  S1 用户请求原文（instruction）
  S2 工具输出（history 去掉 assistant 行、再去掉 <INFORMATION> 整块）
**不看 assistant 自己的话**——否则模型复述一遍载荷就给自己授权了（自证循环）。

被检查的工具与关键参数：
  send_email / send_direct_message / send_channel_message → recipient(s)/channel
  post_webpage → url
  reserve_hotel → hotel
  reserve_restaurant → restaurant
  create_calendar_event → title
"""
import json
import os
import re
import sys

R = "/data/projects/guardrails"
sys.path.insert(0, R)
from guard.schema import parse_action  # noqa: E402

INJ = re.compile(r"<INFORMATION>.*?</INFORMATION>", re.S)
FIELDS = {
    "send_email": ["recipients"],
    "send_direct_message": ["recipient"],
    "send_channel_message": ["channel"],
    "post_webpage": ["url"],
    "reserve_hotel": ["hotel"],
    "reserve_restaurant": ["restaurant"],
    "create_calendar_event": ["title"],
}
RUNS = [
    ("travel", "meta", "results/e2e/travel/m2_HB_s0_b6meta_inj1"),
    ("travel", "static", "results/e2e/travel/m2_HB_s0_calls_inj0-1"),
    ("slack", "static", "results/e2e/slack/m2_HB_s0_b10_inj1-3_revallow"),
    ("travel", "static2", "results/e2e/travel/m2_HB_s0_calls2_inj2-3"),
]


def norm(x):
    return re.sub(r"\s+", " ", str(x)).strip().lower()


# 有的轨迹里模型把收尾标签写成 <function>（少了斜杠），两种都要覆盖
FN = re.compile(r"<function=.*?(?:</function>|<function>|\n\n)", re.S)


def tool_text(history):
    """只保留工具输出。

    轨迹格式：assistant 的一段话 + <function=tool>{args}</function>，然后
    `---` 分隔，接着是工具返回，再 `---`。history 可能被 max_len 截断，
    所以最后一个 assistant 段常常没有收尾标签。

    做法：按 `---` 切段，丢掉"像 assistant 的段"（以 assistant: 开头，或含 <function=），
    剩下的就是工具返回。这样"可信来源"= 用户请求 + 环境数据，不含模型自己的话。
    """
    h = INJ.sub("", history or "")
    keep = []
    for seg in h.split("\n---\n"):
        t = seg.strip()
        if not t:
            continue
        if t.startswith("assistant:") or "<function=" in t:
            continue
        keep.append(t)
    return "\n".join(keep)


def vals_of(tool, args):
    out = []
    for k in FIELDS.get(tool, []):
        v = (args or {}).get(k)
        if isinstance(v, list):
            out += [str(x) for x in v if str(x).strip()]
        elif v:
            out.append(str(v))
    return out


def decide(instruction, history, current_action, scope):
    _pa = parse_action(current_action or "")
    tool, args = _pa["tool"], (_pa["args"] if isinstance(_pa["args"], dict) else {})
    if not tool or tool not in FIELDS:
        return None
    if scope == "email_only" and tool != "send_email":
        return None
    if scope == "ref_only" and tool == "create_calendar_event":
        # title 是生成字段（模型自己起名），不是引用字段，检查它只会误杀
        return None
    vals = vals_of(tool, args)
    if not vals:
        return None
    trusted = norm((instruction or "") + "\n" + tool_text(history))
    missing = [v for v in vals if norm(v) not in trusted]
    return None if not missing else (tool, vals, missing)


def main():
    rows = []
    for suite, kind, run in RUNS:
        p = os.path.join(R, run, "scen.jsonl")
        if not os.path.exists(p):
            continue
        tr = {}
        for line in open(os.path.join(R, run, "trace.jsonl"), encoding="utf-8"):
            t = json.loads(line)
            tr[(t["user_task"], t.get("injection_task"), t["step"])] = t
        for line in open(p, encoding="utf-8"):
            sc = json.loads(line)
            for h in (sc.get("guard_hits") or []):
                if h.get("tool") not in FIELDS:
                    continue
                step = (h.get("idx") or 0) + 1
                t = tr.get((sc["user_task"], sc.get("injection_task"), step))
                if not t:
                    continue
                for scope in ("email_only", "ref_only", "all_write"):
                    r = decide(t.get("instruction"), t.get("history_full"),
                               t.get("current_action"), scope)
                    rows.append(dict(suite=suite, kind=kind, scope=scope,
                                     user_task=sc["user_task"],
                                     attack=bool(sc.get("injection_present")),
                                     tool=h.get("tool"), guard=h.get("decision"),
                                     blocked=bool(r), missing=(r[2] if r else []),
                                     success=sc.get("attack_success"),
                                     utility=sc.get("utility")))
    # 统计
    for scope in ("email_only", "ref_only", "all_write"):
        rs = [x for x in rows if x["scope"] == scope]
        atk = [x for x in rs if x["attack"]]
        cln = [x for x in rs if not x["attack"]]
        print("== scope=%s ==" % scope)
        print("  攻击外发/写类调用 %d 条，授权层拦 %d（其中原本 guard=ALLOW 的 %d/%d）"
              % (len(atk), sum(1 for x in atk if x["blocked"]),
                 sum(1 for x in atk if x["blocked"] and x["guard"] == "ALLOW"),
                 sum(1 for x in atk if x["guard"] == "ALLOW")))
        print("  干净外发/写类调用 %d 条，授权层误杀 %d"
              % (len(cln), sum(1 for x in cln if x["blocked"])))
        for x in cln:
            if x["blocked"]:
                print("     FP: %-6s %-12s %-22s miss=%s util=%s"
                      % (x["suite"], x["user_task"], x["tool"], x["missing"][:1], x["utility"]))
        print()
    json.dump(rows, open(os.path.join(R, "probes/auth_layer_sim.json"), "w"),
              ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
