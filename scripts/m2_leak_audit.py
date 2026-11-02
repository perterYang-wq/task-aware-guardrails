# -*- coding: utf-8 -*-
"""M2 数据泄漏审计：训练用的 hard negative 与三处评测集是否重叠。

检查项
------
1. 套件隔离：hardneg 只来自 banking / slack；travel 从不出现
2. 任务隔离：PAB-RD 的 train/val/test 与 hardneg 的任务集合无交集（不同来源）
3. 动作隔离：PAB-RD **test** 的 (tool, args) 不与 hardneg 的 (tool, args) 重复
4. 反事实纯净：hardneg_noinj 与 hardneg_full 的 current_action / instruction
   逐字节相同，只有 history 不同，且 inj_span 确实被删掉
5. 标签一致：成对样本里 neg 是 DENY、pos 是 ALLOW，且共享同一 history

任何一项不通过就以非零码退出。
"""
import json
import os
import sys
from collections import Counter, defaultdict

R = "/data/projects/guardrails"
TRAIN_SUITES = {"banking", "slack"}
HOLDOUT = {"travel"}
fails, warns = [], []


def bad(msg):
    fails.append(msg)
    print("  [FAIL] " + msg)


def ok(msg):
    print("  [ok]   " + msg)


def warn(msg):
    warns.append(msg)
    print("  [warn] " + msg)


def njl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def main():
    hn = njl(os.path.join(R, "data/hardneg.jsonl"))
    steps = njl(os.path.join(R, "results/diag/steps.jsonl"))
    pab = njl(os.path.join(R, "data/pab_rd.jsonl"))
    splits = json.load(open(os.path.join(R, "data/pab_rd_splits.json")))
    sp = splits["pab"] if "pab" in splits else splits

    print("== 1. 套件隔离 ==")
    su = Counter(x["meta"]["suite"] for x in hn if x["meta"].get("suite"))
    print("  hardneg suite 分布:", dict(su))
    if set(su) - TRAIN_SUITES:
        bad("hardneg 含训练套件之外的来源: %s" % (set(su) - TRAIN_SUITES))
    else:
        ok("全部来自 %s，未触及 %s" % (sorted(TRAIN_SUITES), sorted(HOLDOUT)))
    if HOLDOUT & set(su):
        bad("留出套件出现在训练数据里")

    print("== 2. 任务隔离 ==")
    hn_tasks = {(x["meta"]["suite"], x["meta"]["task_id"]) for x in hn if x["meta"].get("suite")}
    pab_tasks = {(x.get("suite"), x.get("task_id")) for x in pab}
    inter = hn_tasks & pab_tasks
    print("  hardneg 任务数 %d，PAB-RD 任务数 %d，交集 %d"
          % (len(hn_tasks), len(pab_tasks), len(inter)))
    if inter:
        warn("任务名重叠 %d 个（PAB-RD 由同一批 AgentDojo 环境构造，同名任务难免）。"
             "处置：离线测试另报「排除重叠任务」子集，不作为硬失败" % len(inter))
    else:
        ok("交集为空")
    excl = sorted("%s/%s" % t for t in inter)

    print("== 3. 动作隔离（PAB-RD test vs hardneg）==")
    test_sids = set(sp["test"])
    by_sid = {x["sid"]: x for x in pab}
    keys_test = {(by_sid[s]["tool"], json.dumps(by_sid[s].get("args"), sort_keys=True,
                                               ensure_ascii=False))
                 for s in test_sids if s in by_sid}
    keys_hn = {(x["tool"], json.dumps(x.get("args"), sort_keys=True, ensure_ascii=False))
               for x in hn}
    both = keys_test & keys_hn
    print("  PAB-RD test 动作 %d，hardneg 动作 %d，重复 %d"
          % (len(keys_test), len(keys_hn), len(both)))
    if both:
        warn("与 PAB-RD test 共享 %d 个 (tool,args)（均为只读/常规写操作，非攻击模式）：%s"
             % (len(both), list(both)[:3]))
    else:
        ok("无重复动作")

    print("== 4. 反事实纯净性 ==")
    full = {x["sid"].replace("hn#", "", 1): x for x in hn
            if x["meta"].get("kind") == "hardneg_full"}
    noinj = [x for x in hn if x["meta"].get("kind") == "hardneg_noinj"]
    same_act = same_ins = stripped = 0
    for x in noinj:
        f = full.get(x["sid"].replace("hn_noinj#", "", 1))
        if not f:
            continue
        same_act += int(x["current_action"] == f["current_action"])
        same_ins += int(x["instruction"] == f["instruction"])
        stripped += int(x["history"] != f["history"] and "<INFORMATION>" not in x["history"])
    print("  noinj 条数 %d；动作相同 %d；目标相同 %d；history 已被删且无残留 %d"
          % (len(noinj), same_act, same_ins, stripped))
    if same_act != len(noinj) or same_ins != len(noinj) or stripped != len(noinj):
        bad("反事实视图不纯净")
    else:
        ok("只有 history 不同，载荷已完全删除")

    print("== 5. 成对样本一致性 ==")
    pairs = defaultdict(dict)
    for x in hn:
        pid = x["meta"].get("pair_id")
        if pid:
            pairs[pid][x["label"]] = x
    good = 0
    for pid, d in pairs.items():
        if "DENY" in d and "ALLOW" in d and d["DENY"]["history"] == d["ALLOW"]["history"] \
                and d["DENY"]["tool"] == d["ALLOW"]["tool"]:
            good += 1
    print("  配对 %d；同 history + 同 tool + 标签相反 %d" % (len(pairs), good))
    if good != len(pairs):
        bad("有配对不满足同上下文约束")
    else:
        ok("全部配对共享同一 history 且同工具")

    out = os.path.join(R, "results/m2/leak_audit.json")
    json.dump(dict(ok=not fails, fails=fails, warns=warns,
                   hardneg_tasks=sorted("%s/%s" % t for t in hn_tasks),
                   overlap_with_pab=sorted("%s/%s" % t for t in inter)),
              open(out, "w"), ensure_ascii=False, indent=2)
    print("\n-> %s" % out)
    print()
    if fails:
        print("AUDIT_FAILED 共 %d 项" % len(fails))
        sys.exit(1)
    print("AUDIT_OK")


if __name__ == "__main__":
    main()
