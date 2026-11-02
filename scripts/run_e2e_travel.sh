#!/bin/bash
# travel 端到端：守卫臂 vs 已采集基线（同一批 task/injection）。
# 用法: bash scripts/run_e2e_travel.sh <ADAPTER> [INJECTIONS]
set -u
A="${1:?adapter}"
INJ="${2:-injection_task_0,injection_task_1}"
UTIL="${3:-0.72}"
ROOT=/data/projects/guardrails
cd "$ROOT"
L="$ROOT/results/e2e/run_e2e_travel.log"
mkdir -p "$ROOT/results/e2e"

echo "[$(date +%H:%M:%S)] TRAVEL / $A / inj=$INJ / util=$UTIL" | tee -a "$L"
GUARD_DEVICE="${GUARD_DEVICE:-cuda}" bash scripts/e2e_guard.sh travel "$A" "$INJ" "$UTIL" "" "" \
  2>&1 | tail -3 | tee -a "$L"

DIR="$ROOT/results/e2e/travel/${A}_inj$(echo "$INJ" | sed 's/injection_task_//g; s/,/-/g')"
/data/conda/envs/guard/bin/python scripts/e2e_compare.py --suite travel \
  --baseline "$ROOT/results/ad_v3/travel/scen_merged.jsonl" \
  --runs "$DIR/scen.jsonl" 2>&1 | tee -a "$L"
echo "[$(date +%H:%M:%S)] TRAVEL_E2E_DONE" | tee -a "$L"
