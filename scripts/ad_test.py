"""阶段 5/6：把 workspace 选出的阈值冻结，在 banking 上做独立测试。
不在此脚本里做任何选择；曲线只是描述性输出。"""
import json, os, sys, argparse, csv
import numpy as np
sys.path.insert(0, '/data/projects/guardrails')
sys.path.insert(0, '/data/projects/guardrails/scripts')
import ad_eval_lib as L

ap = argparse.ArgumentParser()
ap.add_argument('--suite', default='banking')
ap.add_argument('--frozen', default=os.path.join(L.OUT, 'frozen_selection.json'))
ap.add_argument('--boot', type=int, default=2000)
a = ap.parse_args()

rows = L.load(a.suite)
fz = json.load(open(a.frozen, encoding='utf-8'))
print('frozen from %s: selected=%s  infeasible=%s' % (
    fz['suite'], list(fz['selected']), fz['infeasible']))

# 1) 冻结策略（只用选出的 tau）
main = []
call_rows = []
for pol in L.POLICIES:
    if pol in fz['selected']:
        tau = fz['selected'][pol]['tau']
        dec = [L.decide(pol, r, tau) for r in rows]
        m = L.metrics(rows, dec)
        ci, ntask = L.cluster_bootstrap(rows, dec, B=a.boot, seed=0)
        m.update(policy=pol, tau=tau, status='selected', cluster_unit='task_id',
                 n_clusters=ntask, boot= a.boot)
        m['ci'] = ci
        main.append(m)
        for i, r in enumerate(rows):
            call_rows.append(dict(idx=i, task_id=r['task_id'], scenario_id=r['scenario_id'],
                                  tool=r['tool_name'], gamma=r['gamma'],
                                  guard=r['guard'], pg2=round(r['pg2'], 4),
                                  label=r['attack_call_label'], uncertain=bool(r.get('uncertain')),
                                  policy=pol, tau=tau, decision=dec[i]))
    else:
        main.append(dict(policy=pol, tau=None, status='INFEASIBLE'))

# 2) 描述性曲线（不做任何选择）
curve = []
for pol in L.POLICIES:
    for t in ([0.0] if pol == 'A_guard' else
              [0.02, 0.05, 0.08, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]):
        dec = [L.decide(pol, r, t) for r in rows]
        m = L.metrics(rows, dec)
        m.update(policy=pol, tau=t, status='descriptive')
        curve.append(m)

OUT = L.OUT
with open(os.path.join(OUT, 'test_%s_calllevel.csv' % a.suite), 'w', newline='', encoding='utf-8') as f:
    if call_rows:
        w = csv.DictWriter(f, fieldnames=list(call_rows[0].keys()))
        w.writeheader()
        for r in call_rows:
            w.writerow(r)
with open(os.path.join(OUT, 'test_%s_curve.csv' % a.suite), 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=list(curve[0].keys()))
    w.writeheader()
    for r in curve:
        w.writerow(r)
json.dump(dict(suite=a.suite, frozen_from=fz['suite'], selected=main, curve=curve),
          open(os.path.join(OUT, 'test_%s.json' % a.suite), 'w'), ensure_ascii=False, indent=1)

print('\n=== banking 独立测试（冻结阈值）===')
n_atk = len([r for r in rows if r['attack_call_label'] == 'attack'])
n_leg = len([r for r in rows if r['attack_call_label'] == 'legit'])
n_asc = len({r['scenario_id'] for r in rows if r['attack_call_label'] == 'attack'})
n_csc = len({r['scenario_id'] for r in rows if str(r['scenario_id']).endswith('|None')})
print('调用 %d（攻击 %d / 合法 %d）  场景：有攻击 %d / 无注入 %d' % (
    len(rows), n_atk, n_leg, n_asc, n_csc))
for m in main:
    if m['status'] != 'selected':
        print('%-14s   -   | INFEASIBLE（无 tau 满足合法中断 ≤ %.0f%%）' % (m['policy'], fz['budget'] * 100))
        continue
    ci = m['ci'].get('leg_interrupt', (float('nan'),) * 2)
    print('%-14s %5.2f | %.2f/%.2f/%.2f  %.3f | %.3f %.3f  %.3f [%.3f,%.3f] | %2d/%2d=%.3f | %d/%d' % (
        m['policy'], m['tau'], m['atk_deny'], m['atk_review'], m['atk_allow'], m['atk_block'],
        m['leg_deny'], m['leg_review'], m['leg_interrupt'], ci[0], ci[1],
        m['scen_defended'], m['n_atk_scen'], m['scen_defense'],
        m['clean_interrupted'], m['n_clean_scen']))
print('\n不确定样本中断率:', {m['policy']: round(m['unc_interrupt'], 3)
                        for m in main if m['status'] == 'selected'})
