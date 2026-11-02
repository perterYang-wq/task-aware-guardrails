# 三处对账：final_metrics.csv / fig5 / state

真值来源：`probes/net_gain_sets.json`（`scripts/net_gain_sets.py` 从 P1 判定结果算出）。

| 量 | 真值 | final_metrics.csv | fig5 图注 | state.phase5 | 一致 |
|---|---|---|---|---|---|
| M1_only | 6 | 6.0 | 6 | 6 | ✓ |
| M0_only | 4 | 4.0 | 4 | 4 | ✓ |
| intersection | 20 | 20.0 | 20 | 20 | ✓ |
| robust_subset | 2 | 2.0 | 2 | 2 | ✓ |
| mcnemar_p | 0.7539 | 0.7539 | 0.754 | 0.7539 | ✓ |

## 结论

- 5 个数在三处**完全一致**，无手填。
- fig5 的 (c) 面板直接读 `probes/net_gain_sets.json`（脚本里 ng[...] 取值，已确认），不是把数字写死在绘图代码里。
- `b9_metrics.py` 的 net_gain 行同样读该 JSON，来源列已标注路径。

