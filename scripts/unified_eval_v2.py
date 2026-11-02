# -*- coding: utf-8 -*-
"""P0-2/3/4/5/6/7：冻结评测口径，metric_version = p0-1.0。

定义（写死，别处不得另立）
------------------------
对每对 (a, o)：a 为 ALLOW 成员，o 为同动作文本的非 ALLOW 成员。
    score ∈ [0,1]，越高越倾向 ALLOW。
    win   : s(a) > s(o)
    tie   : s(a) == s(o)
    loss  : s(a) < s(o)
    PRA   = (wins + 0.5*ties) / n
    SPA   = wins / n
    TieR  = ties / n
    恒等式 PRA = SPA + 0.5*TieR   （逐臂断言）

统计（回答"相关性"问题）
----------------------
同一动作文本下有多个配对（一个 ALLOW 对多个非 ALLOW），且多个配对共享同一个 ALLOW 样本，
因此配对之间**不独立**。所以：
    - ΔPRA / ΔSPA 的 CI 用 **按 action_id 分组的 bootstrap**（整组重采样）
    - ΔMacro-F1 的 CI 用 **按 task_id 分组的 bootstrap**
    - McNemar 仅作辅助（它假定配对独立，在这个结构下偏乐观），显式标注
合并四个模型时，同一 90 个配对在每个模型上被重复测量，360 个观测彼此相关，
**不能当作独立样本做 McNemar**；正确做法是在配对层面对模型取平均后再检验。
"""
import argparse
import collections
import hashlib
import json
import math
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
METRIC_VERSION = "p0-1.0"
DATA = os.path.join(ROOT, "data", "pab_rd.jsonl")
SPLITS = os.path.join(ROOT, "data", "pab_rd_splits.json")
PREDS = os.path.join(ROOT, "results", "preds")
OUTDIR = os.path.join(ROOT, "results", "frozen")

# 训练配置（来源：scripts/run_sizes.sh / run_7b.sh / run_lr_check.sh）
HPARAMS = {
    "full_0.5B": dict(base="/data/hf_cache/qwen0.5b", epochs=4, bs=8, accum=2, lr=2e-4),
    "blind_0.5B": dict(base="/data/hf_cache/qwen0.5b", epochs=4, bs=8, accum=2, lr=2e-4, no_task=True),
    "full_1.5B": dict(base="/data/hf_cache/qwen1.5b", epochs=4, bs=2, accum=8, lr=2e-4),
    "blind_1.5B": dict(base="/data/hf_cache/qwen1.5b", epochs=4, bs=2, accum=8, lr=2e-4, no_task=True),
    "full_3B": dict(base="/data/hf_cache/qwen3b", epochs=3, bs=4, accum=4, lr=2e-4),
    "blind_3B": dict(base="/data/hf_cache/qwen3b", epochs=3, bs=4, accum=4, lr=2e-4, no_task=True),
    "full_7B": dict(base="Qwen2.5-7B-Instruct", epochs=2, bs=1, accum=8, lr=2e-4, note="显存受限，探索性"),
    "blind_7B": dict(base="Qwen2.5-7B-Instruct", epochs=2, bs=1, accum=8, lr=2e-4, no_task=True),
    "full_1.5B_lr4": dict(base="/data/hf_cache/qwen1.5b", epochs=4, bs=2, accum=8, lr=1e-4),
    "blind_1.5B_lr4": dict(base="/data/hf_cache/qwen1.5b", epochs=4, bs=2, accum=8, lr=1e-4, no_task=True),
}
SEED = 0
ADAPTER = {
    "full_0.5B": "o1_rd_05b", "blind_0.5B": "o1_rd_05b_nt",
    "full_1.5B": "o1_rd_15b", "blind_1.5B": "o1_rd_15b_nt",
    "full_3B": "o1_rd_3b", "blind_3B": "o1_rd_3b_nt",
    "full_7B": "o1_rd_7b", "blind_7B": "o1_rd_7b_nt",
    "full_1.5B_lr4": "o1_rd_15b_lr4", "blind_1.5B_lr4": "o1_rd_15b_nt_lr4",
}
DEPLOY_PAIRS = [("0.5B", "full_0.5B", "blind_0.5B"),
                ("1.5B", "full_1.5B", "blind_1.5B"),
                ("3B", "full_3B", "blind_3B")]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def score_of(rec):
    s = rec.get("score")
    if s is None:
        s = {"ALLOW": 1.0, "REVIEW": 0.5, "DENY": 0.0}.get(rec.get("pred"))
    return float(s)


def load_pred(name):
    p = os.path.join(PREDS, name + ".jsonl")
    d = {}
    for line in open(p, encoding="utf-8"):
        r = json.loads(line)
        d[r["sid"]] = r
    return d


def macro_f1(gold, pred):
    f1s = []
    for c in ("ALLOW", "REVIEW", "DENY"):
        tp = sum(1 for g, p in zip(gold, pred) if g == c and p == c)
        fp = sum(1 for g, p in zip(gold, pred) if g != c and p == c)
        fn = sum(1 for g, p in zip(gold, pred) if g == c and p != c)
        P = tp / (tp + fp) if tp + fp else 0.0
        R = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * P * R / (P + R) if P + R else 0.0)
    acc = sum(1 for g, p in zip(gold, pred) if g == p) / len(gold)
    return sum(f1s) / 3, acc


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def sign_test(v, eps=1e-9):
    w = int((v > eps).sum())
    l = int((v < -eps).sum())
    n = w + l
    if n == 0:
        return 1.0, w, l
    k = min(w, l)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n), w, l


def group_boot(units, values, n_boot=4000, seed=0, alpha=0.05):
    """按 units（分组 id）整组重采样，返回均值的百分位 CI。"""
    idx = collections.defaultdict(list)
    for u, val in zip(units, values):
        idx[u].append(val)
    keys = sorted(idx)
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(keys), len(keys))
        pool = []
        for i in pick:
            pool.extend(idx[keys[i]])
        means.append(float(np.mean(pool)))
    lo, hi = np.percentile(means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(lo), float(hi), len(keys)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(OUTDIR, "unified_eval.json"))
    a = ap.parse_args()
    os.makedirs(OUTDIR, exist_ok=True)

    rows = {json.loads(l)["sid"]: json.loads(l)
            for l in open(DATA, encoding="utf-8")}
    sp = json.load(open(SPLITS))
    te = [rows[s] for s in sp["test"]]
    te_ids = [r["sid"] for r in te]

    # ---------- 配对：稳定 pair_id / action_id
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
    n_pairs = len(pairs)
    n_actions = len({p["aid"] for p in pairs})
    n_tasks = len({(r["suite"], r["task_id"]) for r in te})
    print("测试样本 %d，任务组 %d，配对 %d，动作组 %d"
          % (len(te), n_tasks, n_pairs, n_actions))

    # ---------- 一致性：所有臂必须覆盖同一批 sid
    arms = {}
    for f in sorted(os.listdir(PREDS)):
        if f.endswith(".jsonl"):
            arms[f[:-6]] = load_pred(f[:-6])
    for name, p in arms.items():
        miss = set(te_ids) - set(p)
        assert not miss, "%s 缺 %d 个测试 sid" % (name, len(miss))
    print("一致性检查：%d 个臂全部覆盖同一批 %d 个 sid，pair_id 集合唯一（由数据决定）"
          % (len(arms), len(te_ids)))

    # ---------- 逐臂指标
    res = {"metric_version": METRIC_VERSION,
           "dataset_hash": sha256(DATA), "split_hash": sha256(SPLITS),
           "pairs_hash": hashlib.sha1(
               "|".join(p["pid"] for p in pairs).encode()).hexdigest()[:16],
           "n_test": len(te), "n_pairs": n_pairs, "n_actions": n_actions,
           "n_tasks": n_tasks, "seed": SEED,
           "arms": {}, "deltas": [], "pooled": {}}

    for name, p in arms.items():
        w = t = l = 0
        for pr in pairs:
            sa, so = score_of(p[pr["a"]]), score_of(p[pr["o"]])
            if sa > so:
                w += 1
            elif sa == so:
                t += 1
            else:
                l += 1
        pra = (w + 0.5 * t) / n_pairs
        spa = w / n_pairs
        tie = t / n_pairs
        assert abs(pra - (spa + 0.5 * tie)) < 1e-12, "恒等式不成立: %s" % name
        f1, acc = macro_f1([rows[s]["label"] for s in te_ids],
                           [p[s].get("pred") for s in te_ids])
        res["arms"][name] = {
            "wins": w, "ties": t, "losses": l,
            "PRA": pra, "SPA": spa, "TieRate": tie,
            "macro_f1": f1, "acc": acc,
            "identity_ok": True,
            "hparams": HPARAMS.get(name),
            "checkpoint": ("guard/adapters/" + ADAPTER[name]) if name in ADAPTER else None,
        }

    # ---------- Full − No-task
    for size, fa, fb in DEPLOY_PAIRS + [("1.5B_lr4", "full_1.5B_lr4", "blind_1.5B_lr4"),
                                        ("7B", "full_7B", "blind_7B")]:
        if fa not in arms or fb not in arms:
            continue
        pa, pb = arms[fa], arms[fb]
        dpra, dspa, units = [], [], []
        b = c = 0
        for pr in pairs:
            sa, so = score_of(pa[pr["a"]]), score_of(pa[pr["o"]])
            ba, bo = score_of(pb[pr["a"]]), score_of(pb[pr["o"]])
            va = 1.0 if sa > so else (0.5 if sa == so else 0.0)
            vb = 1.0 if ba > bo else (0.5 if ba == bo else 0.0)
            dpra.append(va - vb)
            dspa.append((1.0 if sa > so else 0.0) - (1.0 if ba > bo else 0.0))
            if sa > so and not (ba > bo):
                b += 1
            elif ba > bo and not (sa > so):
                c += 1
            units.append(pr["aid"])
        lo_p, hi_p, k_act = group_boot(units, dpra)
        lo_s, hi_s, _ = group_boot(units, dspa)
        ps, win_p, lose_p = sign_test(np.array(dpra))

        # Macro-F1：按任务分组 bootstrap
        tasks = collections.defaultdict(list)
        for r in te:
            tasks[(r["suite"], r["task_id"])].append(r["sid"])
        tkeys = sorted(tasks)
        rng = np.random.default_rng(0)
        f1d = []
        for _ in range(2000):
            pick = rng.integers(0, len(tkeys), len(tkeys))
            sids = [s for i in pick for s in tasks[tkeys[i]]]
            g_ = [rows[s]["label"] for s in sids]
            ma, _ = macro_f1(g_, [pa[s].get("pred") for s in sids])
            mb, _ = macro_f1(g_, [pb[s].get("pred") for s in sids])
            f1d.append(ma - mb)
        lo_m, hi_m = np.percentile(f1d, [2.5, 97.5])

        res["deltas"].append({
            "size": size,
            "PRA": {"full": res["arms"][fa]["PRA"], "blind": res["arms"][fb]["PRA"],
                    "delta": float(np.mean(dpra)), "ci_action_boot": [lo_p, hi_p],
                    "p_sign": ps, "win": win_p, "lose": lose_p, "n_action_groups": k_act},
            "SPA": {"full": res["arms"][fa]["SPA"], "blind": res["arms"][fb]["SPA"],
                    "delta": float(np.mean(dspa)), "ci_action_boot": [lo_s, hi_s],
                    "mcnemar_aux": mcnemar(b, c), "strict_win": b, "strict_loss": c},
            "macro_f1": {"full": res["arms"][fa]["macro_f1"],
                         "blind": res["arms"][fb]["macro_f1"],
                         "delta": res["arms"][fa]["macro_f1"] - res["arms"][fb]["macro_f1"],
                         "ci_task_boot": [float(lo_m), float(hi_m)],
                         "n_task_groups": len(tkeys)},
        })

    # ---------- 合并：显式处理重复测量
    per_pair = []
    for pr in pairs:
        v = []
        for size, fa, fb in DEPLOY_PAIRS:
            pa, pb = arms[fa], arms[fb]
            va = 1.0 if score_of(pa[pr["a"]]) > score_of(pa[pr["o"]]) else 0.0
            vb = 1.0 if score_of(pb[pr["a"]]) > score_of(pb[pr["o"]]) else 0.0
            v.append(va - vb)
        per_pair.append(float(np.mean(v)))
    # 朴素做法（错误示范）：把 3 个模型 x 90 对当 270 个独立观测
    nb = nc = 0
    for pr in pairs:
        for size, fa, fb in DEPLOY_PAIRS:
            pa, pb = arms[fa], arms[fb]
            va = score_of(pa[pr["a"]]) > score_of(pa[pr["o"]])
            vb = score_of(pb[pr["a"]]) > score_of(pb[pr["o"]])
            if va and not vb:
                nb += 1
            elif vb and not va:
                nc += 1
    pp = np.array(per_pair)
    ps_pool, w_pool, l_pool = sign_test(pp)
    lo, hi, _ = group_boot([p["aid"] for p in pairs], per_pair)
    res["pooled"] = {
        "models": [s for s, _, _ in DEPLOY_PAIRS],
        "naive_units": nb + nc,
        "naive_mcnemar": mcnemar(nb, nc),
        "naive_note": "把 3 个模型 x 90 对当 270 个独立观测——同一对在每个模型上被重复测量，此 p 值不可用",
        "pair_level_mean_delta": float(pp.mean()),
        "pair_level_ci_action_boot": [lo, hi],
        "pair_level_sign_p": ps_pool,
        "pairs_favoring_full": w_pool, "pairs_favoring_blind": l_pool,
        "n_pairs": n_pairs,
    }

    json.dump(res, open(a.out, "w"), ensure_ascii=False, indent=1)
    print("-> %s" % a.out)


if __name__ == "__main__":
    main()
