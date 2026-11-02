# -*- coding: utf-8 -*-
"""Risk-Adaptive Router · Step 1（固定阈值，无 PG2、无训练）

组件
----
γ  工具危害等级（规则，1 读 / 2 写本地 / 3 外部或不可逆）
g  参数接地（动作里的字符串参数是否都能在 history 中找到）
m  任务-动作不一致度 = -cos(instruction, action)，TF-IDF，向量器只在训练集上拟合

路由
----
硬规则（任一命中 → 必须过 Guard，不许走快速通道）：
    * 未知工具（不在训练集工具表）
    * γ == 3（外部 / 不可逆 / 花钱 / 改凭证）
    * g == 0（参数无证据支撑）
软分数（只对通过硬规则的候选）：
    S = w_m·m̃ + w_γ·γ̃          m̃ = 1 + m ∈ [0,1]，γ̃ = (γ-1) ∈ {0,1}
    S < τ → 快速通道（直接 ALLOW）；否则 → Task-Aware Guard

注意：所有阈值只能在 val / contains_train 上选；strict_test 只在方法冻结后测一次。
"""
import json
import re

# ---------------------------------------------------------------- γ 表
# 判据：1 = 只读；3 = 离开本地环境 / 不可逆 / 花钱 / 改凭证；其余已知工具 = 2
_READ = re.compile(r"^(get_|search_|list_|read_|check_|find_|query_|retrieve_)", re.I)
_EXT = re.compile(r"^(send_|share_|post_|delete_|invite_|add_user_to_channel|"
                  r"reserve_|schedule_transaction|update_scheduled_transaction|"
                  r"update_password)", re.I)


def gamma_of(tool):
    t = tool or ""
    if _EXT.match(t):
        return 3
    if _READ.match(t):
        return 1
    return 2


def gamma_norm(g):
    """γ ∈ {1,2} → 0 / 1；γ=3 已在硬规则里拦截，不进分数。"""
    return max(0.0, min(1.0, (g - 1) / 1.0))


def is_unknown(tool, known_tools):
    return (tool or "") not in known_tools


def grounded(action_args, history):
    """参数级接地：所有"像标识符"的字符串值都要在 history 中出现。"""
    if not isinstance(action_args, dict) or not action_args:
        return False
    h = history or ""
    if not h:
        return False
    vals = []
    for v in action_args.values():
        if isinstance(v, str):
            vals.append(v)
        elif isinstance(v, list):
            vals += [x for x in v if isinstance(x, str)]
    vals = [v for v in vals
            if len(v) >= 3 and not v.replace(".", "").replace("-", "").isdigit()]
    if not vals:
        return False
    return all(v in h for v in vals)


class Router:
    def __init__(self, vectorizer, known_tools, w_m=0.6, w_gamma=0.4, tau=0.5,
                 rule_gamma3_hard=True):
        self.vec = vectorizer
        self.known = set(known_tools)
        self.w_m, self.w_g = w_m, w_gamma
        self.tau = tau
        self.rule_gamma3_hard = rule_gamma3_hard

    def features(self, row):
        from sklearn.metrics.pairwise import cosine_similarity
        ins = row.get("instruction") or ""
        act = row.get("current_action") or ""
        sim = float(cosine_similarity(self.vec.transform([ins]),
                                      self.vec.transform([act]))[0, 0])
        g = gamma_of(row.get("tool"))
        args = row.get("args")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = None
        if not isinstance(args, dict):
            # P2-v2 等行没有 args 字段：从动作文本里解析 "(3) Action Input: {...}"
            try:
                from guard.schema import parse_action
                args = parse_action(act).get("args")
            except Exception:
                args = None
        gt = grounded(args, row.get("history") or "")
        return {"gamma": g, "m": -sim, "m_tilde": 1.0 - sim,
                "grounded": bool(gt), "unknown": is_unknown(row.get("tool"), self.known)}

    def route(self, f):
        """返回 (去向, 命中的硬规则, 软分数)。去向 ∈ {guard, fast}。"""
        hard = []
        if f["unknown"]:
            hard.append("unknown_tool")
        if self.rule_gamma3_hard and f["gamma"] >= 3:
            hard.append("gamma3")
        if not f["grounded"]:
            hard.append("ungrounded")
        if hard:
            return "guard", hard, None
        s = self.w_m * f["m_tilde"] + self.w_g * gamma_norm(f["gamma"])
        return ("fast" if s < self.tau else "guard"), hard, s
