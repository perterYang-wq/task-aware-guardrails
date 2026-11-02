# -*- coding: utf-8 -*-
"""P2-v2 构建：以 (Action, Evidence) 为场景单位，放宽到 3–5 对/场景。

与 P2-v1 的区别
----------------
v1 的场景单位实际是 action（evidence 由 action 唯一决定），300 对只对应 17 个组合。
v2 显式把 evidence 作为场景维度：同一动作配 **两份真实且不同的证据包**，
场景数从 17 抬到 2×可用动作数，同时每个场景只保留 3–5 对，
避免"一个动作刷 96 对"的伪规模。

场景定义
--------
    scenario = (tool, args, evidence_variant)
证据变体只用**真实环境对象**构造：
    focused : 命中最高的 1–2 份文档 + 会话记录（自然检索结果）
    wide    : 该域全部文档截断到 6 份 + 会话记录（宽召回结果）
两者文本必然不同，且都真实存在于环境里。

标签
----
沿用 v1 的显式策略（EFFECT / TARGET / QUANTITY 三段谓词），
但**标签只由策略给出**，不看 ground_truth 是否包含：ground_truth 只用于确认"存在授权依据"。
每个场景额外记录 label_reason 与 evidence_source，便于逐条复核。
"""
import argparse
import collections
import copy
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from agentdojo.task_suite.load_suites import get_suite  # noqa: E402
import build_p2 as P  # noqa: E402

SUITES = ["banking", "slack", "travel", "workspace"]


def evidence_variants(suite, docs, fn, args):
    """返回 [(variant, text, sources)]。两份，文本必不同。"""
    tgt, q = P.target_and_quant(args)
    scored = []
    for did, text in docs:
        ntxt = P.norm(text)
        s = 0.0
        if P.usable_target(tgt) and P.norm(tgt) in ntxt:
            s += 2.0
        if q is not None and round(q, 2) in P.nums_in(text):
            s += 1.0
        scored.append((s, did, text))
    scored.sort(key=lambda x: (-x[0], x[1]))
    rec = "session record (retrieved this session): tool=%s args=%s" % (
        fn, json.dumps(args, sort_keys=True, ensure_ascii=False, default=str))
    BUDGET = 1500

    def pack(docs_):
        """先给会话记录留位置，再截断文档；否则长文档会把参数行挤掉，
        导致不同动作产生完全相同的证据文本（场景不再独立）。"""
        room = max(BUDGET - len(rec) - 2, 200)
        body = "\n\n".join(["[%s]\n%s" % (d, t) for d, t in docs_])[:room]
        return (body + "\n\n" + rec) if body else rec

    focused = [x for x in scored if x[0] > 0][:2]
    if not focused:
        focused = scored[:1]
    f_txt = pack([(d, t[:700]) for _, d, t in focused])

    wide = scored[:6]
    w_txt = pack([(d, t[:420]) for _, d, t in wide])

    out = [("focused", f_txt, [d for _, d, _ in focused])]
    seen_txt = [f_txt]
    if w_txt not in seen_txt:
        out.append(("wide", w_txt, [d for _, d, _ in wide]))
        seen_txt.append(w_txt)

    # 第四种：focused + 一份不相关文档（检索噪声的真实形态）
    distr = [x for x in scored if x[0] == 0][:1]
    if distr:
        d_txt = pack([(d, t[:700]) for _, d, t in focused]
                     + [(distr[0][1], distr[0][2][:420])])
        if d_txt not in seen_txt:
            out.append(("distracted", d_txt,
                        [d for _, d, _ in focused] + [distr[0][1]]))
            seen_txt.append(d_txt)

    # 第三种：只有结构化记录（账户/流水/频道/日程），不含文件与云盘正文。
    # 这是真实的一次检索结果（文件读取失败或未被召回的常见形态）。
    recs = [x for x in scored
            if not x[1].startswith(("file:", "drive:", "doc:", "cloud:"))][:6]
    if recs:
        r_txt = pack([(d, t[:420]) for _, d, t in recs])
        if r_txt not in seen_txt:
            out.append(("records", r_txt, [d for _, d, _ in recs]))
            seen_txt.append(r_txt)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "p2v2_pairs.jsonl"))
    ap.add_argument("--max-pairs-per-scenario", type=int, default=4)
    ap.add_argument("--max-scenarios", type=int, default=120)
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(os.path.join(ROOT, "data", "pab_rd.jsonl"),
                                        encoding="utf-8")]
    sp = json.load(open(os.path.join(ROOT, "data", "pab_rd_splits.json"), encoding="utf-8"))
    sid2task = {r["sid"]: (r["suite"], r["task_id"]) for r in rows}
    part = {}
    for k in ("train", "val", "test"):
        for sid in sp[k]:
            part[sid2task[sid]] = k

    scen = []      # 待评估的场景
    stats = collections.Counter()

    for suite in SUITES:
        s = get_suite("v1", suite)
        env = s.load_and_inject_default_environment({})
        docs = P.docs_for(suite, env)

        tasks = {}
        for tid, t in s.user_tasks.items():
            try:
                gt = t.ground_truth(copy.deepcopy(env))
            except Exception:
                stats["gt_fail"] += 1
                continue
            tasks[tid] = {"tid": tid, "prompt": t.PROMPT, "cls": type(t).__name__,
                          "part": part.get((suite, tid), "?"),
                          "calls": [(g.function, dict(g.args)) for g in gt]}

        # 收集写动作 + 授权它的任务
        acts = collections.defaultdict(lambda: {"allow": [], "fn": None, "args": None})
        for tid, v in tasks.items():
            for fn, args in v["calls"]:
                if P.effect_of(fn) == "READ":
                    continue
                key = (fn, json.dumps(args, sort_keys=True, default=str))
                lab, why = P.policy_A(v["prompt"], fn, args, "", docs)
                if lab == "ALLOW":
                    acts[key]["allow"].append((tid, v["part"], why))
                    acts[key]["fn"], acts[key]["args"] = fn, args
                    stats["allow_calls"] += 1
                else:
                    stats["gt_rejected"] += 1

        for key, act in acts.items():
            if not act["allow"]:
                continue
            fn, args = act["fn"], act["args"]
            allow_set = {t for t, _, _ in act["allow"]}
            # DENY 侧候选
            deny = []
            for tid, v in tasks.items():
                if tid in allow_set:
                    continue
                lab, why = P.policy_A(v["prompt"], fn, args, "", docs)
                if lab == "DENY":
                    deny.append((tid, v["part"], v["cls"], why))
            if not deny:
                continue
            for variant, ev_text, sources in evidence_variants(suite, docs, fn, args):
                sid = hashlib.sha1(("%s|%s|%s" % (fn, key[1], variant)).encode()).hexdigest()[:10]
                # 选 3–5 个 DENY 任务：同 part 优先，其次模板多样
                allow_parts = {p_ for _, p_, _ in act["allow"]}
                pools = collections.defaultdict(list)
                for d in sorted(deny, key=lambda x: (x[1] not in allow_parts, x[0])):
                    pools[d[3]].append(d)
                picked, seen_cls = [], collections.Counter()
                order_r = ["TARGET_MISMATCH", "EFFECT_NOT_REQUESTED"]
                while len(picked) < a.max_pairs_per_scenario:
                    progressed = False
                    for r in order_r:
                        while pools[r]:
                            d = pools[r].pop(0)
                            if seen_cls[d[2]] >= 1 and len(picked) < 2:
                                continue
                            picked.append(d)
                            seen_cls[d[2]] += 1
                            progressed = True
                            break
                        if progressed:
                            break
                    if not progressed:
                        break
                for tid, p_, cls, why in picked:
                    scen.append(dict(
                        suite=suite, scenario_id=sid, variant=variant,
                        tool=fn, args=args,
                        task_auth="%s/%s" % (suite, act["allow"][0][0]),
                        task_deny="%s/%s" % (suite, tid),
                        part_auth=act["allow"][0][1], part_deny=p_,
                        allow_reason=act["allow"][0][2], deny_reason=why,
                        evidence=ev_text, evidence_source=sources,
                        action=P.render_action(fn, args),
                        prompt_auth=tasks[act["allow"][0][0]]["prompt"],
                        prompt_deny=tasks[tid]["prompt"],
                        cls_auth=tasks[act["allow"][0][0]]["cls"], cls_deny=cls,
                    ))

    # 场景去重与排序：strict 优先，其次动作多样
    order = {"test": 0, "val": 1, "train": 2}
    scen.sort(key=lambda r: (max(order[r["part_auth"]], order[r["part_deny"]]),
                             r["scenario_id"], r["task_deny"]))
    by_scen = collections.OrderedDict()
    for r in scen:
        by_scen.setdefault(r["scenario_id"], []).append(r)
    keep_scen = list(by_scen)[: a.max_scenarios]
    by_scen = {k: by_scen[k] for k in keep_scen}

    final, pairs = [], []
    for sid, rs in by_scen.items():
        base = rs[0]
        for r in rs:
            pid = "p2v2|%s|%s" % (sid, r["task_deny"])
            for role, task, lab, why, p_ in (
                    ("positive", r["task_auth"], "ALLOW", r["allow_reason"], r["part_auth"]),
                    ("negative", r["task_deny"], "DENY", r["deny_reason"], r["part_deny"])):
                final.append(dict(
                    pair_id=pid, pair_role=role, scenario_id=sid, suite=r["suite"],
                    variant=r["variant"], part_auth=r["part_auth"], part_deny=r["part_deny"],
                    task_id=task, task_cls=r["cls_auth"] if role == "positive" else r["cls_deny"],
                    instruction=r["prompt_auth"] if role == "positive" else r["prompt_deny"],
                    history=r["evidence"], current_action=r["action"],
                    action_id=hashlib.sha1(r["action"].encode()).hexdigest()[:10],
                    evidence_id=hashlib.sha1(r["evidence"].encode()).hexdigest()[:10],
                    label=lab, label_reason=why, tool=r["tool"],
                    evidence_source=r["evidence_source"]))
            pairs.append(dict(pair_id=pid, scenario_id=sid, suite=r["suite"],
                              variant=r["variant"], action_id=final[-1]["action_id"],
                              evidence_id=final[-1]["evidence_id"],
                              task_auth=r["task_auth"], task_deny=r["task_deny"],
                              part_auth=r["part_auth"], part_deny=r["part_deny"],
                              deny_reason=r["deny_reason"]))

    # ---- 统计
    def tier(q):
        ps = {q["part_auth"], q["part_deny"]}
        if ps == {"test"}:
            return "strict_test"
        if ps <= {"val", "test"}:
            return "unseen"
        return "contains_train"

    tiers = collections.Counter(tier(q) for q in pairs)
    n_scen_total = len({q["scenario_id"] for q in pairs})
    n_act = len({q["action_id"] for q in pairs})
    print("场景 %d（其中 strict_test %d），配对 %d，记录 %d，不同 action %d"
          % (n_scen_total, len({q["scenario_id"] for q in pairs if tier(q) == "strict_test"}),
             len(pairs), len(final), n_act), flush=True)
    print("分层: %s" % dict(tiers), flush=True)
    print("场景 × 域: %s" % dict(collections.Counter(q["suite"] for q in
                                                     {q["scenario_id"]: q for q in pairs}.values())),
          flush=True)
    print("每场景配对数分布: %s"
          % dict(collections.Counter(collections.Counter(q["scenario_id"] for q in pairs).values())),
          flush=True)
    print("证据变体: %s" % dict(collections.Counter(q["variant"] for q in pairs)), flush=True)
    print("负例理由: %s" % dict(collections.Counter(q["deny_reason"] for q in pairs)), flush=True)

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        for r in final:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    h = hashlib.sha256(open(a.out, "rb").read()).hexdigest()
    idx = {"n_scenarios": n_scen_total, "n_pairs": len(pairs), "n_records": len(final),
           "n_actions": n_act, "tiers": dict(tiers),
           "pairs_per_scenario": dict(collections.Counter(
               collections.Counter(q["scenario_id"] for q in pairs).values())),
           "sha256": h, "frozen": True,
           "note": "构建后冻结；模型评测前不得按成绩筛选样本"}
    json.dump({"index": idx, "pairs": pairs, "stats": dict(stats)},
              open(os.path.join(ROOT, "data", "p2v2_index.json"), "w"),
              ensure_ascii=False, indent=1)
    print("\nsha256 = %s" % h, flush=True)
    print("-> %s" % a.out, flush=True)


if __name__ == "__main__":
    main()
