#!/bin/bash
# B7：跨 agent 骨干（7B -> 3B）。等 B10/B8 链结束后换模型，跑 travel 60 场景 × {E0, M1}。
set -u
cd /data/projects/guardrails
L=/data/projects/guardrails/results/auto_b7.log
say() { echo "[$(date +%H:%M:%S)] $*" >> "$L"; }

for i in $(seq 1 240); do
  grep -q B10B8_DONE /data/projects/guardrails/results/auto_b10b8.log && break
  sleep 15
done
say "B10/B8 结束，停 7B vLLM"
pkill -f 'vllm.entrypoints' || true
sleep 10

say "B7a 3B agent + 无守卫"
bash scripts/e2e_guard_3b.sh travel none injection_task_0,injection_task_1 0.72 '' _b7 block both
say "B7a rc=$?"

say "B7b 3B agent + M1"
bash scripts/e2e_guard_3b.sh travel m2_HB_s0 injection_task_0,injection_task_1 0.72 '' _b7 block both
say "B7b rc=$?"
say "B7_DONE"
