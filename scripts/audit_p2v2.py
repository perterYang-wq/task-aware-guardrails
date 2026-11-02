# -*- coding: utf-8 -*-
"""P2-v2 审计：结构一致性、场景统计、重复与交叉泄漏、字段完整性。"""
import collections
import hashlib
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAIRS = os.path.join(ROOT, "data", "p2v2_pairs.jsonl")
IDX = os.path.join(ROOT, "data", "p2v2_index.json")


def tier(r):
    ps = {r["part_auth"], r["part_deny"]}
    if ps == {"test"}:
        return "strict_test"
    if ps <= {"val", "test"}:
        return "unseen"
    return "contains_train"


def main():
    rows = [json.loads(l) for l in open(PAIRS, encoding="utf-8")]
    idx = json.load(open(IDX, encoding="utf-8"))
    by = collections.defaultdict(list)
    for r in rows:
        by[r["pair_id"]].append(r)
    scen = collections.defaultdict(list)
    for r in rows:
        scen[r["scenario_id"]].append(r)

    print("== 1. 结构一致性 ==")
    ok, bad = collections.Counter(), []
    for pid, rs in by.items():
        if len(rs) != 2:
            bad.append((pid, "arity"))
            continue
        p = next((x for x in rs if x["pair_role"] == "positive"), None)
        n = next((x for x in rs if x["pair_role"] == "negative"), None)
        if not (p and n):
            bad.append((pid, "role"))
            continue
        for k, v in (("same_action", p["current_action"] == n["current_action"]),
                     ("same_evidence", p["history"] == n["history"]),
                     ("diff_task", p["instruction"] != n["instruction"]),
                     ("same_scenario", p["scenario_id"] == n["scenario_id"]),
                     ("label_flip", (p["label"], n["label"]) == ("ALLOW", "DENY"))):
            ok[k] += v
            if not v:
                bad.append((pid, k))
    print("配对 %d / 记录 %d / 场景 %d / 动作 %d"
          % (len(by), len(rows), len(scen), len({r["action_id"] for r in rows})))
    for k in ("same_action", "same_evidence", "diff_task", "same_scenario", "label_flip"):
        print("  %-14s %d/%d" % (k, ok[k], len(by)))
    print("  异常 %d" % len(bad))

    print("\n== 2. 场景结构 ==")
    per = collections.Counter(rs[0]["scenario_id"] for rs in by.values())
    print("  每场景配对数: %s" % dict(collections.Counter(per.values())))
    per_rec = collections.Counter(r["scenario_id"] for r in rows)
    print("  每场景记录数: %s" % dict(collections.Counter(per_rec.values())))
    print("  场景 × 域: %s" % dict(collections.Counter(
        {s: rs[0]["suite"] for s, rs in scen.items()}.values())))
    print("  证据变体 × 场景: %s" % dict(collections.Counter(
        {s: rs[0]["variant"] for s, rs in scen.items()}.values())))
    acts = collections.defaultdict(set)
    for s, rs in scen.items():
        acts[rs[0]["action_id"]].add(s)
    print("  每个动作的场景数: %s" % dict(collections.Counter(len(v) for v in acts.values())))
    print("  场景最多的动作: %s" % [x[1] for x in
                                sorted(((len(v), k) for k, v in acts.items()), reverse=True)[:3]])

    print("\n== 3. 分层与泄漏 ==")
    tiers = collections.defaultdict(set)
    for r in rows:
        tiers[tier(r)].add(r["scenario_id"])
    print("  场景分层: %s" % {k: len(v) for k, v in tiers.items()})
    print("  配对分层: %s" % dict(collections.Counter(tier(r) for r in by_representative(by))))

    def tasks_of(pids):
        out = set()
        for r in rows:
            if r["scenario_id"] in pids:
                out.add(r["task_id"])
        return out
    st = tasks_of(tiers["strict_test"])
    tr = tasks_of(tiers["contains_train"])
    print("  strict_test 任务 %d 个，与 contains_train 交集 %d" % (len(st), len(st & tr)))
    sa = {r["action_id"] for r in rows if r["scenario_id"] in tiers["strict_test"]}
    ca = {r["action_id"] for r in rows if r["scenario_id"] in tiers["contains_train"]}
    print("  strict_test 动作 %d 个，与 contains_train 交集 %d" % (len(sa), len(sa & ca)))
    se = {r["evidence_id"] for r in rows if r["scenario_id"] in tiers["strict_test"]}
    ce = {r["evidence_id"] for r in rows if r["scenario_id"] in tiers["contains_train"]}
    print("  strict_test 证据 %d 份，与 contains_train 交集 %d" % (len(se), len(se & ce)))
    stpl = {r["task_cls"] for r in rows if r["scenario_id"] in tiers["strict_test"]}
    ctpl = {r["task_cls"] for r in rows if r["scenario_id"] in tiers["contains_train"]}
    print("  strict_test 任务模板 %d 个，与 contains_train 交集 %d" % (len(stpl), len(stpl & ctpl)))

    print("\n== 4. 重复检查 ==")
    print("  pair_id 唯一: %s" % (len(by) == len({r['pair_id'] for r in rows})))
    print("  scenario_id 唯一: %s" % (len(scen) == len({r['scenario_id'] for r in rows})))
    ev = collections.Counter(r["evidence_id"] for r in rows)
    act = collections.Counter(r["action_id"] for r in rows)
    print("  证据复用: 最多一条证据被 %d 条记录共用（同一场景内 4 对共享 = 8 条）"
          % max(ev.values()))
    print("  动作复用: 最多一个动作被 %d 条记录共用" % max(act.values()))
    instr = collections.Counter(r["instruction"] for r in rows)
    print("  任务文本复用: 最多 %d 次（同名任务配不同动作，预期）" % max(instr.values()))

    print("\n== 5. 字段完整性 ==")
    need = ("label_reason", "evidence_source", "scenario_id", "variant", "tool")
    missing = {k: sum(1 for r in rows if not r.get(k)) for k in need}
    print("  缺失字段: %s" % missing)

    print("\n== 6. 冻结 ==")
    h = hashlib.sha256(open(PAIRS, "rb").read()).hexdigest()
    print("  当前文件 sha256 = %s" % h)
    print("  index 记录 sha256 = %s  %s"
          % (idx["index"]["sha256"], "一致" if h == idx["index"]["sha256"] else "**不一致**"))

    out = os.path.join(ROOT, "results", "audit", "p2v2_validation.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({"checks": dict(ok), "bad": bad[:20],
               "n_pairs": len(by), "n_records": len(rows), "n_scenarios": len(scen),
               "n_actions": len({r["action_id"] for r in rows}),
               "scenario_tiers": {k: len(v) for k, v in tiers.items()},
               "per_scenario": dict(collections.Counter(per.values())),
               "sha256": h}, open(out, "w"), ensure_ascii=False, indent=1)
    print("\n-> %s" % out)


def by_representative(by):
    return [rs[0] for rs in by.values()]


if __name__ == "__main__":
    main()
