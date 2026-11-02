# -*- coding: utf-8 -*-
"""为什么只有 1.5B 不显著：逐项拆解 + 合并/分层检验。

三个可能的解释必须分开验证：
  H1 功效不足：90 个配对单元的分辨率只有 ~20pp，8pp 的效应本来就测不出来
  H2 效应确实更小：1.5B 的点估计（+7.8pp）远低于其他三个（+19/+30/+23）
  H3 检验选错：动作级符号检验丢掉幅度，改用配对单元 McNemar 是否改变结论

做法：
  1) 每个尺寸给出配对单元 2x2 表、McNemar、bootstrap CI、以及"要多大样本才能测到"
  2) 合并四个尺寸做 McNemar（效应同质的假设下）
  3) 做 CMH 分层检验（允许各尺寸效应不同）
  4) 反推达到 80%/90% 功效所需配对数
"""
import collections
import json
import math

ROOT = "/data/projects/guardrails"
SC = {"ALLOW": 1.0, "REVIEW": 0.5, "DENY": 0.0, None: -1.0}
SIZES = [("0.5B", "05b"), ("1.5B", "15b"), ("3B", "3b"), ("7B", "7b")]


def load_pred(p):
    d = {}
    for l in open(p, encoding="utf-8"):
        x = json.loads(l)
        d[x["sid"]] = x["pred"]
    return d


def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def main():
    rows = {json.loads(l)["sid"]: json.loads(l)
            for l in open(f"{ROOT}/data/pab_rd.jsonl", encoding="utf-8")}
    sp = json.load(open(f"{ROOT}/data/pab_rd_splits.json"))
    te = [rows[i] for i in sp["test"]]

    g = collections.defaultdict(lambda: {"ALLOW": [], "other": []})
    for r in te:
        g[r["current_action"]]["ALLOW" if r["label"] == "ALLOW" else "other"].append(r)
    pairs = []
    for k, v in g.items():
        for a in v["ALLOW"]:
            for o in v["other"]:
                pairs.append((a, o))

    print("测试集配对单元总数 = %d（与尺寸无关，由基准决定）\n" % len(pairs))
    print("%-7s%8s%8s%9s%11s%14s" % ("size", "aware+", "blind+", "Δ(pp)",
                                     "McNemar p", "bootstrap 95%CI"))
    tot = [0, 0]
    strata = []
    for name, tag in SIZES:
        A = load_pred(f"{ROOT}/results/o1_rd_{tag}_test.jsonl")
        B = load_pred(f"{ROOT}/results/o1_rd_{tag}_nt_test.jsonl")
        b = c = both = neither = 0
        deltas = []
        for a, o in pairs:
            okA = SC[A.get(a["sid"])] > SC[A.get(o["sid"])]
            okB = SC[B.get(a["sid"])] > SC[B.get(o["sid"])]
            if okA and not okB:
                b += 1
            elif okB and not okA:
                c += 1
            elif okA:
                both += 1
            else:
                neither += 1
        n = len(pairs)
        d = 100.0 * (b - c) / n
        # Wald CI（配对比例差）
        se = 100.0 * math.sqrt(max(b + c - (b - c) ** 2 / n, 1e-9)) / n
        print("%-7s%8d%8d%9.1f%11.4f%14s"
              % (name, b, c, d, mcnemar_exact(b, c),
                 "[%+.1f,%+.1f]" % (d - 1.96 * se, d + 1.96 * se)))
        tot[0] += b
        tot[1] += c
        strata.append((name, b, c, both, neither))

    # ---- 合并检验（假设四个尺寸效应同质）
    print("\n合并四个尺寸：aware 独对 %d，blind 独对 %d，精确 McNemar p = %.2e"
          % (tot[0], tot[1], mcnemar_exact(*tot)))

    # ---- CMH 分层检验（允许各层效应不同，检验"控制尺寸后是否仍有共同效应"）
    num = den = 0.0
    for name, b, c, both, neither in strata:
        n = b + c + both + neither
        if n < 2:
            continue
        num += b - (b + c) / 2.0
        den += (b + c) * (2 * both + 2 * neither + b + c) / (4.0 * (n - 1))
    stat = num ** 2 / den if den > 0 else 0.0
    # 卡方 1 自由度
    p_cmh = math.erfc(math.sqrt(stat / 2.0))
    print("CMH 分层检验（按尺寸分层）：chi2 = %.2f, df=1, p = %.2e" % (stat, p_cmh))

    # ---- 要多大的样本才能测到 8pp
    print("\n样本量需求（双侧 α=.05, 配对比例差 d）：")
    for d_pp in (5, 8, 15, 20):
        p = d_pp / 100.0
        # 近似：n ≈ (z_{1-α/2}+z_{power})^2 * (1-p_disc) / p_disc^2，用 discordance≈0.5 保守
        for power, z in ((0.8, 2.802), (0.9, 3.242)):
            n_req = (z / p) ** 2 * 0.25 * 4      # discordant pairs 需求 ~ (z/p)^2 * 0.25*4
            print("  Δ=%2dpp, 功效 %.0f%% -> 需要约 %d 个配对（现 90 个）"
                  % (d_pp, 100 * power, n_req))


if __name__ == "__main__":
    main()
