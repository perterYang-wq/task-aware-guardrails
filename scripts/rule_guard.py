# -*- coding: utf-8 -*-
"""外部基线 1：规则守卫（不训练、不看标签，纯运行时判据）。

两条规则，都对应用户能直接部署的朴素做法：

`gamma`  敏感工具一律拦。凡 γ==3（外发 / 不可逆 / 花钱 / 改凭证）就 DENY。
         这是"高敏工具必须二次确认"的白名单式做法，业界最常见。
`ground` 无出处一律拦。γ≥2 的调用，只要有关键字符串参数（长度 ≥6）在
         「用户请求 ∪ 已发生的工具输出」里都找不到，就 DENY。
         这是"参数必须有来源"的约束式做法，不需要模型。

为什么用它们当基线
------------------
它们完全不依赖训练数据，因此和 PAB-RD / hard negative 没有任何共享信息；
在同一套 travel/slack 协议下跑出来的 ASR/Utility 可以直接和 HB 比。

用法（由 ad_run3 通过 --guard-adapter rule:gamma 调用）
-----------------------------------------------------
    decide(instruction, history, current_action) -> (label, reason)
    label ∈ {ALLOW, DENY}（规则不给 REVIEW，避免和守卫的三档混在一起）
"""
import json
import re
import sys

ROOT = "/data/projects/guardrails"
sys.path.insert(0, ROOT)
from guard.router import gamma_of  # noqa: E402

_ACT = re.compile(r"\(2\)\s*Action\s*:\s*(.+)")
_ARG = re.compile(r"\(3\)\s*Action\s*Input\s*:\s*(\{.*)", re.S)


def parse_action(text):
    tool, args = None, {}
    m = _ACT.search(text or "")
    if m:
        tool = m.group(1).strip().splitlines()[0].strip()
    mi = _ARG.search(text or "")
    if mi:
        try:
            args = json.loads(mi.group(1).strip().split("\n(1)")[0])
        except Exception:
            args = {}
    return tool, args


def key_vals(args):
    out = []
    for v in (args or {}).values():
        if isinstance(v, str) and len(v) >= 6:
            out.append(v)
        elif isinstance(v, list):
            out += [str(x) for x in v if isinstance(x, str) and len(x) >= 6]
    return out


class RuleGuard:
    def __init__(self, mode="gamma"):
        assert mode in ("gamma", "ground"), mode
        self.mode = mode
        self.name = "rule:" + mode

    def decide(self, instruction, history, current_action):
        tool, args = parse_action(current_action)
        g = gamma_of(tool)
        if self.mode == "gamma":
            return ("DENY", "gamma3:%s" % tool) if g == 3 else ("ALLOW", "gamma%d" % g)
        # ground: γ>=2 且有关键参数在「请求 ∪ 历史」里找不到
        if g < 2:
            return "ALLOW", "read_only"
        vals = key_vals(args)
        if not vals:
            return "ALLOW", "no_strong_arg"
        src = (instruction or "") + "\n" + (history or "")
        miss = [v for v in vals if v not in src]
        if miss:
            return "DENY", "ungrounded:%d/%d" % (len(miss), len(vals))
        return "ALLOW", "grounded"
