#!/bin/bash
# B1: slack 补 M0 + banking 扩到 4 个注入；B2: slack 补全 5 个注入
set -u
cd /data/projects/guardrails
L=/data/projects/guardrails/results/auto_b1b2.log
mkdir -p /data/projects/guardrails/results
say() { echo "[$(date +%H:%M:%S)] $*" >> "$L"; }

say "B1-1 slack M0 (inj1,3, both)"
bash scripts/e2e_guard.sh slack m2_HBnt_s0 injection_task_1,injection_task_3 0.72 '' _b1 block both
say "B1-1 rc=$?"

for A in none m2_HBnt_s0 m2_HB_s0; do
  say "B1-2 banking $A (inj4,6, attack-only)"
  bash scripts/e2e_guard.sh banking "$A" injection_task_4,injection_task_6 0.72 '' _b1 block attack
  say "B1-2 $A rc=$?"
done

for A in m2_HBnt_s0 m2_HB_s0; do
  say "B2 slack $A (inj2,4,5, attack-only)"
  bash scripts/e2e_guard.sh slack "$A" injection_task_2,injection_task_4,injection_task_5 0.72 '' _b2 block attack
  say "B2 $A rc=$?"
done
say "B1B2_DONE"
