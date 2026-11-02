# -*- coding: utf-8 -*-
"""P1 的聚类推断（与 P0 同一套方法，换数据）

复用 `scripts/final_stats.py` 的 cluster_boot / cluster_perm / sign_test / pair_value /
build_pairs，保证"动作整组重采样 + 整组翻符号"的实现与 P0 逐字相同。

三层结果
--------
1. 逐 seed：每个 seed 单独算 ΔPRA / ΔSPA 的聚类 CI、聚类置换 p、配对符号检验（辅助）、设计效应。
2. 跨 seed 汇总（主）：把同一配对的 Δ 在 3 个 seed 上取平均，再做聚类推断。
3. ΔMacro-F1：按 **task 组**（25 个任务）重采样给 CI（Macro-F1 不是配对比较，不做置换）。

输出：results/p1/p1_infer.json、reports/p1_infer.md（供论文 §5.3 引用）
"""
import collections
import json
import os
import sys

import numpy as np

ROOT = "/data/projects/guardrails"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import final_stats as FS  # noqa: E402

P1 = os.path.join(ROOT, "results", "p1", "preds")
OUTJ = os.path.join(ROOT, "results", "p1", "p1_infer.json")
OUTM = os.path.join(ROOT, "reports", "p1_infer.md")
SEEDS = [0, 42, 123]
MODELS = [("15b", "1.5B"), ("3b", "3B")]
LABELS = ["ALLOW", "REVIEW", "DENY"]


def load(tag, arm):
    fn = os.path.join(P1, "%s_%s.jsonl" % (tag, arm))
    out = {}
    for line in open(fn, encoding="utf-8"):
        r = json.loads(line)
        out[r["sid"]] = {"pred": r["pred"]}
    return out


def rows_of(tag, arm):
    fn = os.path.join(P1, "%s_%s.jsonl" % (tag, arm))
    rs = [json.loads(l) for l in open(fn, encoding="utf-8")]
    return [{"sid": r["sid"], "current_action": r["action"], "label": r["gold"]} for r in rs]


L2I = {L: i for i, L in enumerate(LABELS)}


def macro_f1_fast(gi, pi):
    """向量化 macro-F1：gi/pi 是 0..2 的整数标签数组。"""
    cm = np.bincount(gi * 3 + pi, minlength=9).reshape(3, 3)
    tp = np.diag(cm).astype(float)
    fp = cm.sum(0) - tp
    fn = cm.sum(1) - tp
    den = 2 * tp + fp + fn
    f1 = np.where(den > 0, 2 * tp / np.maximum(den, 1e-12), 0.0)
    return float(f1.mean())


def infer(dpra, dspa, aids):
    out = {}
    for tag, vals in (("PRA", dpra), ("SPA", dspa)):
        v = np.asarray(vals, dtype=float)
        lo, hi, design, ng = FS.cluster_boot(aids, vals)
        ps, w, l, t = FS.sign_test(vals)
        am, _ = FS.action_means(aids, vals)
        tt, tp = FS.action_t_test(am)
        out[tag] = {"delta": float(v.mean()), "ci": [float(lo), float(hi)],
                    "p_cluster_perm": float(FS.cluster_perm(aids, vals)),
                    "design_effect": design, "n_groups": ng,
                    "p_pair_sign_aux": float(ps), "pairs_better": w, "pairs_worse": l,
                    "pairs_nodraw": t, "p_action_t": float(tp),
                    "actions_better": int((am > 1e-9).sum()),
                    "actions_worse": int((am < -1e-9).sum())}
    return out


def main():
    # sid → task_id（供 Macro-F1 的 task 组重采样）
    task_of = {}
    for line in open(os.path.join(ROOT, "data", "pab_rd.jsonl"), encoding="utf-8"):
        d = json.loads(line)
        task_of[d["sid"]] = d["task_id"]

    res = {"seeds": SEEDS, "models": {}, "n_perm": FS.N_PERM, "n_boot": FS.N_BOOT}
    for mk, mn in MODELS:
        base_rows = rows_of("p1_%s_task_l2_s0" % mk, "task")
        pairs = FS.build_pairs(base_rows)
        aids = [p["aid"] for p in pairs]
        sids = [r["sid"] for r in base_rows]
        gold = [r["label"] for r in base_rows]
        m = {"n_pairs": len(pairs), "n_actions": len(set(aids)), "per_seed": {},
             "pooled": {}, "macro_f1": {}}

        per_seed_dp, per_seed_ds = [], []
        for s in SEEDS:
            tag = "p1_%s_%s_l2_s%d" % (mk, "task", s)
            a = load(tag, "task")
            b = load("p1_%s_nt_l2_s%d" % (mk, s), "nt")
            dpra = [FS.pair_value(a, b, pr, strict=False) for pr in pairs]
            dspa = [FS.pair_value(a, b, pr, strict=True) for pr in pairs]
            per_seed_dp.append(dpra)
            per_seed_ds.append(dspa)
            m["per_seed"]["s%d" % s] = infer(dpra, dspa, aids)

        # 跨 seed 汇总：同一配对的 Δ 先平均，再做聚类推断
        pooled_p = list(np.mean(np.asarray(per_seed_dp), axis=0))
        pooled_s = list(np.mean(np.asarray(per_seed_ds), axis=0))
        m["pooled"] = infer(pooled_p, pooled_s, aids)

        # ΔMacro-F1：task 组（25）重采样（向量化）
        task_idx = collections.defaultdict(list)
        for i, sid in enumerate(sids):
            task_idx[task_of[sid]].append(i)
        keys = sorted(task_idx)
        gi_all = np.array([L2I[g] for g in gold])
        preds_a, preds_b = [], []
        for s in SEEDS:
            a = load("p1_%s_task_l2_s%d" % (mk, s), "task")
            b = load("p1_%s_nt_l2_s%d" % (mk, s), "nt")
            preds_a.append(np.array([L2I[a[sid]["pred"]] for sid in sids]))
            preds_b.append(np.array([L2I[b[sid]["pred"]] for sid in sids]))
        deltas = [macro_f1_fast(gi_all, preds_a[i]) - macro_f1_fast(gi_all, preds_b[i])
                  for i in range(len(SEEDS))]
        rng = np.random.default_rng(FS.SEED)
        boot = np.empty(FS.N_BOOT)
        for k in range(FS.N_BOOT):
            pick = rng.integers(0, len(keys), len(keys))
            idx = np.concatenate([task_idx[keys[i]] for i in pick])
            gg = gi_all[idx]
            boot[k] = np.mean([macro_f1_fast(gg, preds_a[i][idx])
                               - macro_f1_fast(gg, preds_b[i][idx])
                               for i in range(len(SEEDS))])
        m["macro_f1"] = {"delta_per_seed": [float(x) for x in deltas],
                         "delta_mean": float(np.mean(deltas)),
                         "ci_task_cluster": [float(np.percentile(boot, 2.5)),
                                             float(np.percentile(boot, 97.5))],
                         "n_task_groups": len(keys)}
        res["models"][mk] = m

    os.makedirs(os.path.dirname(OUTJ), exist_ok=True)
    json.dump(res, open(OUTJ, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(OUTM, "w", encoding="utf-8").write(render(res))
    print("写出 %s\n写出 %s" % (OUTM, OUTJ))
    for mk, mn in MODELS:
        p = res["models"][mk]["pooled"]
        print("%s  ΔPRA=%+.3f CI=[%+.3f,%+.3f] p_perm=%.4f | ΔSPA=%+.3f p_perm=%.4f"
              % (mn, p["PRA"]["delta"], p["PRA"]["ci"][0], p["PRA"]["ci"][1],
                 p["PRA"]["p_cluster_perm"], p["SPA"]["delta"], p["SPA"]["p_cluster_perm"]))


def render(res):
    L = []
    A = L.append
    A("# P1 聚类推断（动作整组重采样 / 整组翻符号）\n")
    A("方法沿用 `scripts/final_stats.py`（%d 次 bootstrap，%d 次置换），只替换数据为 P1 的 "
      "12 份预测。Δ = task − no-task，正值为「带请求更好」。\n" % (res["n_boot"], res["n_perm"]))
    A("## 逐 seed\n")
    A("| 模型 | seed | ΔPRA | 95% CI | p(聚类置换) | p(配对符号, 辅助) | ΔSPA | p(聚类置换) | 设计效应 |")
    A("|---|---|---|---|---|---|---|---|---|")
    for mk, mn in MODELS:
        for s in SEEDS:
            d = res["models"][mk]["per_seed"]["s%d" % s]
            A("| %s | %d | %+.3f | [%+.3f, %+.3f] | %.4f | %.4f | %+.3f | %.4f | %.2f |"
              % (mn, s, d["PRA"]["delta"], d["PRA"]["ci"][0], d["PRA"]["ci"][1],
                 d["PRA"]["p_cluster_perm"], d["PRA"]["p_pair_sign_aux"],
                 d["SPA"]["delta"], d["SPA"]["p_cluster_perm"], d["PRA"]["design_effect"]))
    A("\n## 跨 seed 汇总（同一配对先平均，再做聚类推断）\n")
    A("| 模型 | ΔPRA | 95% CI | p(聚类置换) | p(配对符号, 辅助) | 优于/劣于/持平 | ΔSPA | 95% CI | p(聚类置换) | 设计效应 |")
    A("|---|---|---|---|---|---|---|---|---|---|")
    for mk, mn in MODELS:
        p = res["models"][mk]["pooled"]
        A("| %s | %+.3f | [%+.3f, %+.3f] | %.4f | %.4f | %d/%d/%d | %+.3f | [%+.3f, %+.3f] | %.4f | %.2f |"
          % (mn, p["PRA"]["delta"], p["PRA"]["ci"][0], p["PRA"]["ci"][1],
             p["PRA"]["p_cluster_perm"], p["PRA"]["p_pair_sign_aux"],
             p["PRA"]["pairs_better"], p["PRA"]["pairs_worse"], p["PRA"]["pairs_nodraw"],
             p["SPA"]["delta"], p["SPA"]["ci"][0], p["SPA"]["ci"][1],
             p["SPA"]["p_cluster_perm"], p["PRA"]["design_effect"]))
    A("\n## ΔMacro-F1（按 25 个 task 组重采样）\n")
    A("| 模型 | ΔMacro-F1 逐 seed | 均值 | 95% CI (task cluster) |")
    A("|---|---|---|---|")
    for mk, mn in MODELS:
        d = res["models"][mk]["macro_f1"]
        A("| %s | %s | %+.4f | [%+.4f, %+.4f] |"
          % (mn, " / ".join("%+.4f" % x for x in d["delta_per_seed"]), d["delta_mean"],
             d["ci_task_cluster"][0], d["ci_task_cluster"][1]))
    A("\n## 口径\n")
    A("- 配对单位与 §5.1 相同：按 `current_action` 分组，组内 ALLOW × 非 ALLOW；90 个配对、47 个动作组。")
    A("- 聚类置换：零假设下每个动作组的方向可交换，**整组**翻符号（保留组内相关）。")
    A("- 配对符号检验：把 90 个配对当独立投票，与聚类口径冲突，仅作连续性对照。")
    A("- 设计效应 = 聚类 bootstrap 方差 / i.i.d. 方差；>1 表示有效样本小于名义 90。")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
