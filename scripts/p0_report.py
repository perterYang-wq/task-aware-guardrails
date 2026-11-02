# -*- coding: utf-8 -*-
"""P0-7：论文表格只从 results/frozen/unified_eval.json 生成；同时输出新旧口径差异。

用法：
    python scripts/p0_report.py            # 打印表 1/2/3 + 差异
    python scripts/p0_report.py --write    # 同时写 results/frozen/tables.md
"""
import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEW = os.path.join(ROOT, "results", "frozen", "unified_eval.json")
OLD = os.path.join(ROOT, "results", "unified_eval.json")


def f(x, n=3):
    return "%.*f" % (n, x)


def sci(p):
    if p < 1e-4:
        return "%.1e" % p
    return "%.4f" % p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    d = json.load(open(NEW))
    md = []

    md.append("## 表 1  各臂指标（metric_version %s；样本 %d，配对 %d，动作组 %d，任务组 %d）\n"
              % (d["metric_version"], d["n_test"], d["n_pairs"],
                 d["n_actions"], d["n_tasks"]))
    md.append("| arm | wins | ties | losses | PRA | SPA | TieRate | Macro-F1 |")
    md.append("|---|---|---|---|---|---|---|---|")
    order = sorted(d["arms"].items(), key=lambda kv: -kv[1]["PRA"])
    for name, v in order:
        md.append("| %s | %d | %d | %d | %s | %s | %s | %s |"
                  % (name, v["wins"], v["ties"], v["losses"],
                     f(v["PRA"]), f(v["SPA"]), f(v["TieRate"]), f(v["macro_f1"])))
    md.append("")

    md.append("## 表 2  Full − No-task（按动作组分组的 bootstrap；Macro-F1 按任务组）\n")
    md.append("| size | PRA full | PRA blind | ΔPRA | 95%CI(动作组) | p(符号) | "
              "SPA full | SPA blind | ΔSPA | 95%CI(动作组) | McNemar(辅助) | "
              "ΔMacro-F1 | 95%CI(任务组) |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in d["deltas"]:
        md.append("| %s | %s | %s | %+.3f | [%+.3f, %+.3f] | %s | %s | %s | %+.3f | "
                  "[%+.3f, %+.3f] | %s | %+.4f | [%+.4f, %+.4f] |"
                  % (r["size"], f(r["PRA"]["full"]), f(r["PRA"]["blind"]),
                     r["PRA"]["delta"], r["PRA"]["ci_action_boot"][0],
                     r["PRA"]["ci_action_boot"][1], sci(r["PRA"]["p_sign"]),
                     f(r["SPA"]["full"]), f(r["SPA"]["blind"]), r["SPA"]["delta"],
                     r["SPA"]["ci_action_boot"][0], r["SPA"]["ci_action_boot"][1],
                     sci(r["SPA"]["mcnemar_aux"]),
                     r["macro_f1"]["delta"], r["macro_f1"]["ci_task_boot"][0],
                     r["macro_f1"]["ci_task_boot"][1]))
    md.append("")

    p = d["pooled"]
    md.append("## 表 3  合并（部署守卫 0.5B/1.5B/3B）\n")
    md.append("同一 %d 个配对在 %d 个模型上被重复测量，**不可当作独立样本**。\n"
              % (p["n_pairs"], len(p["models"])))
    md.append("| 做法 | 观测数 | p | 说明 |")
    md.append("|---|---|---|---|")
    md.append("| 朴素合并（错误） | %d | %s | %s |"
              % (p["naive_units"], sci(p["naive_mcnemar"]), p["naive_note"]))
    md.append("| 配对层取模型平均（正确） | %d | %s | 每对先对 3 个模型取平均，"
              "再按动作组 bootstrap；%d 对偏向 full、%d 对偏向 blind |"
              % (p["n_pairs"], sci(p["pair_level_sign_p"]),
                 p["pairs_favoring_full"], p["pairs_favoring_blind"]))
    md.append("")
    md.append("配对层平均 Δ = %+.3f，95%%CI(动作组) = [%+.3f, %+.3f]"
              % (p["pair_level_mean_delta"], p["pair_level_ci_action_boot"][0],
                 p["pair_level_ci_action_boot"][1]))
    md.append("")
    md.append("`dataset_hash=%s  split_hash=%s  pairs_hash=%s  seed=%d  metric_version=%s`"
              % (d["dataset_hash"], d["split_hash"], d["pairs_hash"],
                 d["seed"], d["metric_version"]))

    text = "\n".join(md) + "\n"
    print(text)
    if a.write:
        open(os.path.join(ROOT, "results", "frozen", "tables.md"), "w",
             encoding="utf-8").write(text)
        print("-> results/frozen/tables.md")

    # ---------------- 新旧口径差异
    if not os.path.exists(OLD):
        print("\n[无旧结果，跳过差异对比]")
        return
    o = json.load(open(OLD))
    print("\n## 口径差异（旧 unified_eval.json → 新 frozen）\n")
    print("%-16s%14s%14s%14s" % ("arm", "PRA 旧→新", "SPA 旧→新", "MacroF1 旧→新"))
    for name, v in d["arms"].items():
        if name not in o.get("arms", {}):
            continue
        ov = o["arms"][name]
        opra = ov.get("PRA")
        ospa = ov.get("SPA")
        print("%-16s%14s%14s%14s"
              % (name,
                 "%s→%s" % (f(opra) if opra is not None else "-", f(v["PRA"])),
                 "%s→%s" % (f(ospa) if ospa is not None else "-", f(v["SPA"])),
                 "%s→%s" % (f(ov["macro_f1"]), f(v["macro_f1"]))))

    print("\n旧 pooled：360 对 McNemar p = 1.10e-10（把 4 个模型的 90 对当独立样本）")
    print("新 pooled（部署 3 模型，配对层平均）：p = %s，观测数 %d（不是 %d）"
          % (sci(p["pair_level_sign_p"]), p["n_pairs"], p["naive_units"]))
    print("\n△ 主要变化：")
    print("  1) PRA/SPA 点估计不变（定义等价），但 CI 变宽——旧版按配对 i.i.d. "
          "bootstrap，忽略了同动作内多个配对的相关性")
    print("  2) pooled p 从 1.1e-10 变为 %s：旧值把重复测量当独立观测，严重高估显著性"
          % sci(p["pair_level_sign_p"]))


if __name__ == "__main__":
    main()
