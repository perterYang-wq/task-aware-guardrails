# -*- coding: utf-8 -*-
"""meta 变性是否"直接骗过守卫"：逐场景比对 send_email 那条调用的判定。"""
import json, os
R='/data/projects/guardrails'
def J(p): return [json.loads(l) for l in open(os.path.join(R,p,'scen.jsonl'))]
def send_dec(rs):
    out={}
    for r in rs:
        if not (r.get('injection_present') and r.get('injection_task')=='injection_task_1'): continue
        d=[(h['decision'],h.get('raw')) for h in (r.get('guard_hits') or []) if h['tool']=='send_email']
        out[r['user_task']]=d[-1] if d else None
    return out
st=send_dec(J('results/e2e/travel/m2_HB_s0_calls_inj0-1'))
me=send_dec(J('results/e2e/travel/m2_HB_s0_b6meta_inj1'))
print('%-14s %-16s %-16s %s'%('user_task','static(send_email)','meta(send_email)','变化'))
n_flip=0
for k in sorted(set(st)&set(me)):
    a,b=st[k],me[k]
    ch=''
    if a and b and a[0]!=b[0]:
        ch='<== 判定变了'; n_flip+=1
    print('%-14s %-16s %-16s %s'%(k, a[0] if a else '—', b[0] if b else '—', ch))
print('\n判定发生变化的场景数: %d'%n_flip)
