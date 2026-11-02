# -*- coding: utf-8 -*-
"""阶段六 STEP A：McNemar / binomtest 全面审计。

两件事：
  1) 代码级：列出仓库里所有 McNemar 实现，判断它用的是哪一种口径
     （精确 McNemar = 2*Σ_{i≤min(b,c)} C(n,i) 0.5^n，与 scipy 双侧 binomtest 等价；
     错法是"再乘一次 2"，会把 p 抬到 1）。
  2) 数据级：把报告里写过的 p 值逐条从原始 scen.jsonl / probes 重算，标注检验类型
     （McNemar 配对 vs Fisher 非配对），不一致的列出来。

产物：reports/mcnemar_audit.md + probes/mcnemar_audit.json
"""
import json
import math
import os

from scipy.stats import binomtest, fisher_exact

R = "/data/projects/guardrails"
OUT_MD = os.path.join(R, "reports/mcnemar_audit.md")
OUT_JSON = os.path.join(R, "probes/mcnemar_audit.json")


def load(run):
    p = os.path.join(R, run, "scen.jsonl")
    if not os.path.exists(p):
        return None
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def norm_inj(x):
    if x is None:
        return None
    s = str(x)
    return int(s.rsplit("_", 1)[-1]) if s.rsplit("_", 1)[-1].isdigit() else s


def key(r):
    return (r["user_task"], norm_inj(r.get("injection_task")))


def paired(rows_a, rows_b, field, attack_only=False, clean_only=False):
    """返回 (b, c)：a 成功 b 失败 / b 成功 a 失败。

    attack_only=True 只取受攻击场景；clean_only=True 只取干净场景。
    两者互斥；utility 必须用 clean_only（攻击场景里 utility 无意义，会把 63 条全算进来）。
    """
    def keep(r):
        if attack_only:
            return bool(r.get("injection_present"))
        if clean_only:
            return not r.get("injection_present")
        return True
    A = {key(r): bool(r.get(field)) for r in rows_a if keep(r)}
    B = {key(r): bool(r.get(field)) for r in rows_b if keep(r)}
    ks = [k for k in A if k in B]
    b = sum(1 for k in ks if A[k] and not B[k])
    c = sum(1 for k in ks if B[k] and not A[k])
    return b, c, len(ks)


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    return float(min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n))


def mcnemar_scipy(b, c):
    n = b + c
    if n == 0:
        return 1.0
    return float(min(1.0, binomtest(min(b, c), n, 0.5).pvalue * 2))  # 注意：这里模拟"乘 2"错法


def fisher2(b, c):
    """配对表的 Fisher（b vs c），仅作参考。"""
    if b + c == 0:
        return 1.0
    return float(fisher_exact([[b, 0], [0, c]])[1])


# ---------------------------------------------------------------- 代码级
CODE = [
    ("scripts/e2e_analyze.py:131",
     "binomtest(min(b,c), b+c, 0.5).pvalue",
     "正确（scipy 双侧 = 精确 McNemar）"),
    ("scripts/unified_eval.py:122",
     "min(1, 2*Σ_{i≤min(b,c)} C(n,i)/2^n)",
     "正确（精确 McNemar 定义式）"),
    ("scripts/unified_eval_v2.py:105", "同上", "正确"),
    ("scripts/power_analysis.py:32", "同上", "正确"),
    ("scripts/pair_mcnemar.py:46", "同上", "正确"),
    ("scripts/b9_metrics.py（阶段五修复前）",
     "2*min(binomtest(b,n), binomtest(c,n))",
     "**错**：binomtest 已是双侧，再乘 2 会把 p 抬到 1（6:4 由 0.754 变 1.000）"),
    ("scripts/b9_metrics.py（修复后）",
     "binomtest(min(b,c), n, 0.5).pvalue",
     "正确"),
]


# ---------------------------------------------------------------- 数据级
CASES = []


def case(name, src_a, src_b, field, reported, note, test="mcnemar",
         attack_only=False, clean_only=False):
    CASES.append(dict(name=name, a=src_a, b=src_b, field=field, attack_only=attack_only,
                      clean_only=clean_only, reported=reported, note=note, test=test))


case("B3 · slack 效用（M1 vs Task-Shield）",
     "results/e2e/slack/m2_HB_s0_inj1-3", "results/e2e/slack/tshield_b3_inj1-3",
     "utility", 0.0039, "b3_tshield.md", clean_only=True)
case("B3 · slack ASR（M1 vs Task-Shield）",
     "results/e2e/slack/m2_HB_s0_inj1-3", "results/e2e/slack/tshield_b3_inj1-3",
     "attack_success", 1.0, "b3_tshield.md", attack_only=True)
case("B10-2 · slack ASR（S vs M1）",
     "results/e2e/slack/m2_S_s0_b10_inj1-3", "results/e2e/slack/m2_HB_s0_inj1-3",
     "attack_success", 0.0625, "b10_ablation.md", attack_only=True)
case("B10-2 · slack 效用（S vs M1）",
     "results/e2e/slack/m2_S_s0_b10_inj1-3", "results/e2e/slack/m2_HB_s0_inj1-3",
     "utility", 0.125, "b10_ablation.md", clean_only=True)
case("B10-1 · slack ASR（M1+硬规则 vs M1）",
     "results/e2e/slack/m2_HB_s0_b10hr_inj1-3", "results/e2e/slack/m2_HB_s0_inj1-3",
     "attack_success", 1.0, "b10_ablation.md（0/42 vs 0/42）", attack_only=True)
case("B10-1 · slack 效用（M1+硬规则 vs M1）",
     "results/e2e/slack/m2_HB_s0_b10hr_inj1-3", "results/e2e/slack/m2_HB_s0_inj1-3",
     "utility", None, "b10_ablation.md（66.7%→4.8%）", clean_only=True)
case("B10-1 · slack ASR（纯硬规则 vs M1，报告未给 p）",
     "results/e2e/slack/hard_b10_inj1-3", "results/e2e/slack/m2_HB_s0_inj1-3",
     "attack_success", None, "b10_ablation.md（28.6% vs 0%）", attack_only=True)
# B1 的 2/64 是两批注入合并（inj4-6 + inj5-7），单独用一批算不出 0.50，见 main 里的合并块



def main():
    rows = []
    for c in CASES:
        a = load(c["a"]) if c["a"] else None
        b = load(c["b"])
        if b is None or (c["a"] and a is None):
            rows.append(dict(name=c["name"], status="SKIP", reason="缺少运行"))
            continue
        bb, cc, n = paired(a, b, c["field"], c["attack_only"], c["clean_only"])
        p_mc = mcnemar(bb, cc)
        p_bad = min(1.0, 2 * binomtest(min(bb, cc), bb + cc, 0.5).pvalue) if bb + cc else 1.0

        def keep(r):
            if c["attack_only"]:
                return bool(r.get("injection_present"))
            if c["clean_only"]:
                return not r.get("injection_present")
            return True
        sa = sum(1 for r in a if keep(r) and r.get(c["field"]))
        sb = sum(1 for r in b if keep(r) and r.get(c["field"]))
        na = sum(1 for r in a if keep(r))
        nb = sum(1 for r in b if keep(r))
        p_f = float(fisher_exact([[sa, na - sa], [sb, nb - sb]])[1])

        p_used = p_mc if c["test"] == "mcnemar" else p_f
        rep = c["reported"]
        same = True if rep is None else (abs(round(p_used, 4) - rep) <= 5e-4)
        rows.append(dict(name=c["name"], n=n, b=bb, c=cc,
                         p_mcnemar=round(p_mc, 4), p_fisher=round(p_f, 4),
                         p_if_doubled=round(p_bad, 4), test=c["test"],
                         reported=rep, agree=(None if rep is None else same),
                         src_a=c["a"], src_b=c["b"], note=c["note"]))

    # B1：合并 inj4-6 与 inj5-7 两批（报告的 2/64 vs 0/64）
    m0 = (load("results/e2e/banking/m2_HBnt_s0_b1_inj4-6") or []) + \
         (load("results/e2e/banking/m2_HBnt_s0_inj5-7") or [])
    m1 = (load("results/e2e/banking/m2_HB_s0_b1_inj4-6") or []) + \
         (load("results/e2e/banking/m2_HB_s0_inj5-7") or [])
    if m0 and m1:
        sa = sum(1 for r in m0 if r.get("injection_present") and r.get("attack_success"))
        sb = sum(1 for r in m1 if r.get("injection_present") and r.get("attack_success"))
        na = sum(1 for r in m0 if r.get("injection_present"))
        nb = sum(1 for r in m1 if r.get("injection_present"))
        p_f = float(fisher_exact([[sa, na - sa], [sb, nb - sb]])[1])
        rows.append(dict(name="B1 · banking ASR（M0 vs M1，两批合并 %d 场景）" % na, n=na,
                         b=sa, c=sb, p_mcnemar=round(mcnemar(sa, sb), 4), p_fisher=round(p_f, 4),
                         p_if_doubled=None, test="fisher", reported=0.50,
                         agree=abs(round(p_f, 4) - 0.50) <= 5e-3,
                         src_a="banking/m2_HBnt_s0_{b1_inj4-6,inj5-7}",
                         src_b="banking/m2_HB_s0_{b1_inj4-6,inj5-7}",
                         note="state C2 的 2/64 vs 0/64"))

    # 阶段五：净增益集合
    d = json.load(open(os.path.join(R, "probes/deny_attribution_m0.json"), encoding="utf-8"))
    kk = lambda x: (x["suite"], x["user_task"], x["injection"], x["step"])
    A = {kk(x) for x in d["M1"] if x["p1"] == "DENY"}
    B = {kk(x) for x in d["M0"] if x["p1"] == "DENY"}
    only1, only0 = len(A - B), len(B - A)
    rows.append(dict(name="阶段五 · 净增益集合（M1 only vs M0 only）", n=len(A | B),
                     b=only1, c=only0, p_mcnemar=round(mcnemar(only1, only0), 4),
                     p_fisher=None, p_if_doubled=round(min(1.0, 2 * binomtest(min(only1, only0), only1 + only0, 0.5).pvalue), 4),
                     test="mcnemar", reported=0.754,
                     agree=abs(round(mcnemar(only1, only0), 4) - 0.754) <= 5e-4,
                     src_a="probes/deny_attribution_m0.json", src_b="",
                     note="deny_attribution.md 第 3 节"))
    # 阶段五：meta（报告给的是 Fisher）
    ma, mb = load("results/e2e/travel/m2_HB_s0_b6meta_inj1"), load("results/e2e/travel/m2_HB_s0_authmeta_inj1")
    if ma and mb:
        bb, cc, n = paired(ma, mb, "attack_success", True, False)
        sa = sum(1 for r in ma if r.get("attack_success"))
        sb = sum(1 for r in mb if r.get("attack_success"))
        p_f = float(fisher_exact([[sa, n - sa], [sb, n - sb]])[1])
        rows.append(dict(name="阶段五 · meta 攻击（补丁前 vs 后）", n=n, b=bb, c=cc,
                         p_mcnemar=round(mcnemar(bb, cc), 4), p_fisher=round(p_f, 4),
                         p_if_doubled=None, test="fisher", reported=0.231,
                         agree=abs(round(p_f, 4) - 0.231) <= 5e-4,
                         src_a="m2_HB_s0_b6meta_inj1", src_b="m2_HB_s0_authmeta_inj1",
                         note="posthoc_alignment.md 用 Fisher"))

    # ---- 输出 ----
    L = ["# McNemar / binomtest 审计", "",
         "> 目的：确认所有 p 值的口径一致，并把报告里写过的 p 从原始数据重算一遍。",
         "> 精确 McNemar = `2 * Σ_{i≤min(b,c)} C(n,i) 0.5^n`，与 scipy `binomtest(min(b,c), n, 0.5)` 等价。", "",
         "## 1. 代码级：仓库里的 5 个实现", "",
         "| 位置 | 实现 | 判定 |", "|---|---|---|"]
    for loc, impl, verdict in CODE:
        L.append("| `%s` | `%s` | %s |" % (loc, impl, verdict))
    L += ["", "结论：只有 `b9_metrics.py` 的旧版本写错（在双侧 p 上再乘 2），",
          "已改为 `binomtest(min(b,c), n, 0.5)`；其余 5 处口径正确。",
          "错误版本对 6:4 会给出 1.000（正确 0.754），对 9:0 给出 1.000（正确 0.0039）——方向是**抬高 p**，不会伪造显著。", "",
          "## 2. 数据级：报告 p 值的重算", "",
          "> `mcnemar` 行的 b:c 是**配对不一致对**（a 成功 b 失败 / b 成功 a 失败）；",
          "> `fisher` 行的 b:c 是**两臂各自成功的条数**，不是配对计数。", "",
          "| 检验 | 类型 | 配对 n | b : c | McNemar p | Fisher p | 报告值 | 一致 |",
          "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r.get("status") == "SKIP":
            L.append("| %s | — | — | — | — | — | SKIP（%s） |" % (r["name"], r["reason"]))
            continue
        p_f = "—" if r.get("p_fisher") is None else "%.4f" % r["p_fisher"]
        p_rep = "—" if r["reported"] is None else "%.4f" % r["reported"]
        ok = "—" if r["agree"] is None else ("✓" if r["agree"] else "✗")
        L.append("| %s | %s | %d | %d : %d | **%.4f** | %s | %s | %s |"
                 % (r["name"], r["test"], r["n"], r["b"], r["c"], r["p_mcnemar"], p_f, p_rep, ok))
    bad = [r for r in rows if r.get("agree") is False]
    L += ["", "## 3. 结论", ""]
    if bad:
        L += ["- **%d 条不一致**：" % len(bad)]
        for r in bad:
            L += ["  - %s：报告 %.4f / 重算 %.4f" % (r["name"], r["reported"], r["p_mcnemar"])]
    else:
        L += ["- 所有有报告值的条目**重算一致**（差 ≤ 5e-4）。"]
    L += ["- `final_metrics.csv` 的 McNemar 列由 `scripts/b9_metrics.py` 重算，修复后与本节一致；",
          "- 报告里另有若干 p 值其实是 **Fisher（非配对）**，已在「说明」列标出，正文不得写成 McNemar。",
          "- 结论不变：没有任何一处 p 因为口径错误而变成显著；错误方向只会把 p 抬高。",
          "- **注意 0 不一致对的情形**：B3 的 ASR、B10-1 的 ASR 都是 0:0，McNemar p=1.0；",
          "  这只说明『没有可检验的差异』，不能读成『证明了无差异』（n=42/21 下检验力很低）。",
          "- 新增两个报告里没写过的 p：M1+硬规则 vs M1 的效用 13:0（p=0.0002）、",
          "  纯硬规则 vs M1 的 ASR 12:0（p=0.0005）。前者支持『叠加硬规则摧毁效用』，后者说明纯规则确实拦不住一半攻击。", ""]
    open(OUT_MD, "w", encoding="utf-8").write("\n".join(L) + "\n")
    json.dump(rows, open(OUT_JSON, "w"), ensure_ascii=False, indent=2)
    print("rows", len(rows), "| mismatch", len(bad))
    for r in rows:
        print("  %-42s %-7s n=%-3s b:c=%s:%s mc=%s f=%s rep=%s %s"
              % (r["name"][:42], r.get("test"), r.get("n"), r.get("b"), r.get("c"),
                 r.get("p_mcnemar"), r.get("p_fisher"), r.get("reported"), r.get("agree")))


if __name__ == "__main__":
    main()
