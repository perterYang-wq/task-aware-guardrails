# -*- coding: utf-8 -*-
"""阶段五 STEP A：净增益的集合与效度（0 GPU）。

集合定义（都用 P1 去载荷后的判定，口径与 deny_attribution 一致）：
  A = M1 判 DENY 的实例
  B = M0 判 DENY 的实例
  M1 only = A - B      （任务信息独有的拦截）
  M0 only = B - A      （任务盲也拦、任务感知反而不拦 → 净增益的反向证据）
  intersection = A ∩ B

效度：对 M1 only 的每一条，查 p1_residual.json：
  该条的 P1 history 是否仍含载荷实体，或载荷专名复述率 > 0.5。
若命中，这条"净增益"就不是干净的任务推理，而是复述驱动，应剔除。

产物：probes/net_gain_sets.json + 控制台表
"""
import json
import os

R = "/data/projects/guardrails"
d = json.load(open(os.path.join(R, "probes/deny_attribution_m0.json"), encoding="utf-8"))


def key(x):
    return (x["suite"], x["user_task"], x["injection"], x["step"])


m1 = {key(x): x for x in d["M1"]}
m0 = {key(x): x for x in d["M0"]}
assert set(m1) == set(m0), "两臂实例集合不一致"

A = {k for k, x in m1.items() if x["p1"] == "DENY"}
B = {k for k, x in m0.items() if x["p1"] == "DENY"}
m1_only, m0_only, inter = A - B, B - A, A & B

res = json.load(open(os.path.join(R, "probes/p1_residual.json"), encoding="utf-8"))["rows"]
res_by = {(x["suite"], x["user_task"], x["injection"], x["step"]): x for x in res}


def contaminated(k):
    r = res_by.get(k)
    if not r:
        return None
    return bool(r["entity_residual"]) or r["token_recall"] > 0.5


cont = [k for k in m1_only if contaminated(k)]
clean_gain = [k for k in m1_only if contaminated(k) is False]

print("A(M1 DENY)=%d  B(M0 DENY)=%d" % (len(A), len(B)))
print("M1 only=%d  M0 only=%d  intersection=%d" % (len(m1_only), len(m0_only), len(inter)))
print("\nM1 only 的 6 条：")
for k in sorted(m1_only):
    r = res_by.get(k, {})
    print("  %-6s %-13s step=%-2s %-24s ent=%s tok=%.2f -> %s"
          % (k[0], k[1], k[3], m1[k]["tool"],
             len(r.get("entity_residual") or []), r.get("token_recall", 0),
             "污染" if contaminated(k) else "干净"))
print("\nM0 only 的 %d 条：" % len(m0_only))
for k in sorted(m0_only):
    print("  %-6s %-13s step=%-2s %-24s" % (k[0], k[1], k[3], m0[k]["tool"]))

out = dict(
    M1_deny=len(A), M0_deny=len(B),
    M1_only=len(m1_only), M0_only=len(m0_only), intersection=len(inter),
    M1_only_items=[list(k) for k in sorted(m1_only)],
    M0_only_items=[list(k) for k in sorted(m0_only)],
    contaminated=len(cont), robust_subset=len(clean_gain),
    contaminated_items=[list(k) for k in sorted(cont)],
    note="contaminated = P1 后仍含载荷实体 或 专名复述率>0.5",
    ts=__import__("time").strftime("%Y-%m-%d %H:%M:%S"),
)
json.dump(out, open(os.path.join(R, "probes/net_gain_sets.json"), "w"), ensure_ascii=False, indent=2)
print("\n净增益 %d 条，其中受污染 %d 条，稳健子集 %d 条" % (len(m1_only), len(cont), len(clean_gain)))
