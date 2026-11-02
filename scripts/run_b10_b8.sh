#!/bin/bash
# 7B 模型不换的情况下一次跑完：B10-2 / B10-3 / B10-1(两臂) / B8(两 seed)
set -u
cd /data/projects/guardrails
L=/data/projects/guardrails/results/auto_b10b8.log
say() { echo "[$(date +%H:%M:%S)] $*" >> "$L"; }

say "B10-2 slack S 臂"
bash scripts/e2e_guard.sh slack m2_S_s0 injection_task_1,injection_task_3 0.72 '' _b10 block both
say "B10-2 rc=$?"

say "B10-3 slack M1 review=allow"
bash scripts/e2e_guard.sh slack m2_HB_s0 injection_task_1,injection_task_3 0.72 '' _b10 allow both
say "B10-3 rc=$?"

say "B10-1a slack 纯硬规则"
bash scripts/e2e_guard.sh slack hard injection_task_1,injection_task_3 0.72 '' _b10 block both
say "B10-1a rc=$?"

say "B10-1b slack M1+硬规则"
bash scripts/e2e_guard.sh slack m2_HB_s0 injection_task_1,injection_task_3 0.72 '' _b10hr block both 1
say "B10-1b rc=$?"

say "B8a travel M1 seed42"
bash scripts/e2e_guard.sh travel m2_HB_s42 injection_task_0,injection_task_1 0.72 '' _b8 block both
say "B8a rc=$?"

say "B8b travel M1 seed123"
bash scripts/e2e_guard.sh travel m2_HB_s123 injection_task_0,injection_task_1 0.72 '' _b8 block both
say "B8b rc=$?"
say "B10B8_DONE"
