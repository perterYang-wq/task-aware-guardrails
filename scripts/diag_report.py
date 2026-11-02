# -*- coding: utf-8 -*-
"""把 results/diag/metrics.json 渲染成 Markdown 报告（论文表格直接取这里）。

只做渲染，不做任何再计算——所有数字来自 diag_metrics.py 的同一次运行，
保证「报告里的每个数只有一条计算路径」。
"""
import json
import os

R = "/data/projects/guardrails"
D = os.path.join(R, "results/diag")

ARM_DESC = {
    "zs_05b": "Qwen2.5-0.5B 零样本",
    "zs_15b": "Qwen2.5-1.5B 零样本",
    "p1_15b_task_s0": "1.5B task-aware s0（标准授权 SFT）",
    "p1_15b_task_s42": "1.5B task-aware s42",
    "p1_15b_task_s123": "1.5B task-aware s123",
    "p1_15b_nt_s0": "1.5B task-blind s0（去掉用户请求训练）",
    "p1_3b_task_s0": "3B task-aware s0",
    "p1_3b_task_s42": "3B task-aware s42",
    "p1_3b_task_s123": "3B task-aware s123",
    "m2_S_s0": "M2-S 仅 PAB-RD（同协议重训基线）",
    "m2_H_s0": "M2-H + 攻击轨迹 hard negative",
    "m2_HV_s0": "M2-HV + 无载荷反事实视图",
    "m2_HP_s0": "M2-HP + 成对偏好（本文方法）",
}

VIEW_DESC = {
    "none": "不给历史（Clean View）",
    "last1": "最近 1 条工具输出",
    "last3": "最近 3 条工具输出",
    "full": "全部工具输出（线上真实输入）",
    "noinj": "同上但剥掉注入载荷（因果对照）",
}


def f(x, n=3):
    if x is None or (isinstance(x, float) and x != x):
        return "—"
    return ("%%.%df" % n) % x


def main():
    m = json.load(open(os.path.join(D, "metrics.json")))
    b = json.load(open(os.path.join(D, "build_meta.json")))
    L = []
    A = L.append

    A("# 错位诊断报告（自动生成，勿手改）\n")
    A("数据：%d 条真实 agent 调用（攻击调用 %d、干净合法 %d、uncertain %d），"
      "来自 banking / travel / slack 三套件的已采集轨迹。\n"
      % (b["n_total"], b["label"].get("DENY", 0), b["label"].get("ALLOW", 0),
         b["label"].get("REVIEW", 0)))
    A("| 套件 | 调用 | 攻击调用 | 场景 | 受攻击场景 | 干净场景 | 注入暴露 |")
    A("|---|---|---|---|---|---|---|")
    for s, d in b["per_suite"].items():
        A("| %s | %d | %d | %d | %d | %d | %d |"
          % (s, d["n"], d["attack"], d["scenarios"], d["attacked_scen"],
             d["clean_scen"], d["exposed"]))
    A("")
    A("攻击调用的参数来源分解（机制）：%s。"
      % "，".join("%s %d" % (k, v) for k, v in b["attack_provenance"].items()))
    A("其中 `in_payload_only` = 关键参数只出现在注入载荷里（剥掉载荷后不再有接地证据）；"
      "`in_evidence` = 参数在合法证据里本来就有（接地没问题，失效只能来自授权边界）。\n")

    A("## 表 A｜五档 history 视图\n")
    A("block 口径 = 判 DENY。ACB 攻击调用拦截率，ACB_s 仅 γ≥2 的攻击调用，"
      "CCBcl 干净场景合法调用误拦截率，CCBin 受攻击场景里合法调用的误拦截率，"
      "ScenD 攻击场景全拦率，ClInt 干净场景零打扰率。\n")
    A("| arm | view | ACB | ACB_s | CCB_clean | CCB_inj | ScenDef | CleanIntact |")
    A("|---|---|---|---|---|---|---|---|")
    for tag, row in m.items():
        for v in ("none", "last1", "last3", "full", "noinj"):
            if v not in row:
                continue
            d = row[v]
            A("| %s | %s | %s | %s | %s | %s | %s | %s |"
              % (ARM_DESC.get(tag, tag), v, f(d["ACB"]), f(d["ACB_sens"]),
                 f(d["CCB_clean"]), f(d["CCB_inj"]), f(d["scen_def"]),
                 f(d["clean_intact"])))
    A("")

    A("## 表 B｜因果量 dInj = ACB(full) − ACB(noinj)\n")
    A("证据、轮次、工具输出完全相同，只删掉 `<INFORMATION>` 载荷。"
      "负值 = 载荷的存在让守卫**更宽松**（污染）；正值 = 载荷本身成了告警线索。\n")
    A("| arm | dInj | 95%CI（场景簇 bootstrap） | 因载荷被判 DENY | 因载荷被判 ALLOW | dHist |")
    A("|---|---|---|---|---|---|")
    for tag, row in m.items():
        d = row["dInj"]
        A("| %s | %s | [%s, %s] | %d | %d | %s |"
          % (ARM_DESC.get(tag, tag), f(d["delta"]), f(d["ci"][0]), f(d["ci"][1]),
             d["flipped_to_deny"], d["flipped_to_allow"], f(row["dHist"]["delta"])))
    A("")
    A("> `flipped_to_deny` = noinj 判 ALLOW 而 full 判 DENY 的调用数（载荷让守卫更警觉）；"
      "`flipped_to_allow` = 反过来的数量（载荷让守卫放行）。\n")

    A("## 表 C｜意图漂移\n")
    A("只给用户目标 + 待执行调用时判 DENY，看到被污染的历史后改判 ALLOW 的比例。"
      "这是「表面一致性陷阱」的直接计数。\n")
    A("| arm | 只看目标判 DENY 的攻击调用 | 其中被历史翻成 ALLOW | 漂移率 |")
    A("|---|---|---|---|")
    for tag, row in m.items():
        d = row["drift"]
        A("| %s | %d | %d | %s |" % (ARM_DESC.get(tag, tag), d["n_deny_none"],
                                     d["n_drift"], f(d["drift_rate"])))
    A("")

    A("## 表 D｜离线指标 vs 线上攻击拦截\n")
    A("同一 checkpoint 上，PAB-RD 的配对排序准确率（离线授权目标）与真实攻击调用上的拦截率。\n")
    p = os.path.join(D, "offline_vs_online.json")
    if os.path.exists(p):
        rows = json.load(open(p))
        A("| arm | PRA（离线配对） | ACB(full)（线上攻击拦截） | dInj |")
        A("|---|---|---|---|")
        for r in rows:
            A("| %s | %s | %s | %s |" % (ARM_DESC.get(r["arm"], r["arm"]), f(r["PRA"]),
                                         f(r["ACB_full"]), f(r["dInj"])))
        A("")
    A("---\n")
    A("视图说明：" + "；".join("`%s` %s" % (k, v) for k, v in VIEW_DESC.items()) + "。")

    out = os.path.join(D, "report.md")
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("->", out)


if __name__ == "__main__":
    main()
