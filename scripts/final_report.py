# -*- coding: utf-8 -*-
"""把指标层（unified_eval.json, p0-1.0）与推断层（final_stats.json, p0-1.1）
合并成**唯一**的冻结产物 final_report.json，并由它生成论文全部表格。

不覆盖旧结果：unified_eval.json 与 final_stats.json 原样保留，本脚本只读。
"""
import collections
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FROZEN = os.path.join(ROOT, "results", "frozen")

METRIC_VERSION = "p0-1.1"
DEPLOY = ["0.5B", "1.5B", "3B"]
EXPL = ["7B", "1.5B_lr4"]
ARM_ORDER = [
    ("full_3B", "deploy"), ("full_1.5B_lr4", "exploratory"), ("full_7B", "exploratory"),
    ("full_1.5B", "deploy"), ("full_0.5B", "deploy"),
    ("blind_3B", "deploy"), ("blind_1.5B_lr4", "exploratory"), ("blind_7B", "exploratory"),
    ("blind_1.5B", "deploy"), ("blind_0.5B", "deploy"),
    ("zs_7B", "baseline"), ("zs_3B", "baseline"), ("zs_1.5B", "baseline"), ("zs_0.5B", "baseline"),
    ("base_tfidf_full", "surface"), ("base_tfidf_task", "surface"),
    ("base_tfidf_action", "surface"), ("base_action_lookup", "surface"),
    ("base_tool_lookup", "surface"), ("base_majority", "surface"),
]


def main():
    ev = json.load(open(os.path.join(FROZEN, "unified_eval.json"), encoding="utf-8"))
    fs = json.load(open(os.path.join(FROZEN, "final_stats.json"), encoding="utf-8"))

    arms = ev["arms"]
    rep = {
        "metric_version": METRIC_VERSION,
        "sources": {"metrics": "unified_eval.json (p0-1.0)", "inference": "final_stats.json (p0-1.1)"},
        "provenance": {
            "dataset_hash": ev["dataset_hash"], "split_hash": ev["split_hash"],
            "pairs_hash": ev["pairs_hash"], "seed": ev["seed"],
            "n_test": ev["n_test"], "n_pairs": ev["n_pairs"],
            "n_action_groups": ev["n_actions"], "n_task_groups": ev["n_tasks"],
        },
        "deployment": {"guards": DEPLOY, "weights": {s: 1.0 / 3 for s in DEPLOY},
                       "note": "等权预先固定，不按测试表现调整；7B Guard 不参与合并"},
        "arms": {k: arms[k] for k in arms},
        "arm_role": {},
        "deltas": {},
        "pooled_equal_weight": fs["merged_equal_weight"],
        "p_attribution": fs["p_attribution"],
    }
    for name, role in ARM_ORDER:
        if name in arms:
            rep["arm_role"][name] = role

    for size in DEPLOY + EXPL:
        src = fs["single"][size] if size in DEPLOY else fs["exploratory"][size]
        rep["deltas"][size] = {
            "PRA": src["PRA"],
            "SPA": src["SPA"],
            "macro_f1_delta": next(r["macro_f1"] for r in ev["deltas"] if r["size"] == size),
            "role": "deploy" if size in DEPLOY else "exploratory",
        }

    out = os.path.join(FROZEN, "final_report.json")
    json.dump(rep, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ------------------------------------------------------------------ markdown
    md = []
    md.append("<!-- 由 scripts/final_report.py 生成；唯一数据源 final_report.json；"
              "metric_version = %s -->" % METRIC_VERSION)
    md.append("\n## 0. 元数据\n")
    p = rep["provenance"]
    md.append("| 字段 | 值 |\n|---|---|")
    md.append("| metric_version | `%s`（指标定义同 p0-1.0，仅推断层修正） |" % METRIC_VERSION)
    md.append("| dataset_hash | `%s` |" % p["dataset_hash"])
    md.append("| split_hash | `%s` |" % p["split_hash"])
    md.append("| pairs_hash | `%s` |" % p["pairs_hash"])
    md.append("| seed | %d |" % p["seed"])
    md.append("| 测试样本 / 配对 / 动作组 / 任务组 | %d / %d / %d / %d |"
              % (p["n_test"], p["n_pairs"], p["n_action_groups"], p["n_task_groups"]))
    md.append("| 部署守卫 | 0.5B, 1.5B, 3B（等权 1/3） |")
    md.append("| 探索性 | 7B Guard（不进合并、不作部署结论） |")

    md.append("\n## A. 臂级指标（wins / ties / losses）\n")
    md.append("| arm | role | wins | ties | losses | PRA | SPA | TieRate | Macro-F1 |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    for name, role in ARM_ORDER:
        if name not in arms:
            continue
        a = arms[name]
        md.append("| %s | %s | %d | %d | %d | %.3f | %.3f | %.3f | %.3f |"
                  % (name, role, a["wins"], a["ties"], a["losses"],
                     a["PRA"], a["SPA"], a["TieRate"], a["macro_f1"]))

    md.append("\n## B. Full − No-task（主结果：逐尺寸）\n")
    md.append("| size | role | ΔPRA | CI (action cluster) | p cluster-perm | p pair-sign (aux) | "
              "ΔSPA | CI (action cluster) | p cluster-perm | p pair-sign (aux) | "
              "ΔMacro-F1 | CI (task cluster) | design effect |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for size in DEPLOY + EXPL:
        d = rep["deltas"][size]
        pr, sp, mf = d["PRA"], d["SPA"], d["macro_f1_delta"]
        md.append("| %s | %s | %+.3f | [%+.3f, %+.3f] | %.4f | %.4f | %+.3f | [%+.3f, %+.3f] | %.4f | %.4f | %+.3f | [%+.3f, %+.3f] | %.2f |"
                  % (size, d["role"], pr["delta"], pr["ci_action_cluster"][0], pr["ci_action_cluster"][1],
                     pr["p_cluster_perm"], pr["p_pair_sign_aux"],
                     sp["delta"], sp["ci_action_cluster"][0], sp["ci_action_cluster"][1],
                     sp["p_cluster_perm"], sp["p_pair_sign_aux"],
                     mf["delta"], mf["ci_task_boot"][0], mf["ci_task_boot"][1],
                     pr["design_effect"]))

    md.append("\n## C. 等权合并（辅助，三守卫各 1/3）\n")
    md.append("| metric | Δ | per-guard | CI (action cluster) | p cluster-perm | p pair-sign (aux) | design effect |")
    md.append("|---|---|---|---|---|---|---|")
    for tag in ("PRA", "SPA"):
        d = rep["pooled_equal_weight"][tag]
        md.append("| %s | %+.4f | %s | [%+.3f, %+.3f] | %.4f | %.4f (%d:%d) | %.2f |"
                  % (tag, d["delta"], ", ".join("%+.4f" % x for x in d["delta_per_guard"]),
                     d["ci_action_cluster"][0], d["ci_action_cluster"][1],
                     d["p_cluster_perm"], d["p_pair_sign_aux"],
                     d["pairs_better"], d["pairs_worse"], d["design_effect"]))

    md.append("\n## D. 旧 p=0.0007 的归属\n")
    pa = rep["p_attribution"]
    md.append("| metric | 配对符号检验 p | 优/劣 | 动作聚类置换 p | 结论 |\n|---|---|---|---|---|")
    for tag in ("PRA", "SPA"):
        c = pa[tag]
        md.append("| %s | %.5f | %d:%d | %.4f | %s |"
                  % (tag, c["pair_sign_p"], c["better"], c["worse"], c["p_cluster_perm"],
                     "**复现旧的 0.0007**" if tag in pa.get("old_p=0.0007_matches", []) else "—"))
    md.append("\n旧值 0.0007 = **SPA 的配对层普通符号检验**（41:15），不是动作聚类检验。"
              "已降级为辅助结果，旧文件未覆盖。")

    md_path = os.path.join(FROZEN, "final_report.md")
    open(md_path, "w", encoding="utf-8").write("\n".join(md) + "\n")
    print("-> %s" % out)
    print("-> %s" % md_path)
    print("\n" + "\n".join(md[-14:]))


if __name__ == "__main__":
    main()
