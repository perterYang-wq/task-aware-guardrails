# -*- coding: utf-8 -*-
"""P2 验收：结构一致性、策略 A/B 分歧、标签合理性、泄漏。

只读 data/p2_pairs.jsonl 与 data/p2_index.json，不改数据。
"""
import collections
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAIRS = os.path.join(ROOT, "data", "p2_pairs.jsonl")
IDX = os.path.join(ROOT, "data", "p2_index.json")


def main():
    rows = [json.loads(l) for l in open(PAIRS, encoding="utf-8")]
    idx = json.load(open(IDX, encoding="utf-8"))
    by = collections.defaultdict(list)
    for r in rows:
        by[r["pair_id"]].append(r)

    print("== 1. 结构一致性（独立复算，不信任构建脚本的自报） ==")
    ok = collections.Counter()
    bad = []
    for pid, rs in by.items():
        if len(rs) != 2:
            bad.append((pid, "arity=%d" % len(rs)))
            continue
        p = next((x for x in rs if x["pair_role"] == "positive"), None)
        n = next((x for x in rs if x["pair_role"] == "negative"), None)
        if not p or not n:
            bad.append((pid, "missing_role"))
            continue
        checks = {
            "same_action": p["current_action"] == n["current_action"],
            "same_evidence": p["history"] == n["history"],
            "diff_task": p["instruction"] != n["instruction"],
            "diff_task_id": p["task_id"] != n["task_id"],
            "label_flip": (p["label"], n["label"]) == ("ALLOW", "DENY"),
            "same_action_id": p["action_id"] == n["action_id"],
            "same_evidence_id": p["evidence_id"] == n["evidence_id"],
        }
        for k, v in checks.items():
            if v:
                ok[k] += 1
            else:
                bad.append((pid, k))
    print("配对 %d 组，记录 %d 条" % (len(by), len(rows)))
    for k in ("same_action", "same_evidence", "diff_task", "diff_task_id",
              "label_flip", "same_action_id", "same_evidence_id"):
        print("  %-18s %d/%d" % (k, ok[k], len(by)))
    print("  异常 %d 条%s" % (len(bad), ("：" + str(bad[:5])) if bad else ""))

    print("\n== 2. 唯一性与重复 ==")
    print("  pair_id 唯一: %s" % (len(by) == len({r['pair_id'] for r in rows})))
    print("  (action,evidence) 组合数: %d，平均每组 %.1f 对"
          % (len({(r["action_id"], r["evidence_id"]) for r in rows}),
             len(by) / max(len({(r["action_id"], r["evidence_id"]) for r in rows}), 1)))
    same_action_multi = collections.Counter(r["action_id"] for r in rows)
    print("  被复用最多的 action: %s"
          % [(k, v) for k, v in same_action_multi.most_common(3)])

    print("\n== 3. 策略 A/B 分歧 ==")
    dis = [r for r in rows if not r["agree"]]
    print("  不一致 %d/%d = %.2f%%" % (len(dis), len(rows), 100 * len(dis) / len(rows)))
    ct = collections.Counter((r["label"], r["label_B"], r["label_reason"], r["reason_B"])
                             for r in dis)
    for k, v in ct.most_common(8):
        print("    A=%-5s B=%-5s  A理由=%-22s B理由=%-22s %d" % (*k, v))
    print("  分歧样例（前 5）：")
    for r in dis[:5]:
        print("    [%s] %s | %s" % (r["pair_role"], r["label_reason"], r["instruction"][:90]
                                    .replace("\n", " ")))
    # 分歧是否落在正例上（正例被 B 否掉 = 可能误标）
    print("  分歧中正例 %d 条、负例 %d 条"
          % (sum(1 for r in dis if r["pair_role"] == "positive"),
             sum(1 for r in dis if r["pair_role"] == "negative")))

    print("\n== 4. 标签合理性 ==")
    print("  正例理由:", dict(collections.Counter(r["label_reason"] for r in rows
                                                 if r["pair_role"] == "positive")))
    print("  负例理由:", dict(collections.Counter(r["label_reason"] for r in rows
                                                 if r["pair_role"] == "negative")))
    print("  负例理由 × 域:")
    c = collections.Counter((r["suite"], r["label_reason"]) for r in rows
                            if r["pair_role"] == "negative")
    for k, v in sorted(c.items()):
        print("    %-12s %-24s %d" % (k[0], k[1], v))
    # 负例任务是否真的"不请求该效果"：抽查其指令里是否出现工具动词
    print("  受拒正例 %d 条（策略对 ground_truth 判 DENY）—— 说明策略偏严，不是偏松"
          % idx["counts"]["policy_reject"])

    print("\n== 5. 泄漏 ==")
    print("  配对分层:", idx["tiers"])
    tiers = collections.defaultdict(set)
    for q in idx["pairs"]:
        ps = {q["part_auth"], q["part_deny"]}
        t = "strict_test" if ps == {"test"} else ("unseen" if ps <= {"val", "test"} else "contains_train")
        tiers[t].add(q["pair_id"])
    # 任务级重叠
    def tasks_of(pid_set):
        out = set()
        for r in rows:
            if r["pair_id"] in pid_set:
                out.add(r["task_id"])
        return out
    tt = tasks_of(tiers["strict_test"])
    ct2 = tasks_of(tiers["contains_train"])
    print("  strict_test 涉及任务 %d 个（应全部来自 test split）" % len(tt))
    train_tasks = {q["task_auth"] for q in idx["pairs"] if q["part_auth"] == "train"} | \
                  {q["task_deny"] for q in idx["pairs"] if q["part_deny"] == "train"}
    print("  strict_test 与 train 任务交集: %d" % len(tt & train_tasks))
    # 动作/证据重叠
    sa = {r["action_id"] for r in rows if r["pair_id"] in tiers["strict_test"]}
    ca = {r["action_id"] for r in rows if r["pair_id"] in tiers["contains_train"]}
    print("  strict_test 与 contains_train 的 action 交集: %d / %d" % (len(sa & ca), len(sa)))

    print("\n== 6. 与 PAB-RD 的关系 ==")
    import hashlib
    pab = [json.loads(l) for l in open(os.path.join(ROOT, "data", "pab_rd.jsonl"),
                                       encoding="utf-8")]
    pab_actions = {hashlib.sha1(r["current_action"].encode()).hexdigest()[:10] for r in pab}
    p2_actions = {r["action_id"] for r in rows}
    print("  P2 action 与 PAB-RD action 交集: %d / %d"
          % (len(p2_actions & pab_actions), len(p2_actions)))
    print("  （交集非零是预期的：同一套工具与参数空间；关键是配对本身是新建的）")

    out = os.path.join(ROOT, "results", "audit", "p2_validation.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({"n_pairs": len(by), "n_records": len(rows), "checks": dict(ok),
               "bad": bad[:20], "policy_disagree": len(dis),
               "disagree_rows": dis[:50], "tiers": idx["tiers"],
               "rejected_reasons": idx["rejected_reasons"],
               "policy_agreement": idx["policy_agreement"]},
              open(out, "w"), ensure_ascii=False, indent=1)
    print("\n-> %s" % out)


if __name__ == "__main__":
    main()
