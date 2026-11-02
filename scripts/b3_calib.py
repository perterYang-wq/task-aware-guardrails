# -*- coding: utf-8 -*-
"""B3 离线校准：Task-Shield 判官在诊断集 300 条上的判定分布与延迟。"""
import json, os, random, sys, time
R='/data/projects/guardrails'
sys.path.insert(0,R); sys.path.insert(0,os.path.join(R,'scripts'))
from guard.schema import Step, render_pab
from guard_tshield import TShieldGuard

rows=[json.loads(l) for l in open(os.path.join(R,'results/diag/steps.jsonl'))]
rng=random.Random(0)
att=[r for r in rows if r['label']=='DENY']
cln=[r for r in rows if r['label']=='ALLOW']
rng.shuffle(cln); cln=cln[:141]
sample=att+cln
print('样本 %d（攻击 %d / 干净 %d）'%(len(sample),len(att),len(cln)))
g=TShieldGuard()
out=[]
t0=time.time()
for i,r in enumerate(sample):
    st=Step(sid=r['sid'],source='diag',instruction=r['instruction'],history=r['hist_full'],
            current_action=r['current_action'],env_info='',score=0.0,label=r['label'],
            tool=r['tool'],args=r.get('args') or {},meta={})
    action="(1) Thought: (omitted)\n(2) Action: %s\n(3) Action Input: %s"%(
        r['tool'], json.dumps(r.get('args') or {}, ensure_ascii=False))
    lab,raw=g.decide(r['instruction'], r['hist_full'], action)
    out.append(dict(sid=r['sid'],gold=r['label'],pred=lab,raw=raw))
    if (i+1)%50==0: print('  %d/%d %.0fs'%(i+1,len(sample),time.time()-t0), flush=True)
json.dump(out, open(os.path.join(R,'results/classifier/tshield_calib.json'),'w'), ensure_ascii=False, indent=2)
from collections import Counter
c=Counter((o['gold'],o['pred']) for o in out)
den=[o for o in out if o['gold']=='DENY']; cl=[o for o in out if o['gold']=='ALLOW']
print('判定分布', dict(Counter(o['pred'] for o in out)))
print('攻击拦截率 ACB %.3f (%d/%d)'%(sum(1 for o in den if o['pred']=='DENY')/len(den),
      sum(1 for o in den if o['pred']=='DENY'), len(den)))
print('干净误拦  CCB %.3f (%d/%d)'%(sum(1 for o in cl if o['pred']!='ALLOW')/len(cl),
      sum(1 for o in cl if o['pred']!='ALLOW'), len(cl)))
lat=sorted(g.lat); print('延迟 mean %.0fms p50 %.0f p95 %.0f'%(sum(lat)/len(lat), lat[len(lat)//2], lat[int(.95*len(lat))]))
