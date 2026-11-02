# -*- coding: utf-8 -*-
"""STEP A：净增益的集合与效度（0 GPU）。

两臂在同一批 34 条实例上的 DENY 集合。给出两种定义，避免口径含糊：

  定义 S（严格，主口径）：集合成员 = P0 判 DENY **且** P1 仍 DENY
      —— 部署意义上"不看载荷原文也会拦"的调用。任务盲臂若 P0 放行，就不算它有这个先验。
  定义 L（宽松，敏感性）：集合成员 = P1 仍 DENY（不看 P0）
      —— 与第 2 节 76.9%（20/26）同一口径。

  M1 only = |A \\ B|（任务信息独有的拦截 = 净增益）
  M0 only = |B \\ A|（任务盲能拦、任务感知反而放过）
  交集    = |A ∩ B|

再对 M1 only 的每一条查 P1 效度（probes/p1_residual.json）：
实体残留（邮箱/URL 仍在 P1 history）或复述率 > 0.5 → 记为 dirty（净增益不干净）。

产物：probes/net_gain_sets.json
"""
import json

R = "/data/projects/guardrails"
d = json.load(open(R + "/probes/deny_attribution_m0.json", encoding="utf-8"))
res = json.load(open(R + "/probes/p1_residual.json", encoding="utf-8"))
res_idx = {(r["suite"], r["user_task"], r.get("injection"), r["step"]): r for r in res["rows"]}
key = lambda r: (r["suite"], r["user_task"], r["injection"], r["step"])  # noqa: E731


def build(strict):
    def deny(arm):
        return {key(r) for r in d[arm]
                if r["p1"] == "DENY" and (r["p0"] == "DENY" if strict else True)}
    A, B = deny("M1"), deny("M0")
    return dict(M1=len(A), M0=len(B), intersection=len(A & B),
                M1_only=len(A - B), M0_only=len(B - A),
                m1_only_cases=[list(x) for x in sorted(A - B)],
                m0_only_cases=[list(x) for x in sorted(B - A)])


def dirty_of(cases):
    detail, n = [], 0
    for c in cases:
        r = res_idx.get(tuple(c))
        if r is None:
            detail.append(dict(case=c, found=False))
            continue
        bad = bool(r["entity_residual"]) or r["token_recall"] > 0.5
        n += int(bad)
        detail.append(dict(case=c, tool=r["tool"], entity_residual=r["entity_residual"],
                           token_recall=r["token_recall"], dirty=bad))
    return n, detail


out = {"strict": build(True), "loose": build(False)}
for k in ("strict", "loose"):
    n, det = dirty_of(out[k]["m1_only_cases"])
    out[k]["dirty"] = n
    out[k]["robust_subset"] = out[k]["M1_only"] - n
    out[k]["m1_only_detail"] = det
out["primary"] = "strict"
json.dump(out, open(R + "/probes/net_gain_sets.json", "w"), ensure_ascii=False, indent=2)

for k in ("strict", "loose"):
    s = out[k]
    print("[%s] M1 %d / M0 %d / 交集 %d / M1only %d / M0only %d | dirty %d / %d | robust %d"
          % (k, s["M1"], s["M0"], s["intersection"], s["M1_only"], s["M0_only"],
             s["dirty"], s["M1_only"], s["robust_subset"]))
    for x in s["m1_only_detail"]:
        print("   ", x)
