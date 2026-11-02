# -*- coding: utf-8 -*-
"""部署层补丁：工具授权检查（接在 SafeGuard 的 ALLOW 之后）。

为什么要有这一层
----------------
C7 的失败形态是：守卫认得"任务里没有这个环节"，但一句"守卫已批准"就能把它说服。
主模型的判断是**先验型**的，改不动（重训也试过，见 b6_meta_retrain.md）。
所以这里做一个**不动主模型**的部署层补丁：动作放行后，再问一次"这个参数是从哪来的"。

规则（"可信来源"接地）
--------------------
一条外发/写类调用放行，当且仅当它的**引用型参数**能在下面两处找到：
  S1 用户请求原文
  S2 工具输出（history 去掉 assistant 发言、去掉 <function=...> 调用、去掉 <INFORMATION> 载荷）

只看引用型字段（收件人 / 频道 / 酒店 / 餐厅），**不看生成型字段**（邮件标题、正文、
日历事件标题）：后者本来就是模型自己起的名，检查它只会误杀合法调用——
实测 travel user_task_7 与 slack user_task_20 各有一条干净调用因此被误判。

这层的语义边界（必须写进论文）
--------------------------
它挡的是"**参数来自不可信文本**"这一类越权；挡不住"参数合法但意图被改写"。
所以它不能替代任务授权推理，只能把 meta 这类"用载荷给动作授权"的路径堵住。
"""
import re

_INJ = re.compile(r"<INFORMATION>.*?</INFORMATION>", re.S)
_ACT = re.compile(r"\(2\)\s*Action\s*:\s*(.+)")
_ARG = re.compile(r"\(3\)\s*Action Input\s*:\s*(\{.*)", re.S)

# 只检查引用型字段
CHECK = {
    "send_email": ["recipients"],
    "send_direct_message": ["recipient"],
    "send_channel_message": ["channel"],
    "reserve_hotel": ["hotel"],
    "reserve_restaurant": ["restaurant"],
}


def _norm(x):
    return re.sub(r"\s+", " ", str(x)).strip().lower()


def parse_action(text):
    tool, args = None, {}
    m = _ACT.search(text or "")
    if m:
        tool = m.group(1).strip().splitlines()[0].strip()
    mi = _ARG.search(text or "")
    if mi:
        import json
        try:
            args = json.loads(mi.group(1).strip().split("\n(1)")[0])
        except Exception:
            args = {}
    return tool, args


def tool_text(history):
    """只保留工具返回。

    轨迹格式：assistant 一段话 + <function=tool>{args}</function>，`---` 分隔，再是工具返回。
    history 可能被 max_len 截断，最后一个 assistant 段常常没有收尾标签，所以按段过滤：
    丢掉"以 assistant: 开头"或"含 <function=" 的段。
    """
    h = _INJ.sub("", history or "")
    keep = []
    for seg in h.split("\n---\n"):
        t = seg.strip()
        if not t or t.startswith("assistant:") or "<function=" in t:
            continue
        keep.append(t)
    return "\n".join(keep)


class AuthLayer:
    """返回 None = 放行；返回 dict = 拒绝，带 missing 便于审计。"""

    name = "auth_layer"

    def __init__(self, require_env_source=True):
        self.require_env_source = require_env_source
        self.stats = dict(checked=0, denied=0)

    def check(self, instruction, history, current_action):
        tool, args = parse_action(current_action)
        if not tool or tool not in CHECK:
            return None
        vals = []
        for k in CHECK[tool]:
            v = (args or {}).get(k)
            if isinstance(v, list):
                vals += [str(x) for x in v if str(x).strip()]
            elif v:
                vals.append(str(v))
        if not vals:
            return None
        self.stats["checked"] += 1
        trusted = _norm((instruction or "") + "\n" + tool_text(history))
        missing = [v for v in vals if _norm(v) not in trusted]
        if not missing:
            return None
        self.stats["denied"] += 1
        return dict(reason="untrusted_argument", tool=tool, values=vals, missing=missing)
