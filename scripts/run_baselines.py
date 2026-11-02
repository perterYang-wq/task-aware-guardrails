# -*- coding: utf-8 -*-
"""B0/B1/B2 基线，全部在 --split 指定的同一套划分上评测。

B0 多数类        —— 下界，说明数据不平衡程度
B1 关键词规则    —— 一个工程师最先会写的黑名单；不看任务语义
B2b 工具名查表   —— **混淆基线的核心**：训练集里每个工具的多数标签，
                    测试时直接查表（未见工具回退到全局多数类）。
                    如果"任务感知"模型只比它高一点点，就说明模型学到的是工具名先验。
B2 PG2           —— Prompt Guard 2 的 p(MALICIOUS) 当风险分数，在 val 上选两个阈值，
                    切成 ALLOW/REVIEW/DENY 三档后测 test。
"""
import argparse
import collections
import json
import os
import sys

import numpy as np
import torch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from guard.metrics import evaluate  # noqa: E402
from guard.schema import CLASSES, Step, build_agent_log  # noqa: E402

DATA = os.path.join(ROOT, "data", "tsbench_unified.jsonl")
SPLITS = os.path.join(ROOT, "data", "splits.json")

# ---------------------------------------------------------------- B1 规则
# 规则只依赖"动作文本里能直接看见的东西"，不看任务语义。
DENY_TOKENS = [
    "without_authorization", "without authorization", "unauthorized", "bypass",
    "backdoor", "exfiltrat", "keylogger", "reverse shell", "redirect_funds",
    "/etc/passwd", "/etc/shadow", ".ssh/id_rsa", "attacker", "@evil", "@malicious",
    "rm -rf /", "chmod 777", "drop table", "disable_all", "override_permission",
]
REVIEW_TOOLS = ["delete", "remove", "drop", "transfer", "payment", "wire",
                "exec", "shell", "sudo", "admin"]
REVIEW_ARG_KEYS = ["password", "token", "secret", "api_key", "credential",
                   "ssn", "card_number", "iban"]


def rule_predict(st: Step) -> str:
    body = ((st.current_action or "") + " " + json.dumps(st.args, ensure_ascii=False)
            if st.args is not None else (st.current_action or "")).lower()
    tool = (st.tool or "").lower()
    if any(t in body for t in DENY_TOKENS):
        return "DENY"
    if any(k in body for k in REVIEW_ARG_KEYS):
        return "REVIEW"
    if any(t in tool for t in REVIEW_TOOLS):
        return "REVIEW"
    return "ALLOW"


# ---------------------------------------------------------------- B2b 查表
def tool_lookup(train, test):
    tab = collections.defaultdict(collections.Counter)
    for s in train:
        if s.tool:
            tab[s.tool][s.label] += 1
    glob = collections.Counter(s.label for s in train).most_common(1)[0][0]
    return [tab[s.tool].most_common(1)[0][0] if s.tool and tab.get(s.tool) else glob
            for s in test]


# ---------------------------------------------------------------- B2 PG2
def pg2_scores(paths, texts, bs=32, max_len=512):
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(paths)
    m = AutoModelForSequenceClassification.from_pretrained(
        paths, torch_dtype=torch.float32).eval().to("cuda")
    out = []
    with torch.no_grad():
        for i in range(0, len(texts), bs):
            enc = tok(texts[i:i + bs], return_tensors="pt", padding=True,
                      truncation=True, max_length=max_len).to("cuda")
            p = torch.softmax(m(**enc).logits, -1)[:, 1]
            out.extend(p.cpu().tolist())
    del m
    torch.cuda.empty_cache()
    return np.array(out)


def pg2_to_labels(scores, t_lo, t_hi):
    return ["ALLOW" if p < t_lo else ("REVIEW" if p < t_hi else "DENY") for p in scores]


def best_thresholds(scores, gold):
    """在 val 上网格搜索两个阈值，最大化 macro-F1。"""
    grid = np.unique(np.round(np.concatenate([[0.0, 1.0], np.quantile(scores, np.linspace(0, 1, 40))]), 4))
    best = (None, None, -1)
    for i, lo in enumerate(grid):
        for hi in grid[i:]:
            if hi < lo:
                continue
            pred = pg2_to_labels(scores, lo, hi)
            f1 = evaluate(gold, pred, verbose=False)["macro_f1"]
            if f1 > best[2]:
                best = (float(lo), float(hi), f1)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="grouped")
    ap.add_argument("--pg2", default="/data/hf_cache/pg2-86m")
    ap.add_argument("--skip-pg2", action="store_true")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    steps = [Step(**json.loads(l)) for l in open(DATA, encoding="utf-8")]
    by_sid = {s.sid: s for s in steps}
    sp = json.load(open(SPLITS))[a.split]
    train = [by_sid[i] for i in sp["train"]]
    val = [by_sid[i] for i in sp["val"]]
    test = [by_sid[i] for i in sp["test"]]
    print("split=%s  train=%d val=%d test=%d" % (a.split, len(train), len(val), len(test)))

    gold = [s.label for s in test]
    res = {"split": a.split, "n_test": len(test)}

    # B0
    glob = collections.Counter(s.label for s in train).most_common(1)[0][0]
    res["B0_majority"] = evaluate(gold, [glob] * len(test), "B0 多数类(%s)" % glob)

    # B1
    res["B1_rules"] = evaluate(gold, [rule_predict(s) for s in test], "B1 关键词规则")

    # B2b
    res["B2b_tool_lookup"] = evaluate(gold, tool_lookup(train, test), "B2b 工具名查表")

    # B2 PG2
    if not a.skip_pg2:
        def txt(s):
            return (s.instruction + "\n" + build_agent_log(s))[:2000]
        sv = pg2_scores(a.pg2, [txt(s) for s in val])
        st = pg2_scores(a.pg2, [txt(s) for s in test])
        gv = [s.label for s in val]
        lo, hi, f1v = best_thresholds(sv, gv)
        print("\nPG2 val 上选阈值: lo=%.3f hi=%.3f (val macro-F1=%.4f)" % (lo, hi, f1v))
        res["B2_pg2"] = evaluate(gold, pg2_to_labels(st, lo, hi),
                                 "B2 PG2-86M (lo=%.2f,hi=%.2f)" % (lo, hi))
        res["B2_pg2"]["thresholds"] = [lo, hi]
        # 二分类下界参考：只用 hi 一档，其余全 ALLOW
        res["B2_pg2_binary"] = evaluate(
            gold, ["DENY" if p >= hi else "ALLOW" for p in st],
            "B2 PG2-86M 二分类(hi=%.2f)" % hi)

    out = a.out or os.path.join(ROOT, "results", "baselines_%s.json" % a.split)
    json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
    print("\n-> %s" % out)


if __name__ == "__main__":
    main()
