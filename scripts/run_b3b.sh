#!/bin/bash
# B3 补：travel 的 Task-Shield 跑完后，接着跑 slack（in-dist，基线效用 61.9%，才能看出判官的效用代价）
set -u
cd /data/projects/guardrails
L=/data/projects/guardrails/results/auto_b3b.log
say() { echo "[$(date +%H:%M:%S)] $*" >> "$L"; }
for i in $(seq 1 240); do
  pgrep -f 'travel --mode both --injections injection_task_0,injection_task_1' > /dev/null || break
  sleep 15
done
say "travel tshield 结束，启动 slack tshield"
bash scripts/e2e_guard.sh slack tshield injection_task_1,injection_task_3 0.72 '' _b3 block both
say "slack tshield rc=$?"
say "B3B_DONE"
