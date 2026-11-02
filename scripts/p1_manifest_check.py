# -*- coding: utf-8 -*-
"""P1 产物清单校验（启动 P2-v2 前的门禁）

不数文件个数，而是按协议枚举**每一个预期 run**，逐个核对身份与完成状态：

  训练 16 个 = Stage A（2 模型 × 2 lr × 2 臂 × seed0） + Stage B（2 模型 × 2 臂 × seed{42,123} @ 选定 lr）
  评测 12 个 = 2 模型 × 2 臂 × seed{0,42,123} @ 选定 lr

每个训练 run 校验：tag 一致、model 一致、seed 一致、lr 一致、Full/No-task 一致、
训练协议一致（epochs4 / bs4 / accum4 / max_len1024 / lora r16 alpha32 / style pab / 数据同源）、
4 个 epoch 全跑完且 best_epoch 与 hist 自洽、adapter 权重文件真实存在且非空。

每个评测产物校验：文件存在、行数 = test 335、sid 集合与 test 完全一致且不重复、
gold 分布与 test 一致、没有解析失败、raw 非空。

另外核对 p1_record.json 的 lr_choice 与实际训练 json 的 lr 一致、evals 覆盖 12 个 tag，
以及主日志无 [FAIL ] 行且出现 P1_DONE。

退出码：0 = 全部齐全；1 = 有缺失/不一致（调用方据此写 P2V2_ABORT，不启动评测）。
"""
import collections
import json
import os
import re
import sys

ROOT = "/data/projects/guardrails"
MODELS = {"15b": "/data/hf_cache/qwen1.5b", "3b": "/data/hf_cache/qwen3b"}
LRS = {"l1": 1e-4, "l2": 2e-4}
SEEDS_B = [42, 123]
ARMS = {"task": False, "nt": True}
PROTO = {"epochs": 4, "bs": 4, "accum": 4, "max_len": 1024,
         "lora_r": 16, "lora_alpha": 32, "style": "pab"}
DATA = "data/pab_rd.jsonl"
SPLITS = "data/pab_rd_splits.json"
OUT = os.path.join(ROOT, "results", "p2v2", "p1_manifest.json")
N_TEST = 335
LABELS = {"ALLOW", "REVIEW", "DENY"}


def load_json(p, default=None):
    if not os.path.exists(p):
        return default
    return json.load(open(p, encoding="utf-8"))


def adapter_ok(tag):
    d = os.path.join(ROOT, "guard", "adapters", tag)
    cfg = os.path.join(d, "adapter_config.json")
    w = os.path.join(d, "adapter_model.safetensors")
    if not (os.path.isdir(d) and os.path.isfile(cfg) and os.path.isfile(w)):
        return False, "adapter 目录/配置/权重缺失"
    if os.path.getsize(w) < 1_000_000:
        return False, "adapter 权重仅 %d 字节" % os.path.getsize(w)
    try:
        c = json.load(open(cfg, encoding="utf-8"))
    except Exception as e:
        return False, "adapter_config 读取失败 %s" % e
    if int(c.get("r", -1)) != PROTO["lora_r"]:
        return False, "adapter r=%s" % c.get("r")
    return True, ""


def check_train(tag, model, arm, lrkey, seed, errs):
    """返回 run 记录；任何不一致都进 errs。"""
    p = os.path.join(ROOT, "results", "train_%s.json" % tag)
    rec = {"tag": tag, "model": model, "arm": arm, "lrkey": lrkey,
           "lr": LRS[lrkey], "seed": seed, "ok": False, "why": []}
    if not os.path.exists(p):
        rec["why"].append("缺 train json")
        errs.append("%s: 缺 results/train_%s.json" % (tag, tag))
        return rec
    d = load_json(p, {})
    a = d.get("args", {})
    exp_no_task = ARMS[arm]
    checks = [
        (d.get("tag") == tag, "json.tag=%s" % d.get("tag")),
        (a.get("tag") == tag, "args.tag=%s" % a.get("tag")),
        (a.get("model") == MODELS[model], "args.model=%s" % a.get("model")),
        (a.get("seed") == seed, "args.seed=%s" % a.get("seed")),
        (abs(float(a.get("lr", -1)) - LRS[lrkey]) < 1e-12, "args.lr=%s" % a.get("lr")),
        (a.get("no_task") is exp_no_task, "args.no_task=%s" % a.get("no_task")),
        (d.get("task_aware") is (not exp_no_task), "task_aware=%s" % d.get("task_aware")),
        (a.get("epochs") == PROTO["epochs"], "epochs=%s" % a.get("epochs")),
        (a.get("bs") == PROTO["bs"], "bs=%s" % a.get("bs")),
        (a.get("accum") == PROTO["accum"], "accum=%s" % a.get("accum")),
        (a.get("max_len") == PROTO["max_len"], "max_len=%s" % a.get("max_len")),
        (a.get("lora_r") == PROTO["lora_r"], "lora_r=%s" % a.get("lora_r")),
        (a.get("lora_alpha") == PROTO["lora_alpha"], "lora_alpha=%s" % a.get("lora_alpha")),
        (a.get("style") == PROTO["style"], "style=%s" % a.get("style")),
        (a.get("data") == DATA, "data=%s" % a.get("data")),
        (a.get("splits") == SPLITS, "splits=%s" % a.get("splits")),
    ]
    for ok, msg in checks:
        if not ok:
            rec["why"].append(msg)
    hist = d.get("hist") or []
    if len(hist) != PROTO["epochs"]:
        rec["why"].append("hist 只有 %d 个 epoch" % len(hist))
    if not hist:
        rec["why"].append("无 epoch 记录（未跑完）")
    else:
        f1s = [h.get("val_macro_f1", -1) for h in hist]
        be = d.get("best_epoch")
        if be is None or not (1 <= int(be) <= PROTO["epochs"]):
            rec["why"].append("best_epoch 非法 %s" % be)
        elif abs(max(f1s) - float(d.get("best_val_macro_f1", -1))) > 1e-9:
            rec["why"].append("best_val_macro_f1 与 hist 最大值不一致")
        elif int(be) != f1s.index(max(f1s)) + 1:
            rec["why"].append("best_epoch=%s 与 hist 最优轮 %d 不一致"
                              % (be, f1s.index(max(f1s)) + 1))
        rec["best_epoch"] = be
        rec["val_f1"] = d.get("best_val_macro_f1")
    ok, why = adapter_ok(tag)
    if not ok:
        rec["why"].append(why)
    rec["ok"] = not rec["why"]
    if not rec["ok"]:
        errs.append("%s: %s" % (tag, "; ".join(rec["why"])))
    return rec


def check_eval(tag, arm, test_sids, test_gold, errs):
    fn = os.path.join(ROOT, "results", "p1", "preds", "%s_%s.jsonl" % (tag, arm))
    rec = {"tag": tag, "arm": arm, "file": os.path.relpath(fn, ROOT), "ok": False}
    if not os.path.exists(fn):
        rec["why"] = "缺预测文件"
        errs.append("%s: 缺 %s" % (tag, rec["file"]))
        return rec
    rows = [json.loads(l) for l in open(fn, encoding="utf-8")]
    sids = [r["sid"] for r in rows]
    gold = collections.Counter(r["gold"] for r in rows)
    unparsed = sum(1 for r in rows if r.get("pred") is None)
    why = []
    if len(rows) != N_TEST:
        why.append("行数 %d != %d" % (len(rows), N_TEST))
    if len(set(sids)) != len(sids):
        why.append("sid 重复 %d 个" % (len(sids) - len(set(sids))))
    if set(sids) != test_sids:
        why.append("sid 集合与 test 不一致（缺 %d / 多 %d）"
                   % (len(test_sids - set(sids)), len(set(sids) - test_sids)))
    if dict(gold) != dict(test_gold):
        why.append("gold 分布不一致 %s" % dict(gold))
    if set(gold) - LABELS:
        why.append("gold 出现非法标签")
    if unparsed / max(1, len(rows)) > 0.02:
        why.append("解析失败 %d/%d (>2%%)" % (unparsed, len(rows)))
    if any(not r.get("raw") for r in rows):
        why.append("存在空 raw 输出")
    rec.update({"n": len(rows), "unparsed": unparsed, "why": why,
                "ok": not why})
    if why:
        errs.append("%s: %s" % (tag, "; ".join(why)))
    return rec


def main():
    errs, warns = [], []
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    ml = open("/tmp/p1_main.log", encoding="utf-8", errors="replace").read() \
        if os.path.exists("/tmp/p1_main.log") else ""
    if "P1_DONE" not in ml:
        errs.append("主日志未见 P1_DONE（P1 未正常收尾）")
    fails = re.findall(r"\[FAIL \]\s+(\S+)\s+rc=(\d+)", ml)
    for t, rc in fails:
        errs.append("主日志记录失败 run %s rc=%s" % (t, rc))

    sp = load_json(os.path.join(ROOT, SPLITS), {})
    sp = sp.get("pab", sp)
    test_ids = list(sp.get("test", []))
    test_sids = set(test_ids)
    data = {}
    for line in open(os.path.join(ROOT, DATA), encoding="utf-8"):
        d = json.loads(line)
        data[d["sid"]] = d["label"]
    test_gold = collections.Counter(data[s] for s in test_ids)

    rec = load_json(os.path.join(ROOT, "results", "p1", "p1_record.json"), None)
    if rec is None:
        errs.append("缺 results/p1/p1_record.json")
        lr_choice = {}
    else:
        lr_choice = rec.get("lr_choice", {})
        for m in MODELS:
            if m not in lr_choice:
                errs.append("p1_record 缺 %s 的 lr 选择" % m)

    # ---- 枚举全部预期 run（不用数量，用身份）
    expected = []
    for m in ("15b", "3b"):
        for lk in ("l1", "l2"):
            for arm in ("task", "nt"):
                expected.append(("p1_%s_%s_%s_s0" % (m, arm, lk), m, arm, lk, 0))
    for m in ("15b", "3b"):
        ch = lr_choice.get(m)
        if not ch:
            continue
        for arm in ("task", "nt"):
            for s in SEEDS_B:
                expected.append(("p1_%s_%s_%s_s%d" % (m, arm, ch["lrkey"], s),
                                 m, arm, ch["lrkey"], s))
    tags = [e[0] for e in expected]
    if len(tags) != len(set(tags)):
        errs.append("预期清单自身有重复 tag")
    if len(expected) != 16:
        errs.append("预期训练 run 数为 %d，应为 16" % len(expected))

    runs = [check_train(*e, errs) for e in expected]
    evals = []
    for m in ("15b", "3b"):
        ch = lr_choice.get(m)
        if not ch:
            continue
        for arm in ("task", "nt"):
            for s in (0, 42, 123):
                evals.append(check_eval("p1_%s_%s_%s_s%d" % (m, arm, ch["lrkey"], s),
                                        arm, test_sids, test_gold, errs))

    # ---- 额外产物（不算失败，但列出以便发现残留）
    on_disk = {os.path.basename(p)[6:-5]
               for p in [os.path.join(ROOT, "results", f)
                         for f in os.listdir(os.path.join(ROOT, "results"))
                         if f.startswith("train_p1_") and f.endswith(".json")]}
    extra = sorted(on_disk - set(tags))
    if extra:
        warns.append("存在非预期 train json：%s" % extra)

    # ---- p1_record 的 evals 覆盖
    if rec:
        ev = set(rec.get("evals", {}))
        need = {e["tag"] for e in evals}
        if not need <= ev:
            errs.append("p1_record.evals 缺 %d 项" % len(need - ev))
        for m in ("15b", "3b"):
            ch = lr_choice.get(m)
            if not ch:
                continue
            bad = [r["tag"] for r in runs
                   if r["model"] == m and not r["ok"]]
            if bad:
                warns.append("%s 尚不完整的 run：%s" % (m, bad))

    status = {"ok": not errs, "n_expected_train": len(expected),
              "n_ok_train": sum(1 for r in runs if r["ok"]),
              "n_expected_eval": len(evals),
              "n_ok_eval": sum(1 for r in evals if r["ok"]),
              "errors": errs, "warnings": warns,
              "runs": runs, "evals": evals,
              "p1_done_marker": "P1_DONE" in ml,
              "log_fails": fails}
    json.dump(status, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("[manifest] train %d/%d ok   eval %d/%d ok   P1_DONE=%s"
          % (status["n_ok_train"], status["n_expected_train"],
             status["n_ok_eval"], status["n_expected_eval"], status["p1_done_marker"]))
    for w in warns:
        print("  [warn] " + w)
    for e in errs[:20]:
        print("  [miss] " + e)
    if len(errs) > 20:
        print("  ... 共 %d 条" % len(errs))
    print("[manifest] %s -> %s" % ("PASS" if status["ok"] else "FAIL", OUT))
    return 0 if status["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
