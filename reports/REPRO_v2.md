# 复现清单（ad_v2：Guard / PG2 / 融合路由）

所有命令在 `lab` 服务器上执行，工作目录 `/data/projects/guardrails`，Python 环境 `/data/conda/envs/guard/bin/python`。

## 0. 前置条件

- 7B agent 服务（vLLM，CUDA 12.4 环境）：`bash /tmp/start_vllm12.sh`，端口 8000
  - 环境 `/data/conda/envs/vllm12`：vllm 0.6.6.post1 + torch 2.5.1+cu124 + transformers 4.45.2
  - `--max-model-len 12288`（**workspace 会出现超长错误，见审计报告 §5**）
- Guard 与 PG2 推理需独占显存：跑之前 `pkill -f 'vllm serve'`，之后再重启

## 1. 采集轨迹

```bash
# banking：16 用户任务 × (1 无注入 + 9 注入)
python scripts/ad_run.py --suite banking --mode both \
  --logdir runs/ad_bank2 --trace runs/ad_bank2_trace.jsonl \
  --scen-out results/ad_v2/scen_banking.jsonl --force

# workspace：40 用户任务 × 14 注入（仅攻击模式，无 clean 场景）
python scripts/ad_run.py --suite workspace --mode attack \
  --logdir runs/ad_ws2 --trace runs/ad_ws2_trace.jsonl \
  --scen-out results/ad_v2/scen_workspace.jsonl --force
```

轨迹字段：`suite, user_task, injection_task, step, tool, args, instruction, history(1600字符,给Guard用), history_full(完整,给PG2用), current_action`。

## 2. 标签

```bash
python scripts/ad_labels.py --trace runs/ad_bank2_trace.jsonl --name banking
python scripts/ad_labels.py --trace runs/ad_ws2_trace.jsonl  --name workspace
```

产出 `results/ad_v2/labels_{suite}.jsonl`、`scenarios_{suite}.jsonl`、`label_changelog.md`。

## 3. PG2 分段打分

```bash
python scripts/ad_pg2_v2.py --trace runs/ad_bank2_trace.jsonl --name banking
python scripts/ad_pg2_v2.py --trace runs/ad_ws2_trace.jsonl  --name workspace
```

参数：`CHUNK=400, STRIDE=64, MAXLEN=512, record_score=max(chunk)`。产出 `pg2_{suite}_{action|history|concat}.jsonl` 与 `pg2_chunks_{suite}.jsonl`。

## 4. Guard 判定

```bash
python scripts/ad_score.py --trace runs/ad_bank2_trace.jsonl --name banking
python scripts/ad_score.py --trace runs/ad_ws2_trace.jsonl  --name workspace
```

适配器：`guard/adapters/p1_15b_task_l2_s0`（冻结版 taskaware-v1，1.5B + LoRA）。

## 5. 标定（workspace，分组 K 折）

```bash
python scripts/ad_calibrate.py --suite workspace --folds 5 --seed 0
```

折按 `task_id` 分组（同一用户任务的全部注入变体落在同一折），seed=0。
产出 `calib_curve_workspace.csv`、`calib_workspace.json`、`frozen_selection.json`。

## 6. 冻结测试（banking）

```bash
python scripts/ad_test.py --suite banking --boot 2000
```

聚类 bootstrap：按 `task_id`，B=2000，seed=0。
产出 `test_banking_calllevel.csv`、`test_banking_curve.csv`、`test_banking.json`。

## 7. 场景级对照

```bash
python scripts/ad_scen.py banking
python scripts/ad_scen.py workspace
```

## 8. 执行器最小验证（不需要 LLM）

```bash
python scripts/ad_executor.py
```

退出码 0 = 五项全过。

## 9. 审计与混淆检验

```bash
python scripts/ad_audit.py                       # 文件指纹 / 字段 / 标签版本 / 分数方向
python /tmp/ad_lenconfound.py                    # 长度混淆与聚合方式敏感性
python /tmp/ad_pg2_trunc.py                      # 截断 vs 分段（需 GPU，可与 vLLM 共存）
```

## 10. 冻结件复核（必须为 74/74）

```bash
python scripts/check_taskaware_freeze.py
```

## 文件与随机种子汇总

| 项 | 值 |
|---|---|
| 折划分 | `group_folds(task_ids, K=5, seed=0)`，`np.random.default_rng(0).permutation` |
| 聚类 bootstrap | `B=2000, seed=0`，重采样单位 `task_id` |
| PG2 chunk | 400 token，stride 64 |
| Guard 生成 | `bs=16, max_new_tokens=6, do_sample=False` |
| 预注册 | `results/ad_v2/prereg.json`，sha256 `b5aa29961bb752766ff6…` |
