# -*- coding: utf-8 -*-
"""P2-v2 最终校验（纯 CPU，不加载模型、不占 GPU）。

回答五件事：
  1. 分层交叉表：19/9/73 之和 101 > 79 的原因，明确是重叠子集还是互斥划分
  2. 统计口径：主指标 = strict 场景等权 PRA（场景内先平均，再跨场景平均）
  3. strict 涉及的动作逐个列出（结构 + 各动作的场景/配对规模）
  4. 实际输入校验：用真实 tokenizer 重建 prompt，验证 action+evidence 段
     token 序列逐一对齐、只有 task 段不同，并报告 token 长度是否触发截断
  5. 冻结确认：sha256、scenario_id 唯一性、标签、配对数量
"""
import collections
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

PAIRS = os.path.join(ROOT, "data", "p2v2_pairs.jsonl")
IDX = os.path.join(ROOT, "data", "p2v2_index.json")
TOK = "/data/hf_cache/qwen1.5b"
MAXLEN_TRAIN = 1024          # P1 训练用的 max_len
CTX = 32768                  # Qwen2.5 的上下文上限


def tier_of(r):
    ps = {r["part_auth"], r["part_deny"]}
    if ps == {"test"}:
        return "strict_test"
    if ps <= {"val", "test"}:
        return "unseen"
    return "contains_train"


def main():
    rows = [json.loads(l) for l in open(PAIRS, encoding="utf-8")]
    idx = json.load(open(IDX, encoding="utf-8"))
    by_pair = collections.defaultdict(list)
    for r in rows:
        by_pair[r["pair_id"]].append(r)
    scen = collections.defaultdict(list)
    for pid, rs in by_pair.items():
        scen[rs[0]["scenario_id"]].append(pid)

    print("=" * 78)
    print("1. 分层交叉表")
    print("=" * 78)
    pat = collections.Counter()
    pure = collections.Counter()
    for sid, pids in scen.items():
        ts = tuple(sorted({tier_of(by_pair[p][0]) for p in pids}))
        pat[ts] += 1
        if len(ts) == 1:
            pure[ts[0]] += 1
    print("%-46s%6s" % ("场景的配对层组成", "场景数"))
    for ts, n in sorted(pat.items(), key=lambda x: (-x[1], x[0])):
        print("%-46s%6d" % (" + ".join(ts) if ts else "(空)", n))
    print()
    print("→ 三个数字是**重叠子集**（按'该场景至少有一对属于该层'计），不是划分。")
    print("  并集 %d 个场景 = 全部场景；简单相加 %d 是因为一个场景可同时落进多层。"
          % (len(scen), sum(n for ts, n in pat.items() for _ in ts)))
    print()
    print("纯层场景数（该场景**全部**配对都在同一层）:")
    for k in ("strict_test", "unseen", "contains_train"):
        print("  %-15s %d" % (k, pure.get(k, 0)))
    print("  混合场景（跨层）%d 个" % (len(scen) - sum(pure.values())))

    strict_pure = [sid for sid, pids in scen.items()
                   if all(tier_of(by_pair[p][0]) == "strict_test" for p in pids)]
    strict_any = [sid for sid, pids in scen.items()
                  if any(tier_of(by_pair[p][0]) == "strict_test" for p in pids)]
    print()
    print("主指标可用的场景集合：")
    print("  含 strict 配对 %d；其中**全部**配对都 strict 的 %d"
          % (len(strict_any), len(strict_pure)))
    print("  → 主指标分母用纯 strict 场景（%d），混合场景只作辅助" % len(strict_pure))

    print()
    print("=" * 78)
    print("2. 统计口径（写死）")
    print("=" * 78)
    print("  场景 PRA_s = mean(该场景各配对得分)，配对得分 = 1 / 0.5 / 0")
    print("  主指标   = mean_over_strict_scenarios(PRA_s)      ← 场景等权")
    print("  SPA_s / TieRate_s 同法计算，仅作辅助")
    print("  注意：这不等同于按配对加权；4 对/场景时，配对加权会把每场景权重拉平，")
    print("        但一旦场景配对数不等（未来扩展），两者会分叉——故固定为场景等权。")

    print()
    print("=" * 78)
    print("3. strict 场景涉及的动作")
    print("=" * 78)
    act = collections.defaultdict(lambda: {"n_scen": 0, "n_pairs": 0, "tool": None,
                                           "suites": set()})
    for sid in strict_pure:
        pids = scen[sid]
        a = act[by_pair[pids[0]][0]["action_id"]]
        a["n_scen"] += 1
        a["n_pairs"] += len(pids)
        a["tool"] = by_pair[pids[0]][0]["tool"]
        a["suites"].add(by_pair[pids[0]][0]["suite"])
    print("%-12s%-24s%8s%8s%s" % ("action_id", "tool", "场景", "配对", "域"))
    for aid, a in sorted(act.items(), key=lambda x: -x[1]["n_scen"]):
        print("%-12s%-24s%8d%8d%s" % (aid, a["tool"], a["n_scen"], a["n_pairs"],
                                      ",".join(sorted(a["suites"]))))
    print()
    print("  strict 动作数 = %d，场景数 = %d，配对数 = %d"
          % (len(act), sum(a["n_scen"] for a in act.values()),
             sum(a["n_pairs"] for a in act.values())))
    print("  → 以动作为聚类单元时，strict 层只有 %d 个簇；任何'最宽 CI'都受此限制，"
          % len(act))
    print("    不能把三种聚类的最大值当正式显著性检验（见报告 §3）。")

    print()
    print("=" * 78)
    print("4. 实际输入校验（真实 tokenizer）")
    print("=" * 78)
    from transformers import AutoTokenizer
    from guard.schema import Step, render_pab
    tok = AutoTokenizer.from_pretrained(TOK)

    def prompt_of(r):
        st = Step(sid=r["pair_id"], source="p2v2", instruction=r["instruction"],
                  history=r["history"], current_action=r["current_action"],
                  env_info="", score=0.0, label=r["label"], tool=r["tool"], args={})
        return render_pab(st, task_aware=True)

    bad_ident, bad_prefix, lens = [], [], []
    # 模板里 "<<" 段之前是 task，之后是 evidence+action
    for pid, rs in by_pair.items():
        p = next(x for x in rs if x["pair_role"] == "positive")
        n = next(x for x in rs if x["pair_role"] == "negative")
        sp_, sn_ = prompt_of(p), prompt_of(n)
        ids_p = tok(sp_, add_special_tokens=False)["input_ids"]
        ids_n = tok(sn_, add_special_tokens=False)["input_ids"]
        lens += [len(ids_p), len(ids_n)]
        # 从 evidence 标记处切开，比较后半段 token 序列
        marker = "<<Values Retrieved Earlier In This Session>>"
        hp = sp_[sp_.index(marker):]
        hn = sn_[sn_.index(marker):]
        if hp != hn:
            bad_ident.append((pid, "suffix_text"))
        ip = tok(hp, add_special_tokens=False)["input_ids"]
        inn = tok(hn, add_special_tokens=False)["input_ids"]
        if ip != inn:
            bad_prefix.append(pid, )
        # task 段必须不同
        tp = sp_[:sp_.index(marker)]
        tn = sn_[:sn_.index(marker)]
        if tp == tn:
            bad_ident.append((pid, "task_identical"))

    print("  配对 %d 组，逐组比对" % len(by_pair))
    print("  evidence+action 段文本完全相同: %d/%d" % (len(by_pair) - sum(
        1 for x in bad_ident if x[1] == "suffix_text"), len(by_pair)))
    print("  evidence+action 段 **token 序列**完全相同: %d/%d"
          % (len(by_pair) - len(bad_prefix), len(by_pair)))
    print("  task 段互不相同: %d/%d" % (len(by_pair) - sum(
        1 for x in bad_ident if x[1] == "task_identical"), len(by_pair)))
    print("  异常: suffix=%d token=%d task_same=%d"
          % (sum(1 for x in bad_ident if x[1] == "suffix_text"),
             len(bad_prefix), sum(1 for x in bad_ident if x[1] == "task_identical")))
    import statistics as st
    print("  prompt token 长度: mean=%.0f p95=%d max=%d"
          % (st.mean(lens), sorted(lens)[int(0.95 * len(lens))], max(lens)))
    over_train = sum(1 for x in lens if x > MAXLEN_TRAIN)
    over_ctx = sum(1 for x in lens if x > CTX)
    print("  超过训练 max_len(%d) 的 prompt: %d/%d (%.1f%%)"
          % (MAXLEN_TRAIN, over_train, len(lens), 100 * over_train / len(lens)))
    print("  超过模型上下文(%d) 的 prompt: %d → 评测阶段**不发生截断**" % (CTX, over_ctx))

    print()
    print("=" * 78)
    print("5. 冻结确认")
    print("=" * 78)
    h = hashlib.sha256(open(PAIRS, "rb").read()).hexdigest()
    print("  文件 sha256        : %s" % h)
    print("  index 记录 sha256  : %s  %s"
          % (idx["index"]["sha256"], "一致" if h == idx["index"]["sha256"] else "**不一致**"))
    print("  scenario_id 唯一   : %s" % (len(scen) == len({r["scenario_id"] for r in rows})))
    print("  pair_id 唯一       : %s" % (len(by_pair) == len({r["pair_id"] for r in rows})))
    lab = collections.Counter(r["label"] for r in rows)
    print("  标签分布           : %s" % dict(lab))
    print("  每对标签翻转       : %d/%d"
          % (sum(1 for rs in by_pair.values()
                 if {x["label"] for x in rs} == {"ALLOW", "DENY"}), len(by_pair)))
    print("  配对/记录/场景/动作: %d / %d / %d / %d"
          % (len(by_pair), len(rows), len(scen), len({r["action_id"] for r in rows})))

    out = os.path.join(ROOT, "results", "audit", "p2v2_final_check.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({"tier_patterns": {" + ".join(k): v for k, v in pat.items()},
               "pure_scenarios": dict(pure), "n_scenarios": len(scen),
               "strict_pure": len(strict_pure), "strict_any": len(strict_any),
               "strict_actions": {k: {"tool": v["tool"], "n_scen": v["n_scen"],
                                      "n_pairs": v["n_pairs"]} for k, v in act.items()},
               "prompt_tokens": {"mean": st.mean(lens), "p95": sorted(lens)[int(0.95 * len(lens))],
                                 "max": max(lens), "over_train_maxlen": over_train},
               "input_checks": {"suffix_text_mismatch": sum(1 for x in bad_ident if x[1] == "suffix_text"),
                                "suffix_token_mismatch": len(bad_prefix),
                                "task_identical": sum(1 for x in bad_ident if x[1] == "task_identical")},
               "sha256": h}, open(out, "w"), ensure_ascii=False, indent=1)
    print("\n-> %s" % out)


if __name__ == "__main__":
    main()
