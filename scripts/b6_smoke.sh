#!/bin/bash
set -u
cd /data/projects/guardrails
rm -rf results/e2e/travel/m2_HB_s0_b6smoke*
bash scripts/e2e_guard.sh travel m2_HB_s0 injection_task_1 0.72 user_task_1 _b6smoke_meta block attack meta
echo "SMOKE_META_RC=$?"
bash scripts/e2e_guard.sh travel m2_HB_s0 injection_task_1 0.72 user_task_1 _b6smoke_obf block attack obfusc
echo "SMOKE_OBF_RC=$?"
echo B6_SMOKE_DONE
