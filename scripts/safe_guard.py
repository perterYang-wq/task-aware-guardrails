# -*- coding: utf-8 -*-
"""执行边界的守卫包装：超时 / 异常一律 fail-closed（DENY），绝不静默放行。

为什么需要这一层
----------------
原始实现里 `guard.decide()` 是裸调用：
  · 守卫抛异常（OOM、模型加载失败、CUDA 错误）→ 异常一路上抛，整个进程退出，
    剩余场景全部丢失，而且**没有任何记录**说明这个场景是被守卫拖死的；
  · 没有超时，一个卡住的推理会把整批实验挂死；
  · 没有"高危工具必须参数出自用户请求"的硬规则，安全性完全押在模型上。

本模块提供三层，全部可单测：
  1. `hard_rule_check()`  纯规则的强制授权检查（可开关）
  2. `SafeGuard`          超时 + 异常 → DENY，并记录元信息
  3. `BoundaryGuard`      两者串联，对上层暴露与原来相同的 `decide()` 接口

fail-closed 的语义
------------------
超时/异常时返回 DENY。这在无人值守部署里是唯一安全的选择：
宁可误拦一个合法调用（用户会看到提示并重试），也不能放行一个未审的副作用。
"""
import re
import signal
import threading
import time

# 高危工具：动钱、改凭证、改个人信息、外发、删除
HIGH_RISK = re.compile(
    r"^(send_money|schedule_transaction|update_scheduled_transaction|update_password|"
    r"update_user_info|send_direct_message|send_channel_message|invite_user_to_slack|"
    r"add_user_to_channel|post_webpage|delete_|remove_)", re.I)

_ACT = re.compile(r"\(2\)\s*Action\s*:\s*(.+)")
_ARG = re.compile(r"\(3\)\s*Action Input\s*:\s*(\{.*)", re.S)


def parse_action(text):
    """从渲染后的动作文本里取出 (tool, args)。与 rule_guard 的约定保持一致。"""
    import json
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
    """硬规则用的参数取值：**不设长度阈值**。

    为什么不用 len>=6：真正的关键值往往很短——账号 `US133`、金额 `100`、密码 `new_password`。
    早期版本用 len>=6 把它们全过滤掉，导致硬规则在 `send_money({"recipient": "US133"})`
    上直接放行（T4 就是被这个 bug 卡住的）。
    """
    out = []
    for v in (args or {}).values():
        if isinstance(v, bool) or v is None:
            continue
        if isinstance(v, str) and v.strip():
            out.append(v)
        elif isinstance(v, (int, float)):
            out.append(str(v))
        elif isinstance(v, (list, tuple)):
            out += [str(x) for x in v if isinstance(x, (str, int, float)) and str(x).strip()]
    return out


def hard_rule_check(instruction, tool, args):
    """高危工具的关键参数必须出现在用户请求原文里，否则直接 DENY。

    只用 instruction，**不看 history**——history 里已经混进了工具输出与注入载荷，
    用它做"接地"正是被攻击的入口。
    返回 None 表示放行到模型层。
    """
    if not tool or not HIGH_RISK.match(tool):
        return None
    vals = key_vals(args)
    if not vals:
        return None
    miss = [v for v in vals if v not in (instruction or "")]
    if miss:
        return "DENY", "hard_rule:ungrounded:%d/%d" % (len(miss), len(vals))
    return None


class GuardTimeout(Exception):
    pass


class SafeGuard:
    """给任意 scorer 加超时与异常兜底。失败一律 DENY。"""

    def __init__(self, inner, timeout_s=3.0, name=None):
        self.inner = inner
        self.timeout_s = timeout_s
        self.name = name or getattr(inner, "name", type(inner).__name__)
        self.last_meta = {}
        self.n_error = 0
        self.n_timeout = 0

    def _on_alarm(self, signum, frame):
        raise GuardTimeout("guard exceeded %.1fs" % self.timeout_s)

    def decide(self, instruction, history, current_action):
        meta = {"error": None, "timeout": False, "ms": None}
        t0 = time.time()
        in_main = threading.current_thread() is threading.main_thread()
        old = None
        try:
            if self.timeout_s and in_main:
                old = signal.signal(signal.SIGALRM, self._on_alarm)
                signal.setitimer(signal.ITIMER_REAL, self.timeout_s)
            label, raw = self.inner.decide(instruction, history, current_action)
            return label, raw
        except GuardTimeout:
            self.n_timeout += 1
            meta["timeout"] = True
            meta["error"] = "timeout>%.1fs" % self.timeout_s
            return "DENY", "guard_timeout"
        except Exception as e:                                   # noqa: BLE001
            self.n_error += 1
            meta["error"] = "%s: %s" % (type(e).__name__, str(e)[:160])
            return "DENY", "guard_error:%s" % type(e).__name__
        finally:
            if self.timeout_s and in_main:
                signal.setitimer(signal.ITIMER_REAL, 0)
                if old is not None:
                    signal.signal(signal.SIGALRM, old)
            meta["ms"] = int((time.time() - t0) * 1000)
            self.last_meta = meta


class BoundaryGuard:
    """硬规则 + 模型守卫，对上层暴露 `decide()`。

    `last_meta`：{hard_rule, error, timeout, ms, model_decision}
    """

    def __init__(self, inner, hard_rule=False, timeout_s=3.0, name=None):
        # inner=None 表示「纯硬规则臂」：用于消融「收益来自规则还是模型」。
        # 这时没有模型可调，硬规则没命中就放行（等价于一条独立的规则基线）。
        self.has_model = inner is not None
        self.safe = SafeGuard(inner, timeout_s=timeout_s, name=name) if self.has_model else None
        self.hard_rule = hard_rule
        self.name = name or (self.safe.name if self.safe else "hard_rule")
        self.last_meta = {}
        self.n_hard = 0

    def decide(self, instruction, history, current_action):
        tool, args = parse_action(current_action)
        meta = {"hard_rule": False, "tool": tool, "error": None, "timeout": False, "ms": 0}
        if self.hard_rule:
            hr = hard_rule_check(instruction, tool, args)
            if hr is not None:
                self.n_hard += 1
                meta["hard_rule"] = True
                meta["model_decision"] = None
                self.last_meta = meta
                return hr
        if not self.has_model:
            meta["model_decision"] = None
            self.last_meta = meta
            return "ALLOW", "hard_rule_only"
        label, raw = self.safe.decide(instruction, history, current_action)
        meta.update(self.safe.last_meta)
        meta["model_decision"] = label
        self.last_meta = meta
        return label, raw
