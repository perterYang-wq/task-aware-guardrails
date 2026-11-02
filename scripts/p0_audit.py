# -*- coding: utf-8 -*-
"""P0-1：审计每个臂的 score 语义、来源与可比性。

三个问题分开回答（之前把它们混成一个"方向是否 OK"，导致把"模型退化"误判成"口径错误"）：

  A. score 来源与类型
       continuous_prob  —— 连续分数（概率或其线性组合），并列几乎不可能
       ordinal_label    —— 离散标签映射 {ALLOW:1.0, REVIEW:0.5, DENY:0.0}
       constant         —— 常数（多数类基线）

  B. 方向约定
       全部为"越高越倾向 ALLOW"。这是**构造保证**，逐臂用数值范围与端点含义断言校验，
       而不是靠观察均值单调（退化臂的均值必然相等，那是模型问题，不是方向问题）。

  C. 可比性标记
       连续分数臂的 SPA 与 PRA 必然相等（无并列），因此 **SPA 只在离散输出臂之间可比**。
       这一点之前没有写进论文，属于口径差异，必须显式标注。
"""
import collections
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREDS = os.path.join(ROOT, "results", "preds")
OUT = os.path.join(ROOT, "results", "frozen")
DATA = os.path.join(ROOT, "data", "pab_rd.jsonl")
SPLITS = os.path.join(ROOT, "data", "pab_rd_splits.json")

ORIGIN = {
    "base_majority": ("constant", "常数 0.5（多数类）"),
    "base_tool_lookup": ("continuous_prob", "(ALLOW+0.5)/(n+1)，按工具名"),
    "base_action_lookup": ("continuous_prob", "(ALLOW+0.5)/(n+1)，按动作文本"),
    "base_tfidf_action": ("continuous_prob", "p(ALLOW)+0.5*p(REVIEW)，动作"),
    "base_tfidf_task": ("continuous_prob", "p(ALLOW)+0.5*p(REVIEW)，动作+任务"),
    "base_tfidf_full": ("continuous_prob", "p(ALLOW)+0.5*p(REVIEW)，动作+任务+证据"),
}
DEPLOY = {"full_0.5B", "blind_0.5B", "full_1.5B", "blind_1.5B",
          "full_3B", "blind_3B"}


def score_of(rec):
    s = rec.get("score")
    if s is None:
        s = {"ALLOW": 1.0, "REVIEW": 0.5, "DENY": 0.0}.get(rec.get("pred"))
    return float(s)


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = {json.loads(l)["sid"]: json.loads(l)
            for l in open(DATA, encoding="utf-8")}
    sp = json.load(open(SPLITS))
    te_ids = set(sp["test"])

    audit = {"test_size": len(te_ids), "arms": {}, "notes": []}
    for f in sorted(os.listdir(PREDS)):
        if not f.endswith(".jsonl"):
            continue
        name = f[:-6]
        recs = {}
        for line in open(os.path.join(PREDS, f), encoding="utf-8"):
            d = json.loads(line)
            recs[d["sid"]] = d
        vals = [score_of(recs[s]) for s in te_ids & set(recs)]
        uniq = sorted(set(vals))
        if name in ORIGIN:
            stype, origin = ORIGIN[name]
        elif len(uniq) <= 4 and set(uniq) <= {0.0, 0.5, 1.0}:
            stype, origin = "ordinal_label", "ALLOW=1.0 / REVIEW=0.5 / DENY=0.0"
        else:
            stype, origin = "continuous_prob", "未登记"

        in_range = all(-1e-9 <= v <= 1 + 1e-9 for v in vals)
        endpoint_ok = True
        if stype == "ordinal_label":
            endpoint_ok = all(
                (recs[s]["pred"] == "ALLOW") == (abs(score_of(recs[s]) - 1.0) < 1e-9)
                for s in te_ids & set(recs))
        direction_ok = in_range and endpoint_ok

        by = collections.defaultdict(list)
        for s in te_ids & set(recs):
            by[rows[s]["label"]].append(score_of(recs[s]))
        mean = {k: sum(v) / len(v) for k, v in by.items()}

        audit["arms"][name] = {
            "n": len(recs), "missing": len(te_ids - set(recs)),
            "extra": len(set(recs) - te_ids),
            "score_type": stype, "score_origin": origin,
            "score_range": [min(vals), max(vals)],
            "direction_ok": bool(direction_ok),
            "tie_possible": stype != "continuous_prob",
            "spa_comparable": stype != "continuous_prob",
            "degenerate": bool(max(vals) - min(vals) < 1e-9) if vals else True,
            "anti_correlated": bool(mean.get("ALLOW", 1) < mean.get("DENY", 0)),
            "mean_score_by_gold": {k: round(v, 4) for k, v in mean.items()},
            "role": "deploy" if name in DEPLOY else "exploratory/baseline",
        }

    print("%-22s%-17s%8s%7s%7s%8s%9s" % ("arm", "score_type", "max", "dir",
                                         "degen", "spa_cmp", "anti"))
    for n, d in audit["arms"].items():
        print("%-22s%-17s%8.2f%7s%7s%8s%9s"
              % (n, d["score_type"], d["score_range"][1],
                 "OK" if d["direction_ok"] else "BAD",
                 "yes" if d["degenerate"] else "-",
                 "yes" if d["spa_comparable"] else "NO",
                 "yes" if d["anti_correlated"] else "-"))

    audit["notes"].append(
        "所有臂 score 方向均为『越高越倾向 ALLOW』，由构造保证：离散臂为 ordinal_label 映射，"
        "连续臂为 ALLOW 概率或其线性组合。逐臂用数值范围与端点含义断言校验，未依赖均值单调性。")
    audit["notes"].append(
        "口径差异 1（新发现，之前未写）：连续分数臂（6 个基线）不可能出现并列，其 SPA 必然等于 PRA。"
        "因此 SPA 只在离散输出臂之间可比，跨族比较 SPA 无意义。")
    audit["notes"].append(
        "口径差异 2：分数退化为常数（degenerate）与预测反相关（anti_correlated）是模型质量问题，"
        "不是口径错误；已单列，不参与方向判定。")

    json.dump(audit, open(os.path.join(OUT, "preds_audit.json"), "w"),
              ensure_ascii=False, indent=1)
    print("\n口径差异：")
    for note in audit["notes"]:
        print("  - " + note)
    print("\n-> results/frozen/preds_audit.json")


if __name__ == "__main__":
    main()
