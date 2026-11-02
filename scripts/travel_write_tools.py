# -*- coding: utf-8 -*-
"""STEP 2 · travel 正常任务（非注入）的工具调用分布。

用途：决定重训要补「正例」还是「负例」——只有某写工具在正常任务里真实出现，
才可能为它构造"合法调用 + 污染上下文 = ALLOW"的正例。

主口径：results/e2e/travel/m2_HBnt_s0_inj0-1（M0，守卫对干净场景误拦仅 3.3%，
         最接近无守卫行为，且带完整 calls）
交叉核对：m2_HB_s0_calls_inj0-1（M1）

产物：reports/travel_write_tools.md + probes/travel_write_tools.json
"""
import json
import os
from collections import Counter, defaultdict

R = "/data/projects/guardrails"
RUNS = [("M0", "results/e2e/travel/m2_HBnt_s0_inj0-1"),
        ("M1", "results/e2e/travel/m2_HB_s0_calls_inj0-1")]
WRITE = ("send_email", "reserve_hotel", "create_calendar_event")


def analyse(run):
    rows = [json.loads(l) for l in open(os.path.join(R, run, "scen.jsonl"), encoding="utf-8")]
    clean = [r for r in rows if not r.get("injection_present")]
    calls = Counter()
    scen_with = defaultdict(int)
    blocked = Counter()
    for r in clean:
        seen = set()
        for c in (r.get("calls") or []):
            calls[c["tool"]] += 1
            seen.add(c["tool"])
            if c.get("guard_enforced"):
                blocked[c["tool"]] += 1
        for t in seen:
            scen_with[t] += 1
    return dict(n_clean=len(clean), calls=calls, scenes=scen_with, blocked=blocked)


def main():
    out = {}
    for tag, run in RUNS:
        out[tag] = analyse(run)

    a = out["M0"]
    total = a["n_clean"]
    print("[M0] 干净场景 %d，共 %d 次调用" % (total, sum(a["calls"].values())))
    for t, n in a["calls"].most_common():
        print("  %-34s %4d 次 | 覆盖 %2d/%d 场景 | 被拦 %d"
              % (t, n, a["scenes"][t], total, a["blocked"][t]))

    se = a["calls"].get("send_email", 0)
    rh = a["calls"].get("reserve_hotel", 0)
    cc = a["calls"].get("create_calendar_event", 0)
    if se >= 1:
        concl = "A"
        concl_txt = "A: send_email 在 travel 正常任务中出现 ≥1 次 → 可补正例"
    elif rh > 0 or cc > 0:
        concl = "B"
        concl_txt = ("B: send_email 为 0，但 reserve_hotel / create_calendar_event > 0 "
                     "→ 补负例为主，正例只补后两者")
    else:
        concl = "C"
        concl_txt = "C: 三个写工具全为 0 → 只能补负例"

    lines = ["# travel 正常任务的工具调用分布", "",
             "来源：`%s`（M0，守卫对干净场景误拦 3.3%%），" % RUNS[0][1],
             "过滤条件：`injection_present == false`，共 %d 个干净场景。" % total,
             "", "| 工具 | 调用次数 | 覆盖场景数 / %d | 其中被守卫拦下 |" % total,
             "|---|---|---|---|"]
    for t, n in a["calls"].most_common():
        lines.append("| `%s` | %d | %d / %d | %d |"
                     % (t, n, a["scenes"][t], total, a["blocked"][t]))
    lines += ["", "**结论（逐字）**：", "", "```", concl_txt, "```", "",
              "交叉核对（%s，M1）：`send_email` %d 次、`reserve_hotel` %d 次、"
              "`create_calendar_event` %d 次。"
              % (RUNS[1][1], out["M1"]["calls"].get("send_email", 0),
                 out["M1"]["calls"].get("reserve_hotel", 0),
                 out["M1"]["calls"].get("create_calendar_event", 0))]
    os.makedirs(os.path.join(R, "reports"), exist_ok=True)
    open(os.path.join(R, "reports/travel_write_tools.md"), "w", encoding="utf-8").write(
        "\n".join(lines) + "\n")
    json.dump(dict(primary=dict(run=RUNS[0][1], n_clean=total,
                                calls=dict(a["calls"]), scenes=dict(a["scenes"]),
                                blocked=dict(a["blocked"])),
                   crosscheck=dict(run=RUNS[1][1], n_clean=out["M1"]["n_clean"],
                                   calls=dict(out["M1"]["calls"])),
                   conclusion=concl, conclusion_text=concl_txt),
              open(os.path.join(R, "probes/travel_write_tools.json"), "w"),
              ensure_ascii=False, indent=2)
    os.makedirs(os.path.join(R, "runs/auto/round_probe"), exist_ok=True)
    json.dump(dict(step=2, script="scripts/travel_write_tools.py",
                   inputs=[r for _, r in RUNS],
                   outputs=["reports/travel_write_tools.md",
                            "probes/travel_write_tools.json"],
                   rc=0, conclusion=concl,
                   ts=__import__("time").strftime("%Y-%m-%d %H:%M:%S")),
              open(os.path.join(R, "runs/auto/round_probe/step_2.json"), "w"),
              ensure_ascii=False, indent=2)
    print("\n[conclusion] %s" % concl_txt)


if __name__ == "__main__":
    main()
