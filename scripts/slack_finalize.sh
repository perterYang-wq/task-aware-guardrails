#!/bin/bash
# slack 收尾：合并分片 → 生成标签 → 五臂评测
set -u
cd /data/projects/guardrails || exit 1
D=results/ad_v3/slack

echo "== 1. 合并场景 =="
/data/conda/envs/guard/bin/python - <<'PY'
import json, glob, os
D = '/data/projects/guardrails/results/ad_v3/slack'
rows = []
for f in sorted(glob.glob(D + '/scen_*.jsonl')):
    rows += [json.loads(l) for l in open(f, encoding='utf-8')]
seen = {}
for r in rows:
    seen.setdefault((r['user_task'], r['injection_task']), r)
with open(D + '/scen_merged.jsonl', 'w', encoding='utf-8') as f:
    for k in sorted(seen, key=lambda x: (x[0], x[1] or '')):
        f.write(json.dumps(seen[k], ensure_ascii=False) + '\n')
a = [v for v in seen.values() if v['gate'] == 'attack']
c = [v for v in seen.values() if v['gate'] == 'clean']
print('分片 %d 行 → 去重 %d 场景（clean %d / attack %d）' % (len(rows), len(seen), len(c), len(a)))
print('攻击成功 %d | 暴露 %d | overflow %d | loop %d | no_tool %d | 平均步数 %.1f' % (
    sum(1 for r in a if r['attack_success']), sum(r['injection_exposed'] for r in a),
    sum(1 for r in a if r['agent_failure'] == 'context_overflow'),
    sum(1 for r in a if r['agent_failure'] == 'tool_loop'),
    sum(1 for r in a if r['agent_failure'] == 'no_tool_call'),
    sum(r['n_steps'] for r in a) / max(1, len(a))))
print('任务数 %d' % len({v['user_task'] for v in seen.values()}))
PY

echo "== 2. 合并轨迹 =="
cat $D/trace_A.jsonl $D/trace_B.jsonl $D/trace_C.jsonl > $D/trace_merged.jsonl 2>/dev/null
wc -l $D/trace_merged.jsonl

echo "== 3. 生成标签 =="
/data/conda/envs/guard/bin/python /tmp/make_labels_slack.py $D/trace_merged.jsonl $D/labels_slack_v2.jsonl

echo "== 4. 五臂评测 =="
/data/conda/envs/guard/bin/python scripts/contract_eval_v2.py \
  --suite slack --trace $D/trace_merged.jsonl \
  --out $D/contract_eval_v2.json
echo "SLACK_DONE"
