"""阶段 3：按 PG2 模型卡做分段评分（chunk → 逐段打分 → max 聚合）。
保存 chunk 级明细与 record 级分数；三种输入构造各一份。"""
import json, os, sys, argparse
import numpy as np, torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer
ROOT='/data/projects/guardrails'; OUT=os.path.join(ROOT,'results/ad_v2'); os.makedirs(OUT,exist_ok=True)
PG2='/data/hf_cache/pg2-86m'; MAXLEN=512; CHUNK=400; STRIDE=64
tok=AutoTokenizer.from_pretrained(PG2)
model=AutoModelForSequenceClassification.from_pretrained(PG2, torch_dtype=torch.float32).eval().cuda()

def chunks_of(text):
    ids=tok(text or '', add_special_tokens=False)['input_ids']
    if not ids: return ['']
    out=[]; i=0
    while i < len(ids):
        out.append(tok.decode(ids[i:i+CHUNK])); i += CHUNK-STRIDE
        if i >= len(ids): break
    return out

@torch.no_grad()
def score(texts, bs=16):
    res=[]
    for i in range(0,len(texts),bs):
        enc=tok(texts[i:i+bs], padding=True, truncation=True, max_length=MAXLEN,
                return_tensors='pt').to('cuda')
        res += torch.softmax(model(**enc).logits,-1)[:,1].cpu().tolist()
    return res

def run(trace, name):
    rows=[json.loads(l) for l in open(trace,encoding='utf-8')]
    variants={
        'action': [r['current_action'] for r in rows],
        'history': [r.get('history_full') or r.get('history') or '' for r in rows],
        'concat': [(r['instruction'] or '')+'\n'+(r.get('history_full') or r.get('history') or '')+'\n'+(r['current_action'] or '') for r in rows],
    }
    meta=[]
    for vi,vname in enumerate(variants):
        flat=[]; idx=[]
        for i,t in enumerate(variants[vname]):
            cs=chunks_of(t)
            for j,c in enumerate(cs): flat.append(c); idx.append((i,j,len(cs)))
        sc=score(flat)
        byrec={}
        for (i,j,n),s in zip(idx,sc):
            byrec.setdefault(i, []).append(s)
            meta.append(dict(record=i, variant=vname, chunk=j, n_chunks=n, score=float(s)))
        recs=[]
        for i,r in enumerate(rows):
            ss=byrec.get(i,[0.0])
            recs.append(dict(idx=i, task_id=r['user_task'],
                             scenario_id='%s|%s'%(r['user_task'],r.get('injection_task')),
                             tool=r['tool'], gamma=None,
                             record_score=float(max(ss)), max_chunk=float(max(ss)),
                             score_mean=float(np.mean(ss)), n_chunks=len(ss),
                             hist_len=len(r.get('history') or ''),
                             hist_full_len=len(r.get('history_full') or r.get('history') or '')))
        with open(os.path.join(OUT,'pg2_%s_%s.jsonl'%(name,vname)),'w',encoding='utf-8') as f:
            for x in recs: f.write(json.dumps(x,ensure_ascii=False)+'\n')
        print('  %-8s %-7s records=%d chunks=%d  score mean=%.3f max=%.3f'%(
            name,vname,len(recs),sum(x['n_chunks'] for x in recs),
            float(np.mean([x['record_score'] for x in recs])),
            float(np.max([x['record_score'] for x in recs]))), flush=True)
    with open(os.path.join(OUT,'pg2_chunks_%s.jsonl'%name),'w',encoding='utf-8') as f:
        for x in meta: f.write(json.dumps(x,ensure_ascii=False)+'\n')

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--trace',required=True); ap.add_argument('--name',required=True)
    a=ap.parse_args(); run(a.trace,a.name)
