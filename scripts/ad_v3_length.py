"""阶段 2：PG2 是不是只是长度检测器。
场景级特征 → AUC/PR-AUC → 长度基线的增量价值（task 分组 CV + 聚类 bootstrap）→ 来源隔离评分。
只做诊断，不产生任何阈值。
"""
import json, os, sys, collections, hashlib
import numpy as np
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import roc_auc_score, average_precision_score
from transformers import AutoModelForSequenceClassification, AutoTokenizer

ROOT = '/data/projects/guardrails'
OUT = os.path.join(ROOT, 'results/ad_v3/length')
os.makedirs(OUT, exist_ok=True)
J = lambda p: [json.loads(l) for l in open(p, encoding='utf-8')]
SEP = '\n---\n'
K_TOP = 3

rows = J(os.path.join(ROOT, 'runs/ad_bank2_trace.jsonl'))
lab = J(os.path.join(ROOT, 'results/ad_v2/labels_banking.jsonl'))
pg = J(os.path.join(ROOT, 'results/ad_v2/pg2_banking_concat.jsonl'))
assert len(rows) == len(lab) == len(pg)
for i, r in enumerate(rows):
    r['sid'] = lab[i]['scenario_id']
    r['task'] = lab[i]['task_id']
    r['label'] = lab[i]['attack_call_label']
    r['uncertain'] = bool(lab[i].get('uncertain'))
    r['pg2'] = float(pg[i]['record_score'])
    r['n_chunks'] = int(pg[i]['n_chunks'])
    r['hlen'] = len(r.get('history_full') or r.get('history') or '')

# ---------- 2.1 场景级特征 ----------
sc = collections.defaultdict(list)
for r in rows:
    sc[r['sid']].append(r)
feats = []
for sid, rs in sorted(sc.items()):
    s = sorted(x['pg2'] for x in rs)[::-1]
    feats.append(dict(
        scenario_id=sid, task_id=rs[0]['task'],
        injection_task=rs[0]['injection_task'],
        total_history_chars=sum(x['hlen'] for x in rs),
        max_history_chars=max(x['hlen'] for x in rs),
        total_chunks=sum(x['n_chunks'] for x in rs),
        max_chunks_per_call=max(x['n_chunks'] for x in rs),
        step_count=len(rs),
        max_step_idx=max(x['step'] for x in rs),
        pg2_max_score=max(s),
        pg2_mean_score=float(np.mean(s)),
        pg2_topk_mean=float(np.mean(s[:K_TOP])),
        n_attack_calls=sum(1 for x in rs if x['label'] == 'attack'),
        n_uncertain=sum(1 for x in rs if x['uncertain']),
    ))
for f in feats:
    f['compromised'] = int(f['n_attack_calls'] > 0)
    f['injected'] = int(f['injection_task'] is not None)
print('场景 %d（compromised %d / injected %d）' % (
    len(feats), sum(f['compromised'] for f in feats), sum(f['injected'] for f in feats)))

with open(os.path.join(OUT, 'scenario_features.csv'), 'w', encoding='utf-8') as fh:
    keys = list(feats[0].keys())
    fh.write(','.join(keys) + '\n')
    for f in feats:
        fh.write(','.join(str(f[k]) for k in keys) + '\n')

# ---------- 2.2 单一分数的判别力 ----------
SCORES = [('total_history_chars', '累计 history 字符'), ('max_history_chars', '最大 history 字符'),
          ('step_count', '调用次数'), ('max_step_idx', '最大步号'),
          ('total_chunks', '累计 chunk 数'), ('max_chunks_per_call', '单次最大 chunk 数'),
          ('pg2_max_score', 'PG2 最高分'), ('pg2_mean_score', 'PG2 平均分'),
          ('pg2_topk_mean', 'PG2 top%d 均值' % K_TOP)]
res = {'n_scenarios': len(feats), 'labels': {}}
for lname, lkey in (('compromised', 'compromised'), ('injected', 'injected')):
    y = np.array([f[lkey] for f in feats])
    tab = []
    for k, cn in SCORES:
        s = np.array([f[k] for f in feats], float)
        tab.append(dict(key=k, name=cn, auc=float(roc_auc_score(y, s)),
                        pr_auc=float(average_precision_score(y, s))))
    res['labels'][lname] = dict(n_pos=int(y.sum()), scores=tab)
    print('\n=== 标签：%s（正例 %d / %d）===' % (lname, y.sum(), len(y)))
    print('  %-22s %7s %8s' % ('分数', 'ROC-AUC', 'PR-AUC'))
    for t in tab:
        print('  %-22s %7.3f %8.3f' % (t['name'], t['auc'], t['pr_auc']))

json.dump(res, open(os.path.join(OUT, 'scenario_auc.json'), 'w'), ensure_ascii=False, indent=1)

# ---------- 2.3 增量价值 ----------
def folds(tasks, K=5, seed=0):
    ts = sorted(set(tasks))
    perm = np.random.default_rng(seed).permutation(len(ts))
    return {ts[i]: int(perm[i] % K) for i in range(len(ts))}

def cv_auc(X, y, task_arr, K=5, seed=0):
    fm = folds(task_arr, K, seed)
    fid = np.array([fm[t] for t in task_arr])
    oof = np.zeros(len(y))
    for f in range(K):
        tr, te = fid != f, fid == f
        if len(set(y[tr])) < 2 or te.sum() == 0:
            oof[te] = y[tr].mean() if tr.sum() else 0.5
            continue
        m = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000))
        m.fit(X[tr], y[tr])
        oof[te] = m.predict_proba(X[te])[:, 1]
    return oof, fid

BASE = ['total_history_chars', 'max_history_chars', 'step_count', 'max_chunks_per_call']
PG = ['pg2_max_score', 'pg2_mean_score', 'pg2_topk_mean']
inc = {}
for lname in ('compromised', 'injected'):
    y = np.array([f[lname] for f in feats])
    tasks = [f['task_id'] for f in feats]
    Xb = np.array([[*[np.log1p(f[k]) for k in BASE]] for f in feats])
    Xe = np.array([[*[np.log1p(f[k]) for k in BASE], *[f[k] for k in PG]] for f in feats])
    ob, fid = cv_auc(Xb, y, tasks)
    oe, _ = cv_auc(Xe, y, tasks)
    ab, ae = roc_auc_score(y, ob), roc_auc_score(y, oe)
    pb, pe = average_precision_score(y, ob), average_precision_score(y, oe)
    # task-level bootstrap on the OOF predictions
    by = collections.defaultdict(list)
    for i, t in enumerate(tasks):
        by[t].append(i)
    tk = sorted(by)
    rng = np.random.default_rng(0)
    db, de, dp = [], [], []
    for _ in range(2000):
        pick = rng.integers(0, len(tk), len(tk))
        idx = [i for j in pick for i in by[tk[j]]]
        yy = y[idx]
        if yy.min() == yy.max():
            continue
        a1 = roc_auc_score(yy, ob[idx]); a2 = roc_auc_score(yy, oe[idx])
        db.append(a1); de.append(a2); dp.append(a2 - a1)
    inc[lname] = dict(
        n_pos=int(y.sum()), n_scen=len(y),
        baseline_auc=ab, enhanced_auc=ae, delta_auc=ae - ab,
        delta_ci=[float(np.percentile(dp, 2.5)), float(np.percentile(dp, 97.5))],
        baseline_pr=pb, enhanced_pr=pe, delta_pr=pe - pb,
        baseline_auc_ci=[float(np.percentile(db, 2.5)), float(np.percentile(db, 97.5))],
        enhanced_auc_ci=[float(np.percentile(de, 2.5)), float(np.percentile(de, 97.5))],
        p_delta_le0=float(np.mean(np.array(dp) <= 0)))
    print('\n=== 增量价值（%s，5 折按 task 分组，bootstrap 2000）===' % lname)
    print('  长度基线          AUC %.3f [%.3f, %.3f]  PR-AUC %.3f' % (
        ab, *inc[lname]['baseline_auc_ci'], pb))
    print('  基线 + PG2        AUC %.3f [%.3f, %.3f]  PR-AUC %.3f' % (
        ae, *inc[lname]['enhanced_auc_ci'], pe))
    print('  ΔAUC = %+.3f  [%+.3f, %+.3f]   P(Δ≤0) = %.3f' % (
        ae - ab, *inc[lname]['delta_ci'], inc[lname]['p_delta_le0']))

# 长度分层：同长度区间内 PG2 还有没有区分力
strat = {}
y = np.array([f['compromised'] for f in feats])
L = np.array([f['total_history_chars'] for f in feats], float)
q = np.quantile(L, np.linspace(0, 1, 6))
det = []
for i in range(5):
    m = (L >= q[i]) & ((L <= q[i + 1]) if i == 4 else (L < q[i + 1]))
    n1, n0 = int(y[m].sum()), int((~y[m].astype(bool)).sum())
    r = dict(bin=i, lo=float(q[i]), hi=float(q[i + 1]), n=int(m.sum()), n_pos=n1, n_neg=n0, auc=None)
    if n1 >= 2 and n0 >= 2:
        r['auc'] = float(roc_auc_score(y[m], np.array([f['pg2_max_score'] for f in feats])[m]))
    det.append(r)
strat['pg2_max_by_length_quintile'] = det
print('\n=== 长度五分位内的 PG2 最高分 AUC（标签：compromised）===')
for d in det:
    print('  [%7.0f, %7.0f) n=%2d 正=%d 负=%d  AUC=%s' % (
        d['lo'], d['hi'], d['n'], d['n_pos'], d['n_neg'],
        '%.3f' % d['auc'] if d['auc'] is not None else '样本不足'))

# ---------- 2.4 来源隔离 ----------
tok = AutoTokenizer.from_pretrained('/data/hf_cache/pg2-86m')
model = AutoModelForSequenceClassification.from_pretrained(
    '/data/hf_cache/pg2-86m', torch_dtype=torch.float32).eval().cuda()

@torch.no_grad()
def pg2_batch(texts, bs=32):
    out = []
    for i in range(0, len(texts), bs):
        enc = tok(texts[i:i + bs], padding=True, truncation=True, max_length=512,
                  return_tensors='pt').to('cuda')
        out += torch.softmax(model(**enc).logits, -1)[:, 1].cpu().tolist()
    return out

def segs(h):
    out = []
    for s in (h or '').split(SEP):
        s = s.strip()
        if not s:
            continue
        out.append(('assistant', s[11:]) if s.startswith('assistant: ') else ('tool', s))
    return out

# 每段独立评分（同一文本只评一次）
uniq = {}
for r in rows:
    for kind, txt in segs(r.get('history_full') or r.get('history') or ''):
        if kind == 'tool':
            uniq.setdefault(hashlib.sha1(txt.encode()).hexdigest(), txt)
print('\n工具输出片段：语料级唯一 %d 段' % len(uniq))
keys = list(uniq)
vals = pg2_batch([uniq[k] for k in keys])
score_of = dict(zip(keys, vals))

# 按场景维护"已出现片段"集合：同一段注入内容在后续步骤重复出现时不计为新证据
toollvl = []
calllvl = []
seen = collections.defaultdict(set)          # scenario_id -> 已计过的片段 hash
for r in rows:
    sg = segs(r.get('history_full') or r.get('history') or '')
    newsc = []
    for kind, txt in sg:
        if kind != 'tool':
            continue
        hh = hashlib.sha1(txt.encode()).hexdigest()
        if hh in seen[r['sid']]:
            continue
        seen[r['sid']].add(hh)
        newsc.append(score_of[hh])
        toollvl.append(dict(scenario_id=r['sid'], step=r['step'], h=hh, score=score_of[hh]))
    calllvl.append(dict(scenario_id=r['sid'], step=r['step'],
                        new_tool_score=max(newsc) if newsc else 0.0, n_new=len(newsc)))

def auc_or_none(y, s):
    y = np.asarray(y); s = np.asarray(s, float)
    return float(roc_auc_score(y, s)) if 0 < y.sum() < len(y) else None

cy = np.array([f['compromised'] for f in feats])
cy_map = {f['scenario_id']: f['compromised'] for f in feats}
iy_map = {f['scenario_id']: f['injected'] for f in feats}
call_auc = auc_or_none([cy_map[c['scenario_id']] for c in calllvl], [c['new_tool_score'] for c in calllvl])
scen_new = collections.defaultdict(float)
for c in calllvl:
    scen_new[c['scenario_id']] = max(scen_new[c['scenario_id']], c['new_tool_score'])
scen_new_auc = auc_or_none([cy_map[k] for k in scen_new], [scen_new[k] for k in scen_new])
inj_auc = auc_or_none([iy_map[k] for k in scen_new], [scen_new[k] for k in scen_new])
src = dict(n_unique_tool_segments=len(uniq),
           n_new_tool_segments=len(toollvl),
           call_level=dict(metric='max PG2 over new tool-output segments in that call',
                           auc_compromised=call_auc),
           scenario_level=dict(metric='max over calls of the above',
                               auc_compromised=scen_new_auc, auc_injected=inj_auc))
print('\n=== 来源隔离（只用工具输出，不含 assistant 文本与用户指令）===')
print('  新进入上下文的工具片段总数 = %d（按场景去重，重复注入不重复计）' % len(toollvl))
print('  call 级 AUC(compromised) = %s' % ('%.3f' % call_auc if call_auc else '不可算'))
print('  场景级 AUC(compromised) = %s | AUC(injected) = %s' % (
    '%.3f' % scen_new_auc if scen_new_auc else '-', '%.3f' % inj_auc if inj_auc else '-'))

json.dump(dict(incremental=inc, length_strata=strat, source_isolation=src),
          open(os.path.join(OUT, 'incremental.json'), 'w'), ensure_ascii=False, indent=1)
print('\n-> results/ad_v3/length/{scenario_features.csv,scenario_auc.json,incremental.json}')
