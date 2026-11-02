#!/bin/bash
# (b) M1 + REVIEW=allow 补齐调用级；然后 (a) 扩样到 injection_task_2/3（只跑攻击，复用已有干净场景）
set -u
cd /data/projects/guardrails
L=/data/projects/guardrails/results/chain_p1b.log
say() { echo "[$(date +%H:%M:%S)] $*" >> "$L"; }

say "b1 M1 travel allow (both modes)"
bash scripts/e2e_guard.sh travel m2_HB_s0 injection_task_0,injection_task_1 0.72 '' _calls allow both
say "b1 rc=$?"

say "a1 M0 travel inj2,3 attack-only"
bash scripts/e2e_guard.sh travel m2_HBnt_s0 injection_task_2,injection_task_3 0.72 '' _calls2 block attack
say "a1 rc=$?"

say "a2 M1 travel inj2,3 attack-only"
bash scripts/e2e_guard.sh travel m2_HB_s0 injection_task_2,injection_task_3 0.72 '' _calls2 block attack
say "a2 rc=$?"
say "CHAIN_P1B_DONE"
