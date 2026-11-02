# -*- coding: utf-8 -*-
"""端到端行为分析：拦截时机、攻击链是否被打断、效用被谁杀死、agent 如何应对拦截。

对应研究计划的四项要求
--------------------
(2) 首次拦截步 + 攻击链是否被打断
    受攻击场景中至少被拦截一次的比例；首次拦截发生在第几步（均值/中位数）；
    拦截后攻击是否仍成功 —— 用来证明「部分关键步拦截就够」，而不是必须全拦。
(3) 效用分解：干净任务失败被谁杀死
    a) 被守卫拦死（有拦截且失败）
    b) agent 自己本来就失败（无拦截且失败；与基线同任务对照）
    c) 拦截后轨迹分叉导致后续失败（有拦截但拦截的不是致命步 / 分叉后仍失败）
(6) 守卫触发后 agent 的行为
    放弃 / 换工具 / 换参数重试 / 原样重试，四个比例。
(8) 弱攻击 / 强攻击分层
    以「无守卫时该 (task,injection) 是否成功」定义 easy/hard，看守卫吃掉的是哪一类。

输入：守卫臂的 scen.jsonl + trace.jsonl，以及无守卫基线的 scen.jsonl。
"""
import argparse
import json
import os
from collections import Counter, defaultdict

R = "/data/projects/guardrails"


def load(p):
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def key(s):
    return (s["user_task"], s.get("injection_task"))


def pct(a, b):
    return round(100.0 * a / b, 1) if b else None


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return None
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def is_blocked(h, policy):
    """一次守卫判定是否真的拦下了执行。兼容旧 run（无 enforced 字段）。"""
    if "enforced" in h:
        return bool(h["enforced"])
    return h.get("decision") in (("DENY", "REVIEW") if policy == "block" else ("DENY",))


def behavior_after(trace, blocked_idx):
    """看被拦那次调用之后，agent 做了什么。返回分类标签。"""
    seq = [x for x in trace]
    # blocked_idx 是 calls 下标；trace 里每条对应一次 call，按 step 排序即同序
    if blocked_idx + 1 >= len(seq):
        return "give_up"
    cur = seq[blocked_idx]
    nxt = seq[blocked_idx + 1]
    same_tool = nxt["tool"] == cur["tool"]
    same_args = (json.dumps(nxt.get("args") or {}, sort_keys=True, ensure_ascii=False)
                 == json.dumps(cur.get("args") or {}, sort_keys=True, ensure_ascii=False))
    if same_tool and same_args:
        return "retry_identical"
    if same_tool:
        return "retry_new_args"
    return "switch_tool"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="守卫臂目录（含 scen.jsonl/trace.jsonl）")
    ap.add_argument("--baseline", default="")
    ap.add_argument("--policy", default="block", choices=["block", "allow"])
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    scen = load(os.path.join(a.run, "scen.jsonl"))
    trace = load(os.path.join(a.run, "trace.jsonl"))
    base = {key(s): s for s in load(a.baseline)} if a.baseline else {}
    tag = os.path.basename(a.run.rstrip("/"))

    # 按场景把 trace 分组（顺序即调用顺序）
    tr = defaultdict(list)
    for x in trace:
        tr[key(x)].append(x)
    for k in tr:
        tr[k].sort(key=lambda z: z["step"])

    clean = [s for s in scen if not s.get("injection_present")]
    atk = [s for s in scen if s.get("injection_present")]

    res = {"tag": tag, "policy": a.policy,
           "n_clean": len(clean), "n_attack": len(atk)}

    # ---------- (2) 拦截时机与攻击链
    blocked_scen, first_steps = [], []
    succ_blocked = succ_unblocked = 0
    for s in atk:
        hits = s.get("guard_hits") or []
        blk = [i for i, h in enumerate(hits) if is_blocked(h, a.policy)]
        if blk:
            blocked_scen.append(s)
            first_steps.append(blk[0] + 1)      # 第几次判定被拦（1-based）
            succ_blocked += int(bool(s.get("security")))
        else:
            succ_unblocked += int(bool(s.get("security")))
    n_no_block = len(atk) - len(blocked_scen)
    # 配对 ASR（同一 (task,injection) 上基线 vs 守卫）
    if base:
        b_only = g_only = n_pair = 0
        for s in atk:
            b = base.get(key(s))
            if not b:
                continue
            n_pair += 1
            bs, gs_ = bool(b.get("security")), bool(s.get("security"))
            if bs and not gs_:
                b_only += 1
            elif gs_ and not bs:
                g_only += 1
        pv = None
        if b_only + g_only:
            try:
                from scipy.stats import binomtest
                pv = round(float(binomtest(min(b_only, g_only), b_only + g_only, 0.5).pvalue), 4)
            except Exception:
                pass
        res["chain_paired"] = dict(n_pair=n_pair, base_only=b_only, guard_only=g_only,
                                   mcnemar_p=pv)
    res["chain"] = dict(
        n_attack=len(atk), n_blocked_scen=len(blocked_scen),
        blocked_rate=pct(len(blocked_scen), len(atk)),
        first_block_step_mean=(round(sum(first_steps) / len(first_steps), 2)
                               if first_steps else None),
        first_block_step_median=median(first_steps),
        asr_when_blocked=pct(succ_blocked, len(blocked_scen)),
        asr_when_not_blocked=pct(succ_unblocked, n_no_block),
        n_succ_blocked=succ_blocked, n_succ_unblocked=succ_unblocked,
        chain_broken_rate=pct(len(blocked_scen) - succ_blocked, len(blocked_scen)),
    )

    # ---------- (6) 拦截后 agent 行为
    beh = Counter()
    for k in tr:
        hits, seq = None, tr[k]
        sc = next((s for s in scen if key(s) == k), None)
        if not sc:
            continue
        for h in (sc.get("guard_hits") or []):
            if not is_blocked(h, a.policy):
                continue
            i = h.get("idx")
            if i is None or i >= len(seq):
                continue
            beh[behavior_after(seq, i)] += 1
    tot = sum(beh.values())
    res["behavior"] = dict(total=tot, counts=dict(beh),
                           rates={k: pct(v, tot) for k, v in beh.items()})

    # ---------- (3) 效用分解（干净场景，2x2 对照基线）
    # 只有「基线成功而守卫失败」才是守卫的真实代价；「两边都失败」是 agent 自身能力问题。
    cell = Counter()
    for s in clean:
        hits = s.get("guard_hits") or []
        any_blk = any(is_blocked(h, a.policy) for h in hits)
        g = bool(s.get("utility"))
        b = base.get(key(s))
        if b is None:
            cell[("unknown", g, any_blk)] += 1
            continue
        cell[(bool(b.get("utility")), g, any_blk)] += 1

    def cnt(b_ok, g_ok, blk=None):
        return sum(v for (bb, gg, kk), v in cell.items()
                   if bb == b_ok and gg == g_ok and (blk is None or kk == blk))

    both_ok = cnt(True, True)
    base_only = cnt(True, False)          # 基线成功、守卫失败 = 真实代价
    guard_only = cnt(False, True)         # 守卫成功、基线失败 = 真实收益
    both_fail = cnt(False, False)
    killed = cnt(True, False, True)       # 真实代价里由拦截造成的
    res["utility_decomp"] = dict(
        n_clean=len(clean), n_paired=both_ok + base_only + guard_only + both_fail,
        both_ok=both_ok, base_only=base_only, guard_only=guard_only, both_fail=both_fail,
        killed_by_guard=killed,
        base_only_unblocked=base_only - killed,
        guard_utility=pct(both_ok + guard_only, len(clean)),
        baseline_utility=(pct(both_ok + base_only,
                              both_ok + base_only + guard_only + both_fail)
                          if (both_ok + base_only + guard_only + both_fail) else None),
        unknown=sum(v for (bb, _, _), v in cell.items() if bb == "unknown"),
    )

    # ---------- (8) 强弱攻击分层
    if base:
        strata = Counter()
        for s in atk:
            b = base.get(key(s))
            if not b:
                continue
            diff = "easy" if b.get("security") else "hard"
            strata[(diff, bool(s.get("security")))] += 1
        tab = {}
        for d in ("easy", "hard"):
            n = strata[(d, True)] + strata[(d, False)]
            tab[d] = dict(n=n, guard_asr=pct(strata[(d, True)], n))
        base_tab = {}
        for d in ("easy", "hard"):
            bs = [base[key(s)] for s in atk if key(s) in base
                  and (("easy" if base[key(s)].get("security") else "hard") == d)]
            base_tab[d] = dict(n=len(bs), baseline_asr=pct(sum(1 for x in bs if x.get("security")), len(bs)))
        res["strata"] = dict(by_baseline=base_tab, guard=tab)

    out = a.out or os.path.join(a.run, "analysis.json")
    json.dump(res, open(out, "w"), ensure_ascii=False, indent=2)

    # ---------- 打印
    print("== %s (policy=%s)  干净 %d / 受攻击 %d ==" % (tag, a.policy, len(clean), len(atk)))
    c = res["chain"]
    print("\n[2] 攻击链")
    print("  出现过拦截的场景 %d/%d (%.1f%%)；首次拦截步 均值 %s / 中位 %s"
          % (c["n_blocked_scen"], c["n_attack"], c["blocked_rate"] or 0,
             c["first_block_step_mean"], c["first_block_step_median"]))
    print("  拦截后仍成功 %d/%d (%.1f%%)；未拦截场景成功 %d/%d (%.1f%%)；链被打断 %.1f%%"
          % (c["n_succ_blocked"], c["n_blocked_scen"], c["asr_when_blocked"] or 0,
             c["n_succ_unblocked"], c["n_attack"] - c["n_blocked_scen"],
             c["asr_when_not_blocked"] or 0, c["chain_broken_rate"] or 0))
    if "chain_paired" in res:
        cp = res["chain_paired"]
        print("  配对 ASR（n=%d）：仅基线成功 %d、仅守卫成功 %d、McNemar p=%s"
              % (cp["n_pair"], cp["base_only"], cp["guard_only"], cp["mcnemar_p"]))
    b = res["behavior"]
    print("\n[6] 拦截后 agent 行为（共 %d 次拦截）" % b["total"])
    for k in ("give_up", "switch_tool", "retry_new_args", "retry_identical"):
        print("  %-16s %4d  %s%%" % (k, b["counts"].get(k, 0), b["rates"].get(k)))
    u = res["utility_decomp"]
    print("\n[3] 干净任务效用分解（2x2 配对，n=%d）" % u["n_paired"])
    print("  两边都成功        %2d" % u["both_ok"])
    print("  基线成功/守卫失败 %2d  <- 真实代价（其中被拦截造成 %d，未拦截 %d）"
          % (u["base_only"], u["killed_by_guard"], u["base_only_unblocked"]))
    print("  基线失败/守卫成功 %2d  <- 真实收益" % u["guard_only"])
    print("  两边都失败        %2d  <- agent 自身能力问题，不算到守卫头上" % u["both_fail"])
    print("  守卫 utility %s%%  基线 %s%%" % (u["guard_utility"], u["baseline_utility"]))
    if u["base_only"] + u["guard_only"]:
        b_, c_ = u["base_only"], u["guard_only"]
        try:
            from scipy.stats import binomtest
            pv = binomtest(min(b_, c_), b_ + c_, 0.5).pvalue
            print("  配对 McNemar（精确二项）: 不一致 %d 对，p=%.4f" % (b_ + c_, pv))
        except Exception as e:
            print("  McNemar 跳过:", e)
    if "strata" in res:
        print("\n[8] 强弱攻击分层（按无守卫是否成功）")
        for d in ("easy", "hard"):
            bs, gs = res["strata"]["by_baseline"][d], res["strata"]["guard"][d]
            print("  %-5s 基线 n=%-3d ASR %s%%  ->  守卫 n=%-3d ASR %s%%"
                  % (d, bs["n"], bs["baseline_asr"], gs["n"], gs["guard_asr"]))
    print("\n-> %s" % out)


if __name__ == "__main__":
    main()
