#!/bin/bash
cd /data/projects/guardrails || exit 1
setsid nohup bash scripts/p2v2_after_p1.sh >/dev/null 2>&1 </dev/null &
sleep 1
exit 0
