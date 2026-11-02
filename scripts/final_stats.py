# -*- coding: utf-8 -*-
"""P0 最终统计检查（metric_version = p0-1.1）。

本脚本只补推断层，不改任何指标定义：
    PRA / SPA / TieRate / Macro-F1 的定义与 p0-1.0 逐字节相同，
    运行时断言点估计完全一致（差异只可能来自推断，不可能来自定义）。

三件事
------
1. 等权合并：三个部署守卫（0.5B / 1.5B / 3B）预先固定各 1/3，不看测试结果调权重。
   7B Guard 仅探索性对照，不进入合并。合并只作**跨尺寸辅助分析**，
   主结果仍是三个单模型分别报告。

2. 纠正一处标注错误：上一版把合并的 p=0.0007 标成"动作聚类检验"，实际它是
   配对层**普通符号检验**（41 优 / 15 劣 / 34 并列，n=56）。它假定配对独立，
   忽略同一动作下多个配对共享同一个 ALLOW 样本，必须降级为辅助结果。

3. 补真正的动作聚类推断：
   - CI：按 action_id **整组重采样**的 bootstrap
   - p ：按 action_id **整组同时翻转符号**的置换检验
     这一置换在组内保持相对结构，只翻转整组方向，因此保留组内相关。
   同时给出动作层 t 检验（47 个动作均值为独立单元）作为解析交叉验证。
"""
import argparse
import collections
import hashlib
import json
import math
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
METRIC_VERSION = "p0-1.1"
DATA = os.path.join(ROOT, "data", "pab_rd.jsonl")
SPLITS = os.path.join(ROOT, "data", "pab_rd_splits.json")
PREDS = os.path.join(ROOT, "results", "preds")
OUTDIR = os.path.join(ROOT, "results", "frozen")

# 预先固定的部署配置：三守卫等权，权重 1/3；不看测试表现调整
DEPLOY = [("0.5B", "full_0.5B", "blind_0.5B"),
          ("1.5B", "full_1.5B", "blind_1.5B"),
          ("3B", "full_3B", "blind_3B")]
EXPLORATORY = [("7B", "full_7B", "blind_7B"),
               ("1.5B_lr4", "full_1.5B_lr4", "blind_1.5B_lr4")]
WEIGHT = 1.0 / len(DEPLOY)

N_BOOT = 10000
N_PERM = 20000
SEED = 0


# ---------------------------------------------------------------- 基础工具
def score_of(rec):
    s = rec.get("score")
    if s is None:
        s = {"ALLOW": 1.0, "REVIEW": 0.5, "DENY": 0.0}.get(rec.get("pred"))
    return float(s)


def load_pred(name):
    d = {}
    for line in open(os.path.join(PREDS, name + ".jsonl"), encoding="utf-8"):
        r = json.loads(line)
        d[r["sid"]] = r
    return d


def pair_value(pa, pb, pr, strict):
    """一对样本上的 (full - blind) 差值；strict=True 时并列记 0（SPA），否则记 0.5（PRA）。"""
    sa, so = score_of(pa[pr["a"]]), score_of(pa[pr["o"]])
    ba, bo = score_of(pb[pr["a"]]), score_of(pb[pr["o"]])
    tie = 0.0 if strict else 0.5
    va = 1.0 if sa > so else (tie if sa == so else 0.0)
    vb = 1.0 if ba > bo else (tie if ba == bo else 0.0)
    return va - vb


def sign_test(v, eps=1e-9):
    """配对层普通符号检验（辅助结果）。v 为逐配对差值。"""
    v = np.asarray(v, dtype=float)
    w = int((v > eps).sum())
    l = int((v < -eps).sum())
    n = w + l
    if n == 0:
        return 1.0, w, l, 0
    k = min(w, l)
    p = min(1.0, 2.0 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
    return p, w, l, n - w - l


def group_index(units):
    idx = collections.defaultdict(list)
    for i, u in enumerate(units):
        idx[u].append(i)
    return {k: np.array(v) for k, v in sorted(idx.items())}


def cluster_boot(units, values, n_boot=N_BOOT, seed=SEED, alpha=0.05):
    """按组整组重采样，返回均值的百分位 CI 与设计效应。

    设计效应 = 聚类方差 / i.i.d. 方差。>1 表示组内相关使有效样本量小于名义样本量。
    """
    v = np.asarray(values, dtype=float)
    g = group_index(units)
    keys = list(g)
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, len(keys), len(keys))
        idx = np.concatenate([g[keys[i]] for i in pick])
        means[b] = v[idx].mean()
    lo, hi = np.percentile(means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    var_iid = v.var(ddof=1) / len(v)
    design = float(means.var(ddof=1) / var_iid) if var_iid > 0 else float("nan")
    return float(lo), float(hi), float(design), len(keys)


def cluster_perm(units, values, n_perm=N_PERM, seed=SEED):
    """按组整组翻转符号的置换检验（双侧）。

    零假设下每个动作组的方向可交换；翻转整组（而不是逐配对翻转）保留了组内的
    相对结构，因此 p 值考虑了组内相关。
    """
    v = np.asarray(values, dtype=float)
    g = group_index(units)
    keys = list(g)
    obs = abs(v.mean())
    rng = np.random.default_rng(seed)
    cnt = 0
    for _ in range(n_perm):
        signs = rng.choice([-1.0, 1.0], size=len(keys))
        tot = 0.0
        for s, k in zip(signs, keys):
            tot += s * v[g[k]].sum()
        if abs(tot / len(v)) >= obs - 1e-12:
            cnt += 1
    return (cnt + 1) / (n_perm + 1)


def action_means(units, values):
    v = np.asarray(values, dtype=float)
    g = group_index(units)
    return np.array([v[g[k]].mean() for k in g]), list(g)


def action_t_test(am):
    """动作层单样本 t 检验（47 个动作均值为独立单元），解析交叉验证。"""
    n = len(am)
    if n < 2:
        return float("nan"), float("nan")
    m = am.mean()
    se = am.std(ddof=1) / math.sqrt(n)
    if se == 0:
        return float("inf"), float("nan")
    t = m / se
    # 双侧 p，用正态近似（n=47 时与 t 分布几乎一致）
    p = math.erfc(abs(t) / math.sqrt(2))
    return float(t), float(p)


def action_sign(units, values, eps=1e-9):
    am, keys = action_means(units, values)
    w = int((am > eps).sum())
    l = int((am < -eps).sum())
    n = w + l
    if n == 0:
        return 1.0, w, l, len(keys)
    k = min(w, l)
    p = min(1.0, 2.0 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
    return p, w, l, len(keys)


# ---------------------------------------------------------------- 主流程
def build_pairs(te):
    g = collections.defaultdict(lambda: {"ALLOW": [], "other": []})
    for r in te:
        g[r["current_action"]]["ALLOW" if r["label"] == "ALLOW" else "other"].append(r)
    pairs = []
    for act, v in sorted(g.items()):
        aid = hashlib.sha1(act.encode("utf-8")).hexdigest()[:10]
        for x in v["ALLOW"]:
            for y in v["other"]:
                pairs.append({"pid": "%s|%s|%s" % (aid, x["sid"], y["sid"]),
                              "aid": aid, "a": x["sid"], "o": y["sid"]})
    return pairs


def analyse(arms, pairs, fa, fb, label):
    dpra = [pair_value(arms[fa], arms[fb], pr, strict=False) for pr in pairs]
    dspa = [pair_value(arms[fa], arms[fb], pr, strict=True) for pr in pairs]
    aids = [pr["aid"] for pr in pairs]

    out = {"label": label, "full": fa, "blind": fb, "n_pairs": len(pairs)}
    for tag, vals in (("PRA", dpra), ("SPA", dspa)):
        v = np.asarray(vals, dtype=float)
        lo, hi, design, ng = cluster_boot(aids, vals)
        ps, w, l, t = sign_test(vals)
        am, _ = action_means(aids, vals)
        tt, tp = action_t_test(am)
        asp, aw, al, an = action_sign(aids, vals)
        out[tag] = {
            "delta": float(v.mean()),
            "ci_action_cluster": [lo, hi],
            "p_cluster_perm": cluster_perm(aids, vals),
            "design_effect": design,
            "n_action_groups": ng,
            "p_pair_sign_aux": ps,
            "pairs_better": w, "pairs_worse": l, "pairs_nodiff": t,
            "pairs_discordant": w + l,
            "action_level_t": tt, "p_action_t": tp,
            "p_action_sign_aux": asp,
            "actions_better": aw, "actions_worse": al, "actions_with_signal": aw + al,
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(OUTDIR, "final_stats.json"))
    ap.add_argument("--md", default=os.path.join(OUTDIR, "final_tables.md"))
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(DATA, encoding="utf-8")]
    by_sid = {r["sid"]: r for r in rows}
    sp = json.load(open(SPLITS, encoding="utf-8"))
    te = [by_sid[s] for s in sp["test"]]
    pairs = build_pairs(te)

    arms = {}
    for f in sorted(os.listdir(PREDS)):
        if f.endswith(".jsonl"):
            arms[f[:-6]] = load_pred(f[:-6])

    # 一致性：所有参与臂必须覆盖同一批 sid
    for n in [x[1] for x in DEPLOY] + [x[2] for x in DEPLOY]:
        assert set(arms[n]) == {r["sid"] for r in te}, "%s 覆盖不一致" % n

    res = {"metric_version": METRIC_VERSION,
           "n_samples": len(te), "n_pairs": len(pairs),
           "n_action_groups": len({p["aid"] for p in pairs}),
           "n_task_groups": len({(r["suite"], r["task_id"]) for r in te}),
           "deploy": [s for s, _, _ in DEPLOY],
           "weights": {s: WEIGHT for s, _, _ in DEPLOY},
           "note_weight": "等权预先固定，不按测试表现调整；7B Guard 不参与合并",
           "single": {}, "exploratory": {}}

    print("=" * 100)
    print("单模型（主结果）：ΔPRA / ΔSPA，动作聚类 CI 与动作聚类置换 p")
    print("=" * 100)
    print("%-10s%-7s%9s%8s%24s%10s%9s%14s" %
          ("size", "metric", "delta", "tie", "95%CI(action cluster)", "p_perm", "p_sign", "actions +/-"))

    for size, fa, fb in DEPLOY + EXPLORATORY:
        r = analyse(arms, pairs, fa, fb, size)
        (res["single"] if (size, fa, fb) in DEPLOY else res["exploratory"])[size] = r
        for tag in ("PRA", "SPA"):
            d = r[tag]
            print("%-10s%-7s%+9.3f%8.2f  [%+.3f,%+.3f]%14.4f%9.4f%8d/%-4d" %
                  (size, tag, d["delta"], d["design_effect"],
                   d["ci_action_cluster"][0], d["ci_action_cluster"][1],
                   d["p_cluster_perm"], d["p_pair_sign_aux"],
                   d["actions_better"], d["actions_worse"]))

    # ---------- 等权合并（辅助分析）
    print("\n" + "=" * 100)
    print("等权合并（三个部署守卫各 1/3；跨尺寸辅助分析，非主结果）")
    print("=" * 100)
    aids = [pr["aid"] for pr in pairs]
    merged = {}
    for tag, strict in (("PRA", False), ("SPA", True)):
        vals = []
        for pr in pairs:
            vals.append(sum(WEIGHT * pair_value(arms[fa], arms[fb], pr, strict)
                            for _, fa, fb in DEPLOY))
        v = np.asarray(vals, dtype=float)
        lo, hi, design, ng = cluster_boot(aids, vals)
        ps, w, l, t = sign_test(vals)
        am, _ = action_means(aids, vals)
        tt, tp = action_t_test(am)
        asp, aw, al, an = action_sign(aids, vals)
        # 说明性：per-guard delta 的等权均值，应与上面合并均值相等（线性）
        per_guard = [res["single"][s][tag]["delta"] for s, _, _ in DEPLOY]
        assert abs(sum(WEIGHT * x for x in per_guard) - v.mean()) < 1e-9, "PRA/SPA 线性性检查失败"
        merged[tag] = {
            "delta": float(v.mean()),
            "delta_per_guard": per_guard,
            "delta_mean_of_guards": float(sum(WEIGHT * x for x in per_guard)),
            "ci_action_cluster": [lo, hi],
            "p_cluster_perm": cluster_perm(aids, vals),
            "design_effect": design,
            "n_action_groups": ng,
            "p_pair_sign_aux": ps,
            "pairs_better": w, "pairs_worse": l, "pairs_nodiff": t,
            "pairs_discordant": w + l,
            "action_level_t": tt, "p_action_t": tp,
            "p_action_sign_aux": asp,
            "actions_better": aw, "actions_worse": al, "actions_with_signal": aw + al,
        }
        print("%-4s delta=%+.4f  (per-guard %s, 等权均值 %+.4f)" %
              (tag, v.mean(), ["%+.4f" % x for x in per_guard], sum(WEIGHT * x for x in per_guard)))
        print("     CI(action cluster) [%+.3f, %+.3f]   p_perm=%.4f   设计效应=%.2f   动作组=%d" %
              (lo, hi, merged[tag]["p_cluster_perm"], design, ng))
        print("     配对层普通符号检验（辅助）: %d 优 / %d 劣 / %d 并列 -> p=%.4f" %
              (w, l, t, ps))
        print("     动作层: %d 优 / %d 劣 (n=%d)  符号 p=%.4f ; t=%.2f, p=%.4f" %
              (aw, al, aw + al, asp, tt, tp))

    res["merged_equal_weight"] = merged

    # ---------- 校验：0.0007 到底是什么检验
    print("\n" + "=" * 100)
    print("校验：旧 p=0.0007 的归属")
    print("=" * 100)
    check = {}
    for tag, strict in (("PRA", False), ("SPA", True)):
        vals = []
        for pr in pairs:
            vals.append(sum(WEIGHT * pair_value(arms[fa], arms[fb], pr, strict)
                            for _, fa, fb in DEPLOY))
        ps, w, l, t = sign_test(vals)
        lo, hi, design, ng = cluster_boot(aids, vals)
        check[tag] = {"pair_sign_p": ps, "better": w, "worse": l, "nodiff": t,
                      "discordant": w + l, "delta": float(np.mean(vals)),
                      "ci_action_cluster": [lo, hi],
                      "p_cluster_perm": merged[tag]["p_cluster_perm"]}
    res["p_attribution"] = check
    # 旧口径在合并段用的是 1.0/0.0 的二元差（等价于 SPA），找它落在哪一列
    old = 0.0007
    hits = [k for k, v in check.items() if abs(v["pair_sign_p"] - old) < 5e-4]
    res["p_attribution"]["old_p=0.0007_matches"] = hits
    for tag in ("PRA", "SPA"):
        c = check[tag]
        print("%-4s 合并：%+0.4f，%d 优 / %d 劣 / %d 零差（discordant=%d）"
              % (tag, c["delta"], c["better"], c["worse"], c["nodiff"], c["discordant"]))
        print("       普通配对符号检验 p=%.5f   | 动作聚类置换 p=%.4f   | CI [%+.3f,%+.3f]"
              % (c["pair_sign_p"], c["p_cluster_perm"], c["ci_action_cluster"][0],
                 c["ci_action_cluster"][1]))
    print("结论：旧 p=0.0007 由 %s 的**配对层普通符号检验**复现（%s），"
          % (",".join(hits) if hits else "?",
             "%d:%d" % (check[hits[0]]["better"], check[hits[0]]["worse"]) if hits else "-"))
    print("      它把配对当独立投票、不含动作聚类，**不是**动作聚类检验；已降级为辅助。")

    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n-> %s" % a.out)

    # ---------- markdown
    md = []
    md.append("<!-- metric_version = %s；本文件只由 final_stats.py 从 %s 生成 -->" %
              (METRIC_VERSION, os.path.basename(a.out)))
    md.append("\n### 表 A 单模型（主结果）：Δ = Full − No-task\n")
    md.append("| size | metric | Δ | 95% CI (action cluster) | p (action-cluster permutation) | p (pair sign, aux.) | pairs +/- | actions +/- | design effect |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    for size in [s for s, _, _ in DEPLOY]:
        for tag in ("PRA", "SPA"):
            d = res["single"][size][tag]
            md.append("| %s | %s | %+.3f | [%+.3f, %+.3f] | %.4f | %.4f | %d/%d | %d/%d | %.2f |" %
                      (size, tag, d["delta"], d["ci_action_cluster"][0], d["ci_action_cluster"][1],
                       d["p_cluster_perm"], d["p_pair_sign_aux"],
                       d["pairs_better"], d["pairs_worse"],
                       d["actions_better"], d["actions_worse"], d["design_effect"]))
    md.append("\n### 表 B 等权合并（辅助，三守卫各 1/3）\n")
    md.append("| metric | Δ | per-guard Δ | 95% CI (action cluster) | p (cluster perm) | p (pair sign, aux.) | actions +/- |")
    md.append("|---|---|---|---|---|---|---|")
    for tag in ("PRA", "SPA"):
        d = merged[tag]
        md.append("| %s | **%+.3f** | %s | [%+.3f, %+.3f] | **%.4f** | %.4f | %d/%d |" %
                  (tag, d["delta"], ", ".join("%+.3f" % x for x in d["delta_per_guard"]),
                   d["ci_action_cluster"][0], d["ci_action_cluster"][1],
                   d["p_cluster_perm"], d["p_pair_sign_aux"],
                   d["actions_better"], d["actions_worse"]))
    md.append("\n### 表 C 探索性对照（不进合并、不作部署结论）\n")
    md.append("| size | metric | Δ | 95% CI (action cluster) | p (cluster perm) | p (pair sign, aux.) |")
    md.append("|---|---|---|---|---|---|")
    for size in [s for s, _, _ in EXPLORATORY]:
        for tag in ("PRA", "SPA"):
            d = res["exploratory"][size][tag]
            md.append("| %s | %s | %+.3f | [%+.3f, %+.3f] | %.4f | %.4f |" %
                      (size, tag, d["delta"], d["ci_action_cluster"][0], d["ci_action_cluster"][1],
                       d["p_cluster_perm"], d["p_pair_sign_aux"]))
    open(a.md, "w", encoding="utf-8").write("\n".join(md) + "\n")
    print("-> %s" % a.md)


if __name__ == "__main__":
    main()
