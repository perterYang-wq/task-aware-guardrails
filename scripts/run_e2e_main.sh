#!/bin/bash
# 端到端主实验：同一批任务/注入上，比较 无守卫 / 标准 SFT / 本文方法。
#
# 用法: bash scripts/run_e2e_main.sh [SUITE] [INJECTIONS]
# 预检: 先用 1 个任务试跑，确认 7B(vLLM) 与 1.5B guard 能在 24G 卡上共存；
#       若一条守卫判定都没发生（多半 OOM 或加载失败），整体回退到 CPU 守卫。
set -u
SUITE="${1:-banking}"
INJ="${2:-injection_task_0,injection_task_2,injection_task_4,injection_task_7}"
ROOT=/data/projects/guardrails
cd "$ROOT"
L="$ROOT/results/e2e/run_e2e_main.log"
mkdir -p "$ROOT/results/e2e"
DEV="${GUARD_DEVICE:-cuda}"

if [ "$DEV" = "cuda" ]; then
  echo "[preflight] guard on cuda ..." | tee -a "$L"
  PRE="$ROOT/results/e2e/$SUITE/m2_S_s0_inj0_pre"
  rm -rf "$PRE"
  GUARD_DEVICE=cuda timeout 1200 bash scripts/e2e_guard.sh "$SUITE" m2_S_s0 \
      injection_task_0 0.80 user_task_0 "" 2>&1 | tail -3 | tee -a "$L"
  N=$(python3 - "$PRE/scen.jsonl" <<'PY'
import json, os, sys
p = sys.argv[1]
if not os.path.exists(p):
    print(0); raise SystemExit
print(sum(len(json.loads(l).get("guard_hits") or []) for l in open(p)))
PY
)
  echo "[preflight] guard_hits=$N" | tee -a "$L"
  if [ "${N:-0}" -lt 1 ]; then
    echo "[preflight] cuda 不可用 -> 整体改用 CPU 守卫" | tee -a "$L"
    DEV=cpu
  fi
fi

for A in none m2_S_s0 m2_HP_s0; do
  echo "[$(date +%H:%M:%S)] === $SUITE / $A (guard=$DEV) ===" | tee -a "$L"
  if [ "$A" = "none" ]; then
    bash scripts/e2e_guard.sh "$SUITE" none "$INJ" 0.80 "" "" 2>&1 | tail -3 | tee -a "$L"
  else
    GUARD_DEVICE="$DEV" bash scripts/e2e_guard.sh "$SUITE" "$A" "$INJ" 0.80 "" "" 2>&1 \
      | tail -3 | tee -a "$L"
  fi
done
echo "[$(date +%H:%M:%S)] E2E_DONE" | tee -a "$L"
