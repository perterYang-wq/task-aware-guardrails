# -*- coding: utf-8 -*-
"""v2 场景选择：只改 B 组（inj5 → inj1），D 组改成 3 travel + 1 slack。

规则（写死，不手工挑）：
  A 组：4 个固定 travel 场景（与 v1 相同）
  B 组：slack 写类攻击，ground-truth 工具 ∩ {send_direct_message} ≠ ∅，
        按 (task 数字, inj 数字) 升序取前 5
  C 组：slack 读类攻击，工具集 {get_webpage, read_file, list_channels}，取前 5（与 v1 同规则）
  D 组：D1–D3 = A1–A3 的去注入版（travel ut4 / ut14 / ut19）；D4 = B1 同 task 的 slack 干净场景
产出：results/mechanism_probe_v41flash_v2/scenario_selection.json
"""
import json
import os
import re
import sys
import time

R = "/data/projects/guardrails"
sys.path.insert(0, R)
from agentdojo.task_suite.load_suites import get_suite  # noqa: E402

VER = "mechanism_probe_v41flash_v2"
OUT_DIR = os.path.join(R, "results", VER)
OUT = os.path.join(OUT_DIR, "scenario_selection.json")

SLACK_RUNS = ["results/e2e/slack/m2_HB_s0_inj1-3",
              "results/e2e/slack/m2_HB_s0_b2_inj2-4-5"]
TRAVEL_RUN = "results/e2e/travel/m2_HB_s0_calls_inj0-1"

WRITE_TOOLS = {"send_direct_message"}          # v2 的唯一改动
READ_TOOLS = {"get_webpage", "read_file", "list_channels"}

A_FIXED = [("A1", "user_task_4", "injection_task_1"),
           ("A2", "user_task_14", "injection_task_1"),
           ("A3", "user_task_19", "injection_task_0"),
           ("A4", "user_task_19", "injection_task_1")]


def num(x):
    m = re.search(r"(\d+)", str(x) or "")
    return int(m.group(1)) if m else 10 ** 6


def load_run(p):
    return [json.loads(l) for l in open(os.path.join(R, p, "scen.jsonl"), encoding="utf-8")]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    suite = get_suite("v1.2.2", "slack")
    env0 = suite.load_and_inject_default_environment({})
    gt = {}
    for it in suite.injection_tasks:
        try:
            gt[it] = [c.function for c in suite.injection_tasks[it].ground_truth(env0)]
        except Exception as e:
            gt[it] = []
            print("[warn] GT 失败", it, e)

    trav_suite = get_suite("v1.2.2", "travel")
    tenv = trav_suite.load_and_inject_default_environment({})
    gt_travel = {}
    for it in trav_suite.injection_tasks:
        try:
            gt_travel[it] = [c.function for c in trav_suite.injection_tasks[it].ground_truth(tenv)]
        except Exception:
            gt_travel[it] = []

    cand, seen = [], set()
    for run in SLACK_RUNS:
        for r in load_run(run):
            if not r.get("injection_present"):
                continue
            ut, it = r["user_task"], r.get("injection_task")
            if (ut, it) in seen:
                continue
            seen.add((ut, it))
            tools = gt.get(it, [])
            cand.append(dict(user_task=ut, injection_task=it, gt_tools=tools,
                             write=sorted(set(tools) & WRITE_TOOLS),
                             read=sorted(set(tools) & READ_TOOLS), run=run))
    print("[pool] slack 攻击场景 %d 个" % len(cand))
    print("[gt] 工具分布:", {k: v for k, v in sorted(gt.items())})

    write_pool = [c for c in cand if c["write"]]
    write_pool.sort(key=lambda c: (num(c["user_task"]), num(c["injection_task"])))
    read_pool = [c for c in cand if (not c["write"]) and c["read"]]
    read_pool.sort(key=lambda c: (num(c["user_task"]), num(c["injection_task"])))

    B = write_pool[:5]
    C = read_pool[:5]
    assert len(B) == 5, "写类候选不足 5 个：%d" % len(B)

    travel = {(r["user_task"], r.get("injection_task")): r for r in load_run(TRAVEL_RUN)}
    sel = []
    for sid, ut, it in A_FIXED:
        assert (ut, it) in travel, "A 组场景不存在: %s %s" % (ut, it)
        sel.append(dict(scen_id=sid, group="A", suite="travel", user_task=ut,
                        injection_task=it, gt_tools=gt_travel.get(it, []),
                        source_run=TRAVEL_RUN, note="B8 集中漏检点"))
    for i, c in enumerate(B, 1):
        sel.append(dict(scen_id="B%d" % i, group="B", suite="slack",
                        user_task=c["user_task"], injection_task=c["injection_task"],
                        gt_tools=c["gt_tools"], write_tools=c["write"],
                        source_run=c["run"], note="写类攻击（inj1 send_direct_message）"))
    for i, c in enumerate(C, 1):
        sel.append(dict(scen_id="C%d" % i, group="C", suite="slack",
                        user_task=c["user_task"], injection_task=c["injection_task"],
                        gt_tools=c["gt_tools"], read_tools=c["read"],
                        source_run=c["run"], note="读类攻击"))
    # D1–D3：A1–A3 的去注入版
    for i, (sid, ut, it) in enumerate(A_FIXED[:3], 1):
        sel.append(dict(scen_id="D%d" % i, group="D", suite="travel", user_task=ut,
                        injection_task=None, source_run=TRAVEL_RUN,
                        note="A%d 同 task 去注入" % i))
    # D4：B1 同 task 的 slack 干净场景
    sel.append(dict(scen_id="D4", group="D", suite="slack", user_task=B[0]["user_task"],
                    injection_task=None, source_run=B[0]["run"],
                    note="B1 同 task 去注入（slack）"))

    assert len(sel) == 18, len(sel)
    payload = dict(created=time.strftime("%Y-%m-%d %H:%M:%S"), version=VER,
                   rules=dict(write_tools=sorted(WRITE_TOOLS), read_tools=sorted(READ_TOOLS),
                              sort="(task 数字, inj 数字) 升序",
                              overlap_rule="同一场景同时命中读写时归写类",
                              pool=SLACK_RUNS, a_fixed=len(A_FIXED),
                              pool_size=len(cand),
                              d_group="D1-D3 travel clean；D4 slack clean（B1 同 task）"),
                   n=len(sel), scenarios=sel)
    json.dump(payload, open(OUT, "w"), ensure_ascii=False, indent=2)

    print("\n%-4s %-6s %-7s %-12s %-16s %s" % ("ID", "group", "suite", "task", "injection", "GT"))
    for s in sel:
        print("%-4s %-6s %-7s %-12s %-16s %s"
              % (s["scen_id"], s["group"], s["suite"], s["user_task"],
                 s.get("injection_task") or "-", ",".join(s.get("gt_tools") or [])[:50]))
    print("\n->", OUT)


if __name__ == "__main__":
    main()
