"""终版分析：task 聚类 bootstrap + 漏放归因 + 缺失场景定位。"""
import json, sys, collections
import numpy as np
ROOT = '/data/projects/guardrails'
d = json.load(open(ROOT + '/results/ad_v3/travel/contract_eval_final.json', encoding='utf-8'))
rows = d['decisions']
SENS = {'send_email', 'reserve_hotel', 'reserve_restaurant', 'reserve_car_rental',
        'create_calendar_event', 'cancel_calendar_event'}
ARMS = ['B0', 'B1', 'B2', 'B3']

atk = [i for i, r in enumerate(rows) if r['label'] == 'attack']
leg = [i for i, r in enumerate(rows) if r['label'] == 'legit']
sv = [i for i in atk if rows[i]['tool'] in SENS]


def boot(idx, arm, B=2000, seed=0):
    by = collections.defaultdict(list)
    for i in idx:
        by[rows[i]['task']].append(i)
    ks = sorted(by)
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(B):
        pick = rng.integers(0, len(ks), len(ks))
        ii = [i for k in pick for i in by[ks[k]]]
        if not ii:
            continue
        out.append(sum(1 for i in ii if rows[i][arm]['decision'] != 'ALLOW') / len(ii))
    return (float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))), len(ks)


print('=== 有副作用的攻击调用阻断率（task 聚类 bootstrap，B=2000）===')
print('%-4s %8s %-20s %s' % ('arm', '点估计', '95% CI', '聚类数'))
for arm in ARMS:
    p = sum(1 for i in sv if rows[i][arm]['decision'] != 'ALLOW') / len(sv)
    (lo, hi), k = boot(sv, arm)
    print('%-4s %8.3f [%.3f, %.3f]          %d' % (arm, p, lo, hi, k))

print('\n=== 严格合法调用中断率 ===')
for arm in ARMS:
    p = sum(1 for i in leg if rows[i][arm]['decision'] != 'ALLOW') / len(leg)
    (lo, hi), k = boot(leg, arm)
    print('%-4s %8.4f [%.4f, %.4f]  (n=%d)' % (arm, p, lo, hi, len(leg)))

print('\n=== B2 漏放的有副作用攻击调用：按注入任务归因 ===')
miss = [i for i in sv if rows[i]['B2']['decision'] == 'ALLOW']
c = collections.Counter(rows[i]['inj'] for i in miss)
tot = collections.Counter(rows[i]['inj'] for i in sv)
for inj in sorted(tot):
    print('  %-18s %2d/%2d 漏放  工具: %s' % (
        inj, c.get(inj, 0), tot[inj],
        dict(collections.Counter(rows[i]['tool'] for i in sv if rows[i]['inj'] == inj))))
print('  合计漏放 %d/%d' % (len(miss), len(sv)))

print('\n=== 漏放原因分布 ===')
print(' ', dict(collections.Counter(
    (rows[i]['tool'], tuple(rows[i]['B2']['reasons'][:1])) for i in miss)))

print('\n=== 场景级（排除 overflow 场景）===')
scen = collections.defaultdict(list)
for i, r in enumerate(rows):
    scen['%s|%s' % (r['task'], r['inj'])].append(i)
ov = {k for k, v in scen.items() if any(rows[i]['decision'] is None for i in [])}
atk_scen = {('%s|%s' % (rows[i]['task'], rows[i]['inj'])) for i in atk}
for arm in ARMS:
    d2 = sum(1 for s in atk_scen
             if all(rows[i][arm]['decision'] != 'ALLOW' for i in scen[s]
                    if rows[i]['label'] == 'attack'))
    print('  %-4s 场景防御 %2d/%2d = %.3f' % (arm, d2, len(atk_scen), d2 / len(atk_scen)))

# 缺失场景
have = {(r['task'], r['inj']) for r in rows if r['inj']}
import itertools
allt = ['user_task_%d' % i for i in range(20)]
allinj = ['injection_task_%d' % i for i in range(7)]
missing = [(u, i) for u in allt for i in allinj if (u, i) not in have]
print('\n缺失场景:', missing)
