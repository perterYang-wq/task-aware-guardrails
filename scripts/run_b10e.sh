#!/bin/bash
set -u
cd /data/projects/guardrails
L=/data/projects/guardrails/results/auto_b10e.log
say() { echo "[$(date +%H:%M:%S)] $*" >> "$L"; }
say "HB-sm slack e2e"
bash scripts/e2e_guard.sh slack m2_SM_s0 injection_task_1,injection_task_3 0.72 '' _b10e block both
say "rc=$?"
say "B10E_DONE"
