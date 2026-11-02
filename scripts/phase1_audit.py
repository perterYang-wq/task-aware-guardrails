# -*- coding: utf-8 -*-
"""阶段 1：数据审计（只读）。

产出 runs/dataset_audit/audit.json + audit.md 的数据部分。

审计对象：
  results/diag/steps.jsonl      诊断集（P1/M2 冻结）
  runs/ad_bank2_trace.jsonl     历史 banking 调用级 trace（377）
  runs/ad_ws2_trace.jsonl       历史 workspace 调用级 trace（643）
  results/ad_v3/*/scen_*.jsonl  端到端轨迹（含环境状态）

要回答：
  1. 规模 / 类别分布 / 攻击覆盖面 / 缺失字段
  2. 标签与行为是否一致（攻击调用是否真的带攻击特征）
  3. 重复与近重复
  4. 训练集与测试集的场景级重叠（泄漏）
  5. 日志能否证明"调用被执行 / 环境被改变"
"""
import hashlib
import json
import os
from collections import Counter, defaultdict

R = "/data/projects/guardrails"
OUT = os.path.join(R, "runs/dataset_audit")
os.makedirs(OUT, exist_ok=True)


def J(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def norm(s):
    return (s or "").strip().lower()


def sig(r):
    """近重复指纹：工具 + 归一化参数 + 归一化当前动作。"""
    return hashlib.md5(("%s|%s|%s" % (r.get("tool"), json.dumps(r.get("args") or {},
                                                               sort_keys=True),
                                      norm(r.get("current_action"))[:120])).encode()).hexdigest()


def main():
    A = {}

    # ---------------- 1. 诊断集 ----------------
    steps = J(os.path.join(R, "results/diag/steps.jsonl"))
    A["diag"] = dict(
        n=len(steps), fields=sorted(steps[0].keys()),
        suites=dict(Counter(s["suite"] for s in steps)),
        labels=dict(Counter(s["label"] for s in steps)),
        provenance=dict(Counter(s["provenance"] for s in steps)),
        attack_scen=len({s["scenario_id"] for s in steps if s["label"] == "DENY"}),
        all_scen=len({s["scenario_id"] for s in steps}),
        tasks=len({(s["suite"], s["task_id"]) for s in steps}),
        missing={k: sum(1 for s in steps if s.get(k) in (None, "", [], {}))
                 for k in ("instruction", "history", "current_action", "tool", "args")},
        views=dict(has_noinj=sum(1 for s in steps if s.get("hist_noinj")),
                   noinj_differs=sum(1 for s in steps
                                     if s.get("hist_noinj") != s.get("hist_full"))),
    )

    # 标签一致性：DENY 的调用应当来自受攻击场景且参数有可辨识来源
    den = [s for s in steps if s["label"] == "DENY"]
    A["label_consistency"] = dict(
        deny_total=len(den),
        deny_in_attacked_scen=sum(1 for s in den if s.get("in_attacked_scenario")),
        deny_with_inj_payload=sum(1 for s in den
                                  if "<INFORMATION>" in (s.get("hist_full") or "")),
        allow_in_attacked_scen=sum(1 for s in steps if s["label"] == "ALLOW"
                                   and s.get("in_attacked_scenario")),
        note="DENY 全部应落在受攻击场景；ALLOW 在受攻击场景内也应存在（合法调用）",
    )

    # ---------------- 2. 重复 / 近重复 ----------------
    sigs = Counter(sig(s) for s in steps)
    dup = {k: v for k, v in sigs.items() if v > 1}
    by_label = defaultdict(Counter)
    for s in steps:
        by_label[s["label"]][sig(s)] += 1
    cross = 0
    for sg, c in dup.items():
        labs = {l for l, cc in by_label.items() if cc.get(sg)}
        if len(labs) > 1:
            cross += 1
    A["duplicates"] = dict(unique_sig=len(sigs), dup_sig=len(dup),
                           dup_rows=sum(v - 1 for v in dup.values()),
                           cross_label_dup=cross)

    # ---------------- 3. 训练/测试场景重叠（泄漏） ----------------
    hn = J(os.path.join(R, "data/hardneg_bal.jsonl"))
    hn_tasks = {(x["meta"].get("suite"), x["meta"].get("task_id")) for x in hn
                if x.get("meta")}
    hn_inj = {x["meta"].get("injection_task") for x in hn if x.get("meta")}
    diag_tasks = {(s["suite"], s["task_id"]) for s in steps}
    diag_atk_tasks = {(s["suite"], s["task_id"]) for s in steps if s["label"] == "DENY"}
    A["leakage"] = dict(
        hardneg_rows=len(hn),
        hardneg_tasks=len(hn_tasks),
        hardneg_injection_tasks=sorted(x for x in hn_inj if x),
        diag_tasks=len(diag_tasks),
        overlap_all=sorted("%s/%s" % t for t in (hn_tasks & diag_tasks)),
        overlap_attack=sorted("%s/%s" % t for t in (hn_tasks & diag_atk_tasks)),
        note="重叠 ≠ 泄漏：训练用的是调用级标签，但同一 task 出现在两侧会抬高 in-dist 分数",
    )
    pab = J(os.path.join(R, "data/pab_rd.jsonl"))
    A["leakage"]["pab_rows"] = len(pab)
    A["leakage"]["pab_tasks"] = len({(x["meta"].get("suite"), x["meta"].get("task_id"))
                                     for x in pab if x.get("meta")})

    # ---------------- 4. 历史 trace ----------------
    legacy = {}
    for key in ("runs/ad_bank2_trace.jsonl", "runs/ad_ws2_trace.jsonl"):
        rows = J(os.path.join(R, key))
        legacy[key] = dict(
            calls=len(rows),
            scenarios=len({(r["user_task"], r["injection_task"]) for r in rows}),
            tasks=len({r["user_task"] for r in rows}),
            injection_tasks=len({r["injection_task"] for r in rows if r["injection_task"]}),
            fields=sorted(rows[0].keys()),
            has_env_state=any(k in rows[0] for k in ("security", "utility", "executed")),
            missing={k: sum(1 for r in rows if r.get(k) in (None, "", [], {}))
                     for k in ("instruction", "history", "current_action", "tool", "args")},
        )
    A["legacy_traces"] = legacy

    # ---------------- 5. 端到端轨迹（含环境状态） ----------------
    e2e = {}
    for suite in ("slack", "travel", "banking"):
        p = os.path.join(R, "results/ad_v3", suite, "scen_merged.jsonl")
        if not os.path.isfile(p):
            e2e[suite] = dict(exists=False)
            continue
        rows = J(p)
        atk = [r for r in rows if r.get("injection_present")]
        cl = [r for r in rows if not r.get("injection_present")]
        e2e[suite] = dict(
            exists=True, n=len(rows), clean=len(cl), attack=len(atk),
            utility_clean=round(sum(1 for r in cl if r.get("utility")) / max(1, len(cl)), 4),
            asr=round(sum(1 for r in atk if r.get("security")) / max(1, len(atk)), 4),
            inj_tasks=sorted({r.get("injection_task") for r in atk}),
            fields=sorted(rows[0].keys()),
            has_env_state=all(k in rows[0] for k in ("security", "utility")),
        )
    A["e2e_traces"] = e2e

    # ---------------- 6. 场景清单 ----------------
    manifest = []
    seen = set()
    for s in steps:
        k = (s["suite"], s["task_id"], s.get("injection_task"), s["scenario_id"])
        if k in seen:
            continue
        seen.add(k)
        manifest.append(dict(suite=s["suite"], task=s["task_id"],
                             injection_task=s.get("injection_task"),
                             scenario_id=s["scenario_id"],
                             n_calls=sum(1 for x in steps if x["scenario_id"] == s["scenario_id"]),
                             n_attack_calls=sum(1 for x in steps if x["scenario_id"] == s["scenario_id"]
                                                and x["label"] == "DENY")))
    with open(os.path.join(OUT, "scenario_manifest.jsonl"), "w", encoding="utf-8") as f:
        for r in sorted(manifest, key=lambda x: (x["suite"], x["task"] or "", str(x["injection_task"]))):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    A["scenario_manifest"] = dict(path="runs/dataset_audit/scenario_manifest.jsonl",
                                  rows=len(manifest))

    json.dump(A, open(os.path.join(OUT, "audit.json"), "w"), ensure_ascii=False, indent=2)

    # ---------------- 打印 ----------------
    d = A["diag"]
    print("diag: %d calls | clean %d / attack %d | suites %s"
          % (d["n"], d["labels"].get("ALLOW", 0), d["labels"].get("DENY", 0), d["suites"]))
    print("      scenarios %d (atk %d) | tasks %d | noinj differs %d"
          % (d["all_scen"], d["attack_scen"], d["tasks"], d["views"]["noinj_differs"]))
    lc = A["label_consistency"]
    print("label: DENY %d 全在受攻击场景=%s | DENY 含载荷 %d | 受攻击场景内 ALLOW %d"
          % (lc["deny_total"], lc["deny_in_attacked_scen"] == lc["deny_total"],
             lc["deny_with_inj_payload"], lc["allow_in_attacked_scen"]))
    dp = A["duplicates"]
    print("dup: 唯一指纹 %d, 重复 %d, 多出 %d 行, 跨标签重复 %d"
          % (dp["unique_sig"], dp["dup_sig"], dp["dup_rows"], dp["cross_label_dup"]))
    lk = A["leakage"]
    print("leak: hardneg tasks %d, diag tasks %d, 交集 %d (攻击场景交集 %d)"
          % (lk["hardneg_tasks"], lk["diag_tasks"], len(lk["overlap_all"]),
             len(lk["overlap_attack"])))
    for k, v in A["legacy_traces"].items():
        print("%-28s calls=%d scen=%d env_state=%s" % (k, v["calls"], v["scenarios"],
                                                       v["has_env_state"]))
    for k, v in e2e.items():
        print("e2e %-8s exists=%s n=%s clean=%s attack=%s util=%s asr=%s"
              % (k, v["exists"], v.get("n"), v.get("clean"), v.get("attack"),
                 v.get("utility_clean"), v.get("asr")))
    print("-> runs/dataset_audit/{audit.json,scenario_manifest.jsonl}")


if __name__ == "__main__":
    main()
