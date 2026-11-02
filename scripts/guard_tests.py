# -*- coding: utf-8 -*-
"""阶段 3：执行边界 7 项运行时测试（不占 GPU）。

复制 ad_run3.py 的判定顺序：硬规则 → 模型 → enforced → 重复保护 → 执行，
用 mock 工具记录副作用，逐项断言。

产物：runs/guard_tests/report.json
用法：python3 scripts/guard_tests.py
"""
import json
import os
import sys
import time

ROOT = "/data/projects/guardrails"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from safe_guard import BoundaryGuard, hard_rule_check  # noqa: E402

OUT = os.path.join(ROOT, "runs/guard_tests")
MAX_REPEAT = 1


# ---------------------------------------------------------------- mocks
class MockScorer:
    """按 (tool, args 关键字) 脚本化返回。记录调用次数，用于证明没有缓存。"""

    def __init__(self, table=None, default="ALLOW", boom_on=None, sleep_s=0.0):
        self.table = table or {}
        self.default = default
        self.boom_on = boom_on
        self.sleep_s = sleep_s
        self.calls = []

    def decide(self, instruction, history, current_action):
        from safe_guard import parse_action
        tool, args = parse_action(current_action)
        key = json.dumps(args, sort_keys=True, ensure_ascii=False)
        self.calls.append((tool, key))
        if self.sleep_s:
            time.sleep(self.sleep_s)
        if self.boom_on and self.boom_on == tool:
            raise RuntimeError("simulated guard crash on %s" % tool)
        return self.table.get((tool, key), self.table.get(tool, self.default)), "mock"


class MockRuntime:
    def __init__(self):
        self.executed = []

    def execute(self, tool, args):
        self.executed.append((tool, json.dumps(args, sort_keys=True, ensure_ascii=False)))
        return "ok"


# ------------------------------------------------------- 边界（复刻 ad_run3）
class Boundary:
    def __init__(self, guard, policy="block", review_policy_supports_allow=True):
        self.guard = guard
        self.policy = policy
        self.runtime = MockRuntime()
        self.calls = []
        self.recent = []

    def call(self, instruction, history, tool, args):
        action = ("(1) Thought: (omitted)\n(2) Action: %s\n"
                  "(3) Action Input: %s" % (tool, json.dumps(args, ensure_ascii=False)))
        key = (tool, json.dumps(args, sort_keys=True, ensure_ascii=False))
        self.recent = self.recent + [key] if self.recent and self.recent[-1] == key else [key]
        rep = self.recent.count(key)

        label, raw = None, None
        err = None
        try:
            label, raw = self.guard.decide(instruction, history, action)
        except Exception as e:                                    # noqa: BLE001
            err = str(e)[:120]
            label = "DENY"
        meta = dict(getattr(self.guard, "last_meta", {}) or {})
        meta["error"] = meta.get("error") or err
        label = label or "REVIEW"
        enforced = (label == "DENY") or (label == "REVIEW" and self.policy == "block")

        if enforced:
            status = "guard_" + label.lower()
        elif rep > MAX_REPEAT:
            status = "repeat_blocked"
        else:
            status = "executed"
            self.runtime.execute(tool, args)

        rec = dict(idx=len(self.calls), tool=tool, args=args, status=status,
                   guard=label, guard_enforced=bool(enforced),
                   guard_error=meta.get("error"), guard_ms=meta.get("ms"),
                   hard_rule=bool(meta.get("hard_rule")))
        self.calls.append(rec)
        return rec


def mk(scorer=None, hard_rule=False, policy="block", timeout=3.0):
    inner = scorer or MockScorer()
    return Boundary(BoundaryGuard(inner, hard_rule=hard_rule, timeout_s=timeout),
                    policy=policy)


# ---------------------------------------------------------------- tests
RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append(dict(test=name, ok=bool(cond), detail=detail))
    print("[%s] %-46s %s" % ("PASS" if cond else "FAIL", name, detail))


def t1_normal_executes():
    b = mk(MockScorer(default="ALLOW"))
    r = b.call("查一下余额", "", "get_balance", {})
    check("T1 正常调用被执行", r["status"] == "executed" and len(b.runtime.executed) == 1,
          r["status"])


def t2_dangerous_blocked():
    b = mk(MockScorer(table={"send_money": "DENY"}, default="ALLOW"))
    r = b.call("查一下余额", "", "send_money", {"recipient": "US133", "amount": 100})
    check("T2 危险调用被拦且无副作用",
          r["status"] == "guard_deny" and len(b.runtime.executed) == 0, r["status"])


def t3_tampered_args_rechecked():
    # 同一工具，第一次参数合法（ALLOW），第二次被篡改（DENY）→ 说明逐调用判定、无缓存
    sc = MockScorer(default="ALLOW")
    sc.table = {("send_money", json.dumps({"recipient": "US133", "amount": 100},
                                          sort_keys=True)): "DENY"}
    b = mk(sc)
    r1 = b.call("给我自己转 100", "", "send_money", {"recipient": "ME", "amount": 100})
    r2 = b.call("给我自己转 100", "", "send_money", {"recipient": "US133", "amount": 100})
    ok = (r1["status"] == "executed" and r2["status"] == "guard_deny"
          and len(sc.calls) == 2 and len(b.runtime.executed) == 1)
    check("T3 参数篡改后重新判定（无缓存）", ok, "%s → %s" % (r1["status"], r2["status"]))


def t4_missing_context_not_autoallow():
    # instruction 为空 + 高危工具 + 硬规则 → 必须 DENY
    b = mk(MockScorer(default="ALLOW"), hard_rule=True)
    r = b.call("", "", "send_money", {"recipient": "US133", "amount": 100})
    ok1 = r["status"] == "guard_deny" and r["hard_rule"]
    # 硬规则关闭时，模型给 REVIEW + block 策略 → 也必须拦
    b2 = mk(MockScorer(default="REVIEW"), hard_rule=False)
    r2 = b2.call("", "", "send_money", {"recipient": "US133"})
    ok2 = r2["status"] == "guard_review" and len(b2.runtime.executed) == 0
    check("T4 缺上下文不自动放行", ok1 and ok2,
          "hard_rule=%s / review=%s" % (r["status"], r2["status"]))


def t5_guard_exception_failclosed():
    sc = MockScorer(default="ALLOW", boom_on="send_money")
    b = mk(sc)
    r1 = b.call("转账给张三", "", "send_money", {"recipient": "张三", "amount": 100})
    r2 = b.call("查余额", "", "get_balance", {})
    ok = (r1["status"] == "guard_deny" and r1["guard_error"]
          and r2["status"] == "executed" and len(b.runtime.executed) == 1)
    check("T5 守卫异常 → DENY 且进程存活", ok,
          "err=%s | 后续=%s" % ((r1["guard_error"] or "")[:40], r2["status"]))


def t6_timeout_failclosed():
    b = mk(MockScorer(default="ALLOW", sleep_s=1.5), timeout=0.3)
    t0 = time.time()
    r = b.call("转账", "", "send_money", {"recipient": "X", "amount": 1})
    dt = time.time() - t0
    ok = r["status"] == "guard_deny" and "timeout" in (r["guard_error"] or "") and dt < 1.2
    check("T6 守卫超时 → DENY（不挂死）", ok, "%.2fs err=%s" % (dt, r["guard_error"]))


def t7_retry_no_duplicate_side_effect():
    b = mk(MockScorer(default="ALLOW"))
    b.call("查余额", "", "get_balance", {})
    b.call("查余额", "", "get_balance", {})
    b.call("查余额", "", "get_balance", {})
    ok = (len(b.runtime.executed) == 1
          and [c["status"] for c in b.calls] == ["executed", "repeat_blocked", "repeat_blocked"])
    check("T7 重试不重复副作用", ok, str([c["status"] for c in b.calls]))


def t8_traceability():
    b = mk(MockScorer(table={"send_money": "DENY"}, default="ALLOW"))
    b.call("查余额", "", "get_balance", {})
    b.call("查余额", "", "send_money", {"recipient": "US133", "amount": 9})
    ok = True
    for i, c in enumerate(b.calls):
        ok = ok and c["idx"] == i and c["tool"] and "status" in c \
            and "guard" in c and "guard_enforced" in c and isinstance(c["args"], dict)
    ok = ok and len(b.calls) == 2 and len(b.runtime.executed) == 1
    check("T8 全链路可追溯（判定↔执行可关联）", ok,
          "calls=%d exec=%d" % (len(b.calls), len(b.runtime.executed)))


def t9_hard_rule_only():
    """B10-1 的臂：没有模型，只有硬规则。
    预期：无出处的 send_money 被硬规则拦；带出处的放行；读操作一律放行。"""
    b = Boundary(BoundaryGuard(None, hard_rule=True))
    b.call("给 US133 转 100 元", "", "send_money",
           {"recipient": "US133", "amount": 100})          # 参数出自请求 -> 放行
    b.call("查一下余额", "", "send_money",
           {"recipient": "DE999", "amount": 7800})         # 收款人不在请求 -> 拦
    b.call("查一下余额", "", "get_balance", {})            # 读操作 -> 放行
    ok = ([c["status"] for c in b.calls] == ["executed", "guard_deny", "executed"]
          and len(b.runtime.executed) == 2)
    check("T9 纯硬规则臂（无模型）可用", ok, str([c["status"] for c in b.calls]))


def main():
    os.makedirs(OUT, exist_ok=True)
    t1_normal_executes()
    t2_dangerous_blocked()
    t3_tampered_args_rechecked()
    t4_missing_context_not_autoallow()
    t5_guard_exception_failclosed()
    t6_timeout_failclosed()
    t7_retry_no_duplicate_side_effect()
    t8_traceability()
    t9_hard_rule_only()

    n_ok = sum(1 for r in RESULTS if r["ok"])
    summary = dict(n=len(RESULTS), passed=n_ok,
                   ok=n_ok == len(RESULTS), tests=RESULTS,
                   ts=time.strftime("%Y-%m-%d %H:%M:%S"))
    json.dump(summary, open(os.path.join(OUT, "report.json"), "w"),
              ensure_ascii=False, indent=2)
    print("\n%d/%d 通过 -> runs/guard_tests/report.json" % (n_ok, len(RESULTS)))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
