"""REVIEW 的执行语义：挂起队列 + 一次性确认。

三条硬规则（对应冻结规范 §4 review_semantics）：
1. REVIEW 不执行。参数以 pending 状态挂起，工具调用返回「已挂起」而不是结果。
2. 只有用户通道能确认。Agent 重复提交同一调用不会消耗确认，也不会被放行。
3. 确认后以**原始参数**执行一次；参数被改动则视为新请求，需重新确认。

`ReviewQueue` 不依赖 LLM，可单独测。
"""
import hashlib
import json
import time
import uuid


def call_sig(tool, args):
    """调用签名：tool + 规范化参数。用于去重与一次性确认。"""
    try:
        body = json.dumps(args or {}, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        body = str(args)
    return hashlib.sha1(('%s|%s' % (tool, body)).encode()).hexdigest()[:16]


class ReviewQueue:
    def __init__(self, path=None):
        self.path = path
        self.items = {}          # pending_id -> record
        self.by_sig = {}         # call_sig -> pending_id（同一调用只挂一次）
        self._confirmed = {}     # call_sig -> pending_id（待消费的一次性许可）
        self._log = []

    # ---------- Agent 侧 ----------
    def submit(self, tool, args, reasons, evidence=None, scenario=None):
        """Agent 提交被挂起的调用；同一签名重复提交返回同一个 pending_id。"""
        sig = call_sig(tool, args)
        pid = self.by_sig.get(sig)
        if pid and self.items[pid]['status'] in ('pending', 'confirmed'):
            self._record('resubmit', sig, pid)
            return pid, False
        pid = 'rv-%s' % uuid.uuid4().hex[:10]
        self.items[pid] = dict(pending_id=pid, sig=sig, tool=tool, args=args,
                               reasons=list(reasons or []), evidence=evidence or [],
                               scenario=scenario, status='pending',
                               created_at=time.time(), decided_at=None, decided_by=None)
        self.by_sig[sig] = pid
        self._record('submit', sig, pid)
        return pid, True

    def consume_if_confirmed(self, tool, args):
        """执行前调用：只有当这条调用被用户确认过（且未被消费）才返回 True。执行后许可作废。"""
        sig = call_sig(tool, args)
        pid = self._confirmed.get(sig)
        if not pid:
            return False
        rec = self.items.get(pid)
        if not rec or rec['status'] != 'confirmed':
            return False
        rec['status'] = 'consumed'
        self._confirmed.pop(sig, None)
        self._record('consume', sig, pid)
        return True

    # ---------- 用户侧 ----------
    def confirm(self, pending_id, by='user'):
        """只应由用户通道调用。Agent 路径不暴露此方法。"""
        rec = self.items.get(pending_id)
        if not rec or rec['status'] != 'pending':
            return False
        rec.update(status='confirmed', decided_at=time.time(), decided_by=by)
        self._confirmed[rec['sig']] = pending_id
        self._record('confirm', rec['sig'], pending_id, by)
        return True

    def reject(self, pending_id, by='user'):
        rec = self.items.get(pending_id)
        if not rec or rec['status'] != 'pending':
            return False
        rec.update(status='rejected', decided_at=time.time(), decided_by=by)
        self._record('reject', rec['sig'], pending_id, by)
        return True

    # ---------- 观测 ----------
    def _record(self, action, sig, pid, by=None):
        self._log.append(dict(ts=time.time(), action=action, sig=sig,
                              pending_id=pid, by=by))

    def stats(self):
        st = [r['status'] for r in self.items.values()]
        return dict(total=len(self.items),
                    pending=st.count('pending'), confirmed=st.count('confirmed'),
                    consumed=st.count('consumed'), rejected=st.count('rejected'))

    def dump(self):
        return dict(items=list(self.items.values()), log=self._log, stats=self.stats())
