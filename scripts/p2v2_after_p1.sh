#!/bin/bash
# 等 P1 正常结束后，自动跑 P2-v2 全种子零样本评测（单实例、幂等、只读）。
#
# 规则落实：
#   R1 只等不干预：不 stop / 不重训 / 不动训练参数，仅等待 p1_run.py 退出。
#   R2 单实例 + 幂等：flock 独占锁；已完成则直接跳过；
#      P1 启动前按清单逐 run 核对身份/seed/模型/臂/lr/完成状态（p1_manifest_check.py），
#      任一缺失或不一致 -> P2V2_ABORT，不启动，保留已完成结果。
#   R3 不截断：交给 p2v2_eval_allseeds.py（它记录 max prompt tokens 与超长条数）。
#   R8 只读：P2-v2 数据哈希在启动前后比对；不写 data/、results/frozen/、p1_record.json。
set -u
cd /data/projects/guardrails || exit 1
LOG=results/p2v2/after_p1.log
mkdir -p results/p2v2

# ---------- R2：单实例锁（重复启动的第二个进程立即退出）
exec 9>results/p2v2/.after_p1.lock
if ! flock -n 9; then
  echo "[$(date '+%F %T')] 已有自动链在运行，退出（不重复启动）" >> "$LOG"
  exit 0
fi

# ---------- R2：幂等，已完成就不再做
if grep -q '^P2V2_DONE$' "$LOG" 2>/dev/null && [ -s results/p2v2/p2v2_allseeds.json ]; then
  echo "[$(date '+%F %T')] P2V2_DONE 且结果存在，跳过" >> "$LOG"
  exit 0
fi

P2_HASH0=$(sha256sum data/p2v2_pairs.jsonl | awk '{print $1}')
echo "[$(date '+%F %T')] guard start (waiting for P1)  p2v2=$P2_HASH0" >> "$LOG"

# ---------- R1：只等待，不动 P1
MAXWAIT=43200
t0=$(date +%s)
while pgrep -f 'scripts/p1_run.py' >/dev/null 2>&1 && ! grep -q '^P1_DONE' /tmp/p1_main.log; do
  sleep 60
  if [ $(( $(date +%s) - t0 )) -gt $MAXWAIT ]; then
    echo "[$(date '+%F %T')] TIMEOUT waiting P1" >> "$LOG"
    echo "P2V2_ABORT" >> "$LOG"
    exit 2
  fi
done
sleep 15   # 等 P1 进程真正退出、释放显存后再做校验与评测

# ---------- R2：按清单逐 run 校验（不看文件数量）
echo "[$(date '+%F %T')] P1 exited, running manifest check" >> "$LOG"
/data/conda/envs/guard/bin/python scripts/p1_manifest_check.py >> "$LOG" 2>&1
mrc=$?
if [ $mrc -ne 0 ]; then
  echo "[$(date '+%F %T')] ABORT: P1 产物清单校验未通过（缺 run 或身份不一致），" \
       "不启动 P2-v2；已完成结果全部保留" >> "$LOG"
  echo "P2V2_ABORT" >> "$LOG"
  exit 3
fi
echo "[$(date '+%F %T')] manifest PASS（16 训练 / 12 评测逐项核对）" >> "$LOG"

# ---------- R8：启动前再确认 P2-v2 未被改动
P2_HASH1=$(sha256sum data/p2v2_pairs.jsonl | awk '{print $1}')
if [ "$P2_HASH0" != "$P2_HASH1" ]; then
  echo "[$(date '+%F %T')] ABORT: P2-v2 哈希变化 $P2_HASH0 -> $P2_HASH1" >> "$LOG"
  echo "P2V2_ABORT" >> "$LOG"
  exit 4
fi

echo "[$(date '+%F %T')] start p2v2 all-seeds eval" >> "$LOG"
/data/conda/envs/guard/bin/python scripts/p2v2_eval_allseeds.py \
  --bs 12 --seeds 0,42,123 --models 15b,3b >> "$LOG" 2>&1
rc=$?
echo "[$(date '+%F %T')] eval rc=$rc" >> "$LOG"

P2_HASH2=$(sha256sum data/p2v2_pairs.jsonl | awk '{print $1}')
if [ "$P2_HASH0" != "$P2_HASH2" ]; then
  echo "[$(date '+%F %T')] WARN: 评测后 P2-v2 哈希变化，需人工核查" >> "$LOG"
fi

if [ $rc -eq 0 ]; then echo "P2V2_DONE" >> "$LOG"; else echo "P2V2_FAIL" >> "$LOG"; fi
exit $rc
