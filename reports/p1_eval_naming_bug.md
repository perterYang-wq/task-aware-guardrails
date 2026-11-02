# P1 测试评估产物命名不一致（已恢复，无数据丢失）

## 现象

2026-10-31 03:29–03:43 的 P1 收尾阶段，主日志连续出现：

```
[FAIL-eval] p1_15b_task_l2_s0 rc=0
...
[FAIL-eval] p1_3b_nt_l2_s123 rc=0
```

`rc=0` 却判失败，随后按预期出现 `P1_DONE`，自动链的清单校验报
`eval 0/12 ok` → 写 `P2V2_ABORT`，**未启动 P2-v2**（门禁行为正确）。

## 根因

`run_guard.py` 内部把自己的输出 tag 拼成 `"%s_%s" % (a.tag, a.part)`，落盘为

```
results/p1_15b_task_l2_s0_test.jsonl
```

而 `p1_run.py::evaluate()` 回收时找的是

```python
src = os.path.join(ROOT, "results", "%s.jsonl" % tag)   # 少了 "_test"
```

于是 12 次评估**全部真实跑完并写出结果**，但回收步骤找不到文件、返回 None，
`preds/` 目录为空。

## 证据

12 个文件均在，时间戳 03:34–03:43，大小 ~108.9 KB，内容完整；
评估日志末尾显示正常指标，例如 `p1_3b_task_l2_s0`：

```
配对准确率（同动作文本）= 88.3%  配对数=90  动作数=47
```

## 恢复

按 `results/{tag}_test.jsonl → results/p1/preds/{tag}_{arm}.jsonl` 复制 12 个文件
（`cp -n`，不覆盖任何已有内容），随后用清单校验器逐项核对：

```
[manifest] train 16/16 ok   eval 12/12 ok   P1_DONE=True
[manifest] PASS
```

校验项包括：行数 335、sid 集合与 test 完全一致且不重复、gold 分布一致、
解析失败率、raw 非空。全部通过，说明复制的是正确的评估结果。

## 影响与处置

- **无数据丢失、无需重训、无需重跑评估**；训练产物与 12 份预测均在。
- `p1_record.json` 的 `evals` 字段值是 `None`（当时返回 None 后写入），键齐全但路径为空。
  该字段只被人工追溯使用，`p2v2_eval_allseeds.py` 只读 `lr_choice`，不影响评测与报告。
  为避免改动 P1 记录文件，**未回写**，映射关系以本文档为准。
- `p1_run.py` 未修改（P1 协议冻结）。若日后重跑，只需把
  `evaluate()` 中的 `"%s.jsonl" % tag` 改为 `"%s_%s.jsonl" % (tag, "test")`。

## 时间线

| 时间 | 事件 |
|---|---|
| 03:29–03:43 | 12 次评估实际执行成功，落盘为 `*_test.jsonl` |
| 03:43:47 | 守卫清单校验失败 → `P2V2_ABORT`（未评测，符合规则） |
| 09:46 | 补齐 preds 后校验通过，启动 P2-v2 全种子评测 |
