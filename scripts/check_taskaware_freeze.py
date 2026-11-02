# -*- coding: utf-8 -*-
"""校验 Task-Aware 基线未被改动（只读，秒级）

对照 results/frozen/taskaware/taskaware_freeze.json 里的 sha256，
逐条检查 checkpoint、预测、结果 JSON、报告与脚本。

返回码：0 = 全部一致；1 = 有文件缺失/被改动（打印清单）。
"""
import hashlib
import json
import os
import sys

ROOT = "/data/projects/guardrails"
MAN = os.path.join(ROOT, "results", "frozen", "taskaware", "taskaware_freeze.json")
SECTIONS = ["data", "checkpoint_files", "predictions", "results_json",
            "reports", "scripts"]


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    if not os.path.exists(MAN):
        print("找不到冻结清单：%s" % MAN)
        return 2
    m = json.load(open(MAN, encoding="utf-8"))
    bad, missing, ok = [], [], 0
    for sec in SECTIONS:
        for rel, rec in m[sec].items():
            fp = os.path.join(ROOT, rel)
            if not os.path.exists(fp):
                missing.append(rel)
                continue
            if sha(fp) != rec["sha256"]:
                bad.append(rel)
            else:
                ok += 1
    total = ok + len(bad) + len(missing)
    print("Task-Aware 冻结校验（%s，冻结于 %s）" % (m["version"], m["frozen_at"]))
    print("  一致 %d / %d" % (ok, total))
    for p in missing:
        print("  [缺失] " + p)
    for p in bad:
        print("  [改动] " + p)
    if not bad and not missing:
        print("结论：与冻结版逐字节一致，可用于报告；不可用于选择。")
        return 0
    print("结论：冻结被破坏（%d 缺失 / %d 改动），冻结前的数字不再代表当前代码。"
          % (len(missing), len(bad)))
    return 1


if __name__ == "__main__":
    sys.exit(main())
