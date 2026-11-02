# -*- coding: utf-8 -*-
"""核算 1.5B 的 p 值：换检验、算功效、看两臂预测的一致性与训练稳定性。

为什么要核算
------------
主检验用的是"动作级符号检验"：47 个动作，只有 10 个动作上两臂不同（9 优 5 劣）。
符号检验只看方向、丢掉幅度，且 47 个样本量下功效很低。若真实效应是 +5pp，
47 个动作本来就常常测不出来。所以必须：
  1) 换更有效的配对检验（McNemar 用 90 个配对单元，而不是 47 个动作）
  2) 用 bootstrap 给均值差的置信区间
  3) 算最小可检测效应（80% 功效）
  4) 直接看两臂预测有多像——如果几乎一样，那就是真没学到任务
"""
import collections
import json
import math
import sys

import numpy as np

ROOT = "/data/projects/guardrails"
SC = {"ALLOW": 1.0, "REVIEW": 0.5, "DENY": 0.0, None: -1.0}


def load_pred(p):
    d = {}
    for l in open(p, encoding="utf-8"):
        x = json.loads(l)
        d[x["sid"]] = x["pred"]
    return d


def main(size):
    rows = {json.loads(l)["sid"]: json.loads(l)
            for l in open(f"{ROOT}/data/pab_rd.jsonl", encoding="utf-8")}
    sp = json.load(open(f"{ROOT}/data/pab_rd_splits.json"))
    te = [rows[i] for i in sp["test"]]

    A = load_pred(f"{ROOT}/results/o1_rd_{size}_test.jsonl")
    B = load_pred(f"{ROOT}/results/o1_rd_{size}_nt_test.jsonl")

    g = collections.defaultdict(lambda: {"ALLOW": [], "other": []})
    for r in te:
        g[r["current_action"]]["ALLOW" if r["label"] == "ALLOW" else "other"].append(r)

    # ---- 单元级：90 个 (allow, other) 配对
    cells = collections.Counter()
    per_action = collections.defaultdict(lambda: [0, 0, 0])   # win, lose, n
    for k, v in g.items():
        for a in v["ALLOW"]:
            for o in v["other"]:
                sa, so = SC[A.get(a["sid"])], SC[A.get(o["sid"])]
                ba, bo = SC[B.get(a["sid"])], SC[B.get(o["sid"])]
                okA = sa > so
                okB = ba > bo
                if okA and not okB:
                    cells["aware_only"] += 1
                    per_action[k][0] += 1
                elif okB and not okA:
                    cells["blind_only"] += 1
                    per_action[k][1] += 1
                elif okA and okB:
                    cells["both"] += 1
                else:
                    cells["neither"] += 1
                per_action[k][2] += 1

    bo, bb = cells["aware_only"], cells["blind_only"]
    n = bo + bb
    p_mcn = (sum(math.comb(n, i) for i in range(min(bo, bb) + 1)) / 2 ** n * 2) if n else 1.0
    print("=" * 74)
    print("[%s] 配对单元级（n=%d 对）" % (size, sum(cells.values())))
    print("  两臂都对 %d | 只有 aware 对 %d | 只有 blind 对 %d | 都错 %d"
          % (cells["both"], bo, bb, cells["neither"]))
    print("  精确 McNemar: %d : %d  ->  p = %.4f" % (bo, bb, min(1.0, p_mcn)))
    accA = (cells["both"] + bo) / sum(cells.values())
    accB = (cells["both"] + bb) / sum(cells.values())
    print("  aware=%.1f%%  blind=%.1f%%  Δ=%+.1fpp" % (100 * accA, 100 * accB,
                                                       100 * (accA - accB)))

    # ---- bootstrap over pairs（重采样配对单元）
    pairs = []
    for k, v in g.items():
        for a in v["ALLOW"]:
            for o in v["other"]:
                pairs.append((A.get(a["sid"]), A.get(o["sid"]),
                              B.get(a["sid"]), B.get(o["sid"])))
    rng = np.random.default_rng(0)
    deltas = []
    for _ in range(4000):
        idx = rng.integers(0, len(pairs), len(pairs))
        s = 0.0
        for i in idx:
            sa, so, ba, bo2 = pairs[i]
            s += (SC[sa] > SC[so]) - (SC[ba] > SC[bo2])
        deltas.append(100 * s / len(pairs))
    lo, hi = np.percentile(deltas, [2.5, 97.5])
    print("  bootstrap 95%%CI of Δ = [%+.1f, %+.1f] pp  (mean %+.1f)"
          % (lo, hi, 100 * (accA - accB)))

    # ---- 动作级：符号检验 + Wilcoxon + t
    d = [v[0] / v[2] - v[1] / v[2] for v in per_action.values()]
    win = sum(1 for x in d if x > 1e-9)
    lose = sum(1 for x in d if x < -1e-9)
    m = win + lose
    p_sign = min(1.0, 2 * sum(math.comb(m, i) for i in range(min(win, lose) + 1)) / 2 ** m) if m else 1.0
    print("\n动作级（n=%d）：win %d / lose %d / tie %d，符号检验 p=%.4f"
          % (len(d), win, lose, len(d) - m, p_sign))
    try:
        from scipy import stats
        w = stats.wilcoxon(d)
        t = stats.ttest_rel([per_action[k][0] / per_action[k][2] for k in per_action],
                            [per_action[k][1] / per_action[k][2] for k in per_action])
        print("  Wilcoxon p=%.4f ; paired t p=%.4f" % (w.pvalue, t.pvalue))
    except Exception as e:
        print("  scipy 不可用:", repr(e)[:60])

    # ---- 功效：给定动作级差值的标准差，80% 功效能测到多大效应
    sd = float(np.std(d, ddof=1))
    mde = 2.802 * sd / math.sqrt(len(d))      # 双侧 alpha=.05, power=.8 的近似
    print("\n功效分析：动作级差值 sd=%.3f，n=%d -> 80%% 功效的最小可检测效应 ≈ %.1f pp"
          % (sd, len(d), 100 * mde))
    print("  观测到的均值差 = %+.1f pp" % (100 * float(np.mean(d))))

    # ---- 两臂预测像不像
    same = sum(1 for r in te if A.get(r["sid"]) == B.get(r["sid"]))
    print("\n两臂逐样本预测相同比例 = %d/%d = %.1f%%" % (same, len(te), 100 * same / len(te)))
    cz = collections.Counter((A.get(r["sid"]), B.get(r["sid"])) for r in te)
    top = cz.most_common(4)
    print("  最常见的 (aware, blind) 组合:", top)


if __name__ == "__main__":
    for s in sys.argv[1:] or ["15b"]:
        main(s)
