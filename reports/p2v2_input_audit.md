# P2-v2 输入侧验收：Chat Template 长度 与 No-task 输入一致性

对象：`data/p2v2_pairs.jsonl`（sha256 `1064eb7b3d34348b4ff376ea14207687ef14a77b865acecf7aa55879b81eb3f8`，冻结，本次检查**未改动任何数据**）

- 记录 632 / 配对 316 / 场景 79
- 长度口径：`apply_chat_template(tokenize=False, add_generation_prompt=True)` → `tok(text, add_special_tokens=False)`，与 `p2v2_eval.py` / `run_guard.py` 逐行一致
- 预算口径：训练 `max_len=1024`，推理 `max_new_tokens=6`

## 检查 1：完整 Chat Template 下的 token 长度

### 1.1 模板开销（此前口径漏算的部分）

`apply_chat_template` 会自动注入 Qwen 默认 **system 段**，因此完整输入比「纯内容分词」恒定多 **29** 个 token（632/632 条完全一致，非随机）：

```
template 开头：<|im_start|>system\nYou are Qwen, created by Alibaba Cloud. You are a helpful assistant.<|im_end|>\n<|im_start|>user\nX<|im...
```

这说明早期“max 1018 < 1024”的判断是**内容级**口径，完整模板下应为 1047。两个模型（1.5B / 3B）的分词器与模板完全相同（template_sha1 `9755ed0c4575`），训练与推理走同一模板，不存在 train/eval 模板错配。

### 1.2 长度分布（task 臂 / no-task 臂）

| 模型 | 臂 | min | p50 | p95 | max | >1024 | +6>1024 | 尾部破损 |
|---|---|---|---|---|---|---|---|---|
| 15b | task | 333 | 616 | 934 | 1047 | 6 | 6 | 0 |
| 15b | nt | 318 | 561 | 866 | 932 | 0 | 0 | 0 |
| 3b | task | 333 | 616 | 934 | 1047 | 6 | 6 | 0 |
| 3b | nt | 318 | 561 | 866 | 932 | 0 | 0 | 0 |

`apply_chat_template(tokenize=True)` 与 `tokenize=False→再分词` 的 token id 序列不一致 **0** 例；`add_special_tokens=True` 相对 False 的长度差分布 **全为 0**（空 = 无任何额外特殊 token）；尾部必须以 `<|im_start|>assistant\n` 结束且 `Rating:` 位于末尾，破损 **0** 例。

### 1.3 截断点审计：推理链路上没有任何截断

| 阶段 | 代码 | 是否截断 |
|---|---|---|
| 模板渲染 | `render_pab`（`style=pab` 分支直接返回，不走 `render_fitted` 的 env 预算） | 否 |
| 文本化 | `apply_chat_template(tokenize=False)` | 否 |
| 再分词 | `tok(text, add_special_tokens=False)`，未传 `truncation` | 否 |
| 生成 | `generate(max_new_tokens=6)`，未设 `max_length` | 否（只限输出长度） |

实证：最长样本 `1047` token 的 `decode→再编码` 与原始 id **逐元素相等**，且末尾 3 个 token 就是 assistant 提示，`Rating:` 提示完整保留。`max_position_embeddings=32768`，位置编码无压力。

### 1.4 需要如实记录的一点：6 条超出训练预算 1024

| tokens | 内容 token | 场景 | 配对 | tier | 角色 | 工具 |
|---|---|---|---|---|---|---|
| 1047 | 1018 | 91ae3a54fd | travel/user_task_4 | strict_test | negative | create_calendar_event |
| 1036 | 1007 | 91ae3a54fd | travel/user_task_10 | strict_test | positive | create_calendar_event |
| 1036 | 1007 | 91ae3a54fd | travel/user_task_4 | strict_test | positive | create_calendar_event |
| 1036 | 1007 | 91ae3a54fd | travel/user_task_8 | unseen | positive | create_calendar_event |
| 1036 | 1007 | 91ae3a54fd | travel/user_task_7 | contains_train | positive | create_calendar_event |
| 1034 | 1005 | 91ae3a54fd | travel/user_task_8 | unseen | negative | create_calendar_event |

- 全部来自 1 个场景 `91ae3a54fd`（travel，history 1448 字符、action 337 字符），不是普遍现象。
- 其中 strict_test 主指标池内 3 条，落在 1 个场景、2 个配对。
- 性质：这**不是截断**（没有任何 token 被丢弃），而是长度外推——比训练集最长样本（985 token）多出最多 62 个 token。1.5B/3B 均为 RoPE、上下文 32768，位置外推风险很低。
- 处置：**不修改 P2-v2、不截断**（截断会切掉 `Rating:` 与动作文本本身），评测按原样输入；同时在结果中给出“剔除该场景”的描述性敏感性对照。

### 1.5 训练侧对照（PAB-RD，同一条 chain）

| split | n | p50 | p95 | max |
|---|---|---|---|---|
| test | 335 | 652 | 866 | 957 |
| train | 764 | 618 | 842 | 985 |
| val | 120 | 821 | 913 | 958 |

训练集最长 985，从未触及 1024，因此训练过程也没有发生过任何截断；P2-v2 与训练分布的长度区间基本重合。

## 检查 2：No-task 臂同组正负例输入一致性

| 项目 | 结果 |
|---|---|
| 正负例 `action_id` 与 `evidence_id` 相同 | 316/316 |
| 正负例 `history` 与 `current_action` 逐字符相同 | 316/316 |
| No-task 渲染文本**逐字节相同** | 316/316 |
| No-task **完整模板**后 token id 序列相同 | 316/316 |
| Task 臂仅 task 槽位不同（哨兵替换后相同） | 316/316 |
| Task 臂整段文本相同（应为 0） | 0/316 |
| No-task 中 `(not provided)` 恰好出现 1 次 | 316/316 |
| No-task 文本包含原 instruction 原文（泄漏，应为 0） | 0/316 |

正负例字段差异计数：`{'instruction': 316, 'label': 316, 'label_reason': 316, 'pair_role': 316, 'task_cls': 316, 'task_id': 316}`

即：正负例只差 task 相关字段（instruction / task_id / task_cls / label / label_reason / pair_role），动作与证据完全相同。

异常样本：无

## 结论

1. **检查 1 通过（无截断）**：推理链路上没有任何截断点，模板特殊 token 既不重复也不丢失，尾部评分提示完整。需记录的唯一事实是完整模板固定多 29 token 的 system 段，导致 6 条（单场景）超过训练预算 1024，属长度外推而非截断。
2. **检查 2 通过（完全一致）**：No-task 臂 316/316 对的输入文本与 token id 完全相同，task 臂仅 task 槽位不同。因此 No-task 的 PRA 在理论上应恰为 0.500（同输入→同输出→全 tie）；若实测偏离，只可能来自批内 padding 引起的浮点非确定性，而**不会**是输入差异——出现偏离时先按配对检查正负例预测是否同标签。
3. P2-v2 数据与指标口径保持冻结，不扩数据、不改样本；后续评测只读取该文件。

