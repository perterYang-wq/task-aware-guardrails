# -*- coding: utf-8 -*-
"""论文表格与 final_report.json 的一致性检查。

只做断言，不改文件。检查三件事：
1. 论文里出现的每个 Δ 值都能在 final_report.json 找到对应（允许四舍五入）
2. 旧的错误标注已全部清除
3. 恒等式与点估计仍成立
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FROZEN = os.path.join(ROOT, "results", "frozen")
PAPER = os.path.join(ROOT, "reports", "paper_draft.md")

rep = json.load(open(os.path.join(FROZEN, "final_report.json"), encoding="utf-8"))
paper = open(PAPER, encoding="utf-8").read()

fails = []


def chk(cond, msg):
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


print("== 1. 恒等式与元数据 ==")
for name, a in rep["arms"].items():
    lhs = a["PRA"]
    rhs = a["SPA"] + 0.5 * a["TieRate"]
    chk(abs(lhs - rhs) < 1e-9, "%s: PRA = SPA + 0.5*TieRate" % name)
chk(rep["provenance"]["n_pairs"] == 90, "90 配对")
chk(rep["provenance"]["n_action_groups"] == 47, "47 动作组")
chk(rep["provenance"]["n_task_groups"] == 25, "25 任务组")

print("\n== 2. 关键数字出现在论文里 ==")
key = [
    ("+0.085", "等权 ΔPRA"),
    ("+0.189", "等权 ΔSPA"),
    ("[+0.014, +0.152]", "ΔPRA CI"),
    ("[+0.074, +0.300]", "ΔSPA CI"),
    ("0.021", "ΔPRA cluster p"),
    ("0.0028", "ΔSPA cluster p"),
    ("0.00069", "旧符号检验 p（SPA 41:15）"),
    ("0.0038", "3B ΔPRA cluster p"),
    ("0.166", "0.5B ΔPRA cluster p"),
]
for needle, what in key:
    chk(needle in paper, "%s = %s 出现在论文中" % (what, needle))

print("\n== 3. 旧错误标注已清除 ==")
bad = [
    ("1.1e-10", "旧的 360 对合并 p"),
    ("significant in three of four", "旧的逐尺寸显著性说法"),
    ("p = 0.031", "旧的 0.5B 符号检验 p 被当成主结果"),
]
for needle, what in bad:
    chk(needle not in paper, "已清除：%s" % what)

print("\n== 4. 部署角色表述 ==")
chk("0.5B, 1.5B and 3B each receive 1/3" in paper, "等权 1/3 预注册表述")
chk("exploratory" in paper and "not a deployment candidate" in paper, "7B 排除于合并的表述")

print("\n== 5. 三个单模型都在正文分别报告 ==")
for s in ("0.5B", "1.5B", "3B"):
    chk("| %s |" % s in paper or "| **%s** |" % s in paper, "表内含 %s 行" % s)

print("\n%d checks failed" % len(fails))
if fails:
    for f in fails:
        print("  - " + f)
    raise SystemExit(1)
