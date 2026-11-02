## M0 对照（任务盲臂，同一批 34 条实例）

同一批实例、同一份 history / current_action，M0 用 `m2_HBnt_s0` 且 `task_aware=False`
（训练与部署口径一致，见 `scripts/phase2_eval_test.py` 的 ARMS 定义）。
判定口径与上表完全相同（P1 去载荷后是否仍 DENY）。CPU / float32 / greedy，0 GPU。

| 臂 | 总 DENY | payload-recognition | authorization-reasoning | 比例 |
|---|---|---|---|---|
| M1 `m2_HB_s0`（任务感知） | 32 | 6 | 26 | 81.2% |
| M0 `m2_HBnt_s0`（任务盲） | 27 | 5 | 22 | 81.5% |

分套件（M0）：travel 5 条 DENY（payload 1 / auth 4）；slack 22 条（payload 4 / auth 18）。

**交叉表（这次的实质证据）**：

| M1 的子集 | 条数 | M0 也 DENY | M0 判 ALLOW | M0 判 REVIEW |
|---|---|---|---|---|
| M1 的 authorization-reasoning（P1 仍 DENY） | 26 | 21 | 5 | 0 |
| M1 的 payload-recognition（P1 翻转） | 6 | 6 | 0 | 0 |

净增益口径：M1 的 26 条 auth-DENY 中，M0 在去载荷后仍 DENY 的有 20 条（76.9%），
只有 6 条是任务盲臂做不到的 —— 即**任务信息带来的净增量 = 6/32 = 18.8pp**。

M1 重跑一致性：与已落盘结果不一致 0 条 / 对齐失败 0 条。

**判定（action-prior）**：**动作先验为主。** M0 在 M1 的 auth-DENY 上覆盖 76.9%（≥70%），两臂 auth 比例差 0.2pp（≤10pp）—— 去载荷后仍拦的这些调用，任务盲模型同样拦，说明驱动它的是动作本身而非任务授权推理。第 4 节必须改写为「动作先验为主」，不能保留 76.5% 的表述。

