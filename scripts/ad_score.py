"""对任意 suite 的轨迹跑 Guard 推理，输出 results/ad_v2/guard_{suite}.jsonl"""
import json, os, sys, argparse
ROOT='/data/projects/guardrails'
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT,'scripts'))
from p2v2_eval import run_arm
ap=argparse.ArgumentParser(); ap.add_argument('--trace',required=True); ap.add_argument('--name',required=True)
a=ap.parse_args()
rows=[json.loads(l) for l in open(a.trace,encoding='utf-8')]
shaped=[dict(instruction=r['instruction'], history=r.get('history') or '',
             current_action=r['current_action'], label='REVIEW', tool=r['tool'],
             pair_id=str(i), pair_role='positive') for i,r in enumerate(rows)]
preds,_=run_arm('/data/hf_cache/qwen1.5b', os.path.join(ROOT,'guard/adapters/p1_15b_task_l2_s0'),
                shaped, False, 16, 6)
out=os.path.join(ROOT,'results/ad_v2','guard_%s.jsonl'%a.name)
with open(out,'w',encoding='utf-8') as f:
    for i,p in enumerate(preds):
        f.write(json.dumps(dict(idx=i,pred=p,tool=rows[i]['tool']),ensure_ascii=False)+'\n')
print('%s: %d 条  %s'%(a.name,len(preds),dict((k,preds.count(k)) for k in ('ALLOW','REVIEW','DENY',None))))
