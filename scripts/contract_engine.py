"""Task Contract P1 引擎（严格按 results/ad_v3/p1_frozen_spec.json 实现）

B2 = 参数来源约束
B3 = B2 + 金额/数量约束（仅 spec.2_guarded_parameters.amount_like 列出的参数）

决策：D0 非敏感放行 → D1 无守卫参数放行 → D2 逐值来源判定 → D3 汇总
DENY 与 REVIEW 分开返回，不合并。
"""
import json, os, re, sys

ROOT = '/data/projects/guardrails'
SPEC = json.load(open(os.path.join(ROOT, 'results/ad_v3/p1_frozen_spec.json'), encoding='utf-8'))


def norm(s):
    s = re.sub(r'\s+', ' ', str(s)).strip().lower()
    return s.strip('.,;:!?\'"()[]{}-')


def contains(haystack, needle):
    """归一化子串包含；needle 长度 <3 视为不参与判定（规范 D4）"""
    n = norm(needle)
    if len(n) < 3:
        return False
    return n in norm(haystack)


class Contract:
    def __init__(self, suite_name, instruction, own_identity, trusted_state,
                 s4_tools, u_tools, tool_outputs):
        sp = SPEC
        self.suite = suite_name
        self.sens = set(sp['1_sensitive_actions'].get(suite_name, []))
        self.guard = sp['2_guarded_parameters'].get(suite_name, {})
        self.amount_spec = sp['2_guarded_parameters']['amount_like'].get(suite_name, {}) or {}
        self.s1 = instruction or ''
        self.s2 = [str(x) for x in (own_identity or []) if x]
        self.s3 = [str(x) for x in (trusted_state or []) if x]
        self.s4_tools = set(s4_tools or [])
        self.u_tools = set(u_tools or [])
        self.outputs = tool_outputs or []
        self.s4_text = '\n'.join(o['output'] for o in self.outputs
                                 if o.get('tool') in self.s4_tools)
        self.u_text = '\n'.join(o['output'] for o in self.outputs
                                if o.get('tool') in self.u_tools)

    def _traceable(self, v):
        if contains(self.s1, v):
            return True, 'in_instruction'
        for x in self.s2:
            if norm(v) == norm(x) or contains(x, v):
                return True, 'own_identity'
        for x in self.s3:
            if norm(v) == norm(x):
                return True, 'trusted_state'
        if contains(self.s4_text, v):
            return True, 'business_api'
        return False, ''

    def decide(self, tool, args, allow_amount=False, required=None):
        """返回 (decision, reasons:list)

        required: 该工具的必填参数集合（来自 schema）。规范 D2a 只对**必填**参数缺失判 DENY，
        可选参数缺失一律忽略（否则 create_calendar_event 不带 participants 会被误杀）。
        """
        if tool not in self.sens:
            return 'ALLOW', ['not_sensitive']
        guarded = [p for p in self.guard.get(tool, []) if p]
        if not guarded:
            return 'ALLOW', ['no_guarded_param']
        required = set(required or [])
        reasons = []
        vals_checked = 0
        for p in guarded:
            raw = (args or {}).get(p)
            vs = raw if isinstance(raw, list) else [raw]
            empty = all(v is None or (isinstance(v, str) and not v.strip()) for v in vs)
            if empty:
                if p in required:
                    reasons.append('DENY:missing_required_param')
                continue
            for v in vs:
                if v is None or (isinstance(v, str) and not v.strip()):
                    continue
                vals_checked += 1
                ok, src = self._traceable(v)
                if ok:
                    reasons.append('allow:%s' % src)
                elif contains(self.u_text, v):
                    reasons.append('DENY:value_from_untrusted_content')
                else:
                    reasons.append('REVIEW:unknown_provenance')
        if vals_checked == 0 and not any(r.startswith('DENY') for r in reasons):
            # 所有守卫参数都是可选的且未提供 → 不做判定（不是违规）
            return 'ALLOW', reasons + ['no_guarded_value']
        if allow_amount and tool in self.amount_spec:
            ap = self.amount_spec[tool]
            av = (args or {}).get(ap)
            if isinstance(av, (int, float)):
                ok, _ = self._traceable(str(av))
                if not ok:
                    nums = re.findall(r'\d+(?:\.\d+)?', self.s1)
                    ok = any(abs(float(n) - float(av)) < 1e-6 for n in nums)
                if not ok:
                    reasons.append('REVIEW:amount_out_of_authorised_range')
        if any(r.startswith('DENY') for r in reasons):
            return 'DENY', reasons
        if any(r.startswith('REVIEW') for r in reasons):
            return 'REVIEW', reasons
        return 'ALLOW', reasons


def build_from_suite(suite_name, env0, version='v1.2.2'):
    """返回 (instructions, own_identity_fn, trusted_state_fn, s4_tools, u_tools)"""
    sp = SPEC['3_allowed_sources']
    if suite_name == 'banking':
        ba, ua = env0.bank_account, env0.user_account
        own = [ba.iban, ua.first_name, ua.last_name]
        state = ([t.recipient for t in ba.transactions]
                 + [t.recipient for t in ba.scheduled_transactions])
    elif suite_name == 'travel':
        u = env0.user
        own = [u.email, u.first_name, u.last_name, u.phone_number,
               u.bank_account_number, u.credit_card_number, u.ID_number]
        r = env0.reservation
        state = list(r.contact_information or []) + ([r.title] if r.title else [])
    elif suite_name == 'slack':
        # 规范 §3 声明 slack 的 S2 = user.email / user.name，S3 = []。
        # 但 SlackEnvironment 没有 user 对象（只有 users/channels/inboxes），
        # 因此这两个来源在本环境里**不存在**，按规范只能贡献空集。
        # 这不是放宽规则，而是如实反映「该来源缺失」——报告中必须写明。
        u = getattr(env0, 'user', None)
        own = ([getattr(u, 'email', ''), getattr(u, 'name', '')] if u else [])
        own = [x for x in own if x]
        state = []
    else:
        own, state = [], []
    return own, state, set(sp['S4_trusted_business_api'].get(suite_name, [])), \
        set(sp['U_untrusted_content'].get(suite_name, []))
