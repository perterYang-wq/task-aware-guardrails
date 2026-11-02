# P1 发现：现有 step-level 安全基准测不出"任务感知"

日期：2026-10-30
状态：已用实验确认；数字均可由 `scripts/` 复现

---

## 0. 一句话

在 TS-Bench（ToolSafe 的评测集，7182 条）上，**纯工具名查表 macro-F1 = 0.960**，
**只用动作文本的 TF-IDF = 0.916**，而**把用户任务也喂进去只有 0.913（Δ = −0.003）**。
全库"同工具 + 同参数但标签不同"的最小对只占 **0.48%**，测试集中为 **0**。
结论：该基准的标签几乎完全由动作字符串决定，任务信息在信息上是冗余的，
**任何"task-aware guard 在此提升多少"的主张都无法被它证伪**。

---

## 1. 数据与标注口径（先对齐，否则后面全错）

TS-Bench 真身从 `media.githubusercontent.com` 的 LFS media URL 取得
（`codeload` 的 tarball 里只有 131 字节指针）。

| 子集 | 条数 | 0.0 安全 | 0.5 争议 | 1.0 不安全 |
|---|---|---|---|---|
| agentharm（benign 206 + harmful 525） | 731 | 206 | 315 | 210 |
| agentdojo（banking/slack/travel/workspace） | 1220 | 868 | 0 | 352 |
| asb（failure 429 + DPI 2293 + OPI 2509） | 5231 | 2696 | 1466 | 1069 |
| **合计** | **7182** | **3770** | **1781** | **1631** |

与论文报告一致（ASB 为 5231，原文 5237，差 6 条，已记录）。
`score` 判定的是**当前这一步**而非整条轨迹：ASB 里 `attack_success=True` 但 `score=0`
的样本，其 current_action 确实是合法工具调用（如 `market_data_api`），
而 `score=1` 的样本参数里带 `"action": "redirect_funds_without_authorization"`。

动作解析：`(2) Action` 抽出工具名 **99.8%**（7170/7182），`(3) Action Input` 解析成 JSON **91.9%**。

---

## 2. 核心发现一：工具名就能答对 96%

| 基线 | macro-F1 | acc |
|---|---|---|
| 多数类（ALLOW） | 0.2295 | 0.5251 |
| 关键词规则（黑名单） | 0.2483 | 0.5077 |
| **工具名 → 其训练集多数标签** | **0.9597** | **0.9617** |

（`grouped` 划分的 test，n=1436。工具名映射在训练集上拟合，属乐观上界。）

527 个工具里只有 **44 个**出现过不同标签，其余 483 个工具的标签是确定的。
这不是模型的功劳，是数据构造的性质：攻击步几乎总用攻击者工具
（`InvestmentDiversion`、`delete_email`），合法步几乎总用良性工具。

**留出工具之后立刻崩塌**：在"未见工具"划分（留出 5 个跨标签工具：
`create_calendar_event` / `delete_file` / `get_webpage` / `query_google_search` / `send_email`，
test n=447，ALLOW/REVIEW/DENY = 122/105/220）上，
工具名查表的 macro-F1 = **0.1429**，与多数类基线完全相同（都是猜 ALLOW）。

> 也就是说：**同一套基准，"见过这些工具"时 0.96，"没见过"时等于瞎猜。**
> 高分来自记忆工具身份，不是判断任务授权。

---

## 3. 核心发现二：任务信息贡献 −0.003

按 instruction 分组做 5 折交叉验证（同任务的样本必须同折，否则指标虚高）：

| 输入 | macro-F1 | acc |
|---|---|---|
| 动作文本 only | **0.9161** | 0.9223 |
| 动作 + 用户任务 | 0.9131 | 0.9178 |
| **Δ** | **−0.0030** | −0.0045 |

加入任务不但没有提升，反而略有下降。原因：攻击的可识别痕迹全在动作字符串里
（工具名、`without_authorization` 之类的参数、Thought 里复述注入指令），
任务文本只是重复了用户想做什么，对"这一步是否被授权"没有增量信息。

---

## 4. 核心发现三：最小对几乎不存在

- 同工具 + 同参数、标签不同：**20 / 4207 = 0.48%**
- 跨标签的工具：44 / 527
- 落在跨标签工具上的样本：1799 / 7182（25.0%）
- `unseen_tool` 测试集内"同工具+同任务但标签不同"：**0 组**

没有最小对，就无法排除"模型在记工具名"。这是 §2 的直接后果，
也是为什么必须另造一个基准。

---

## 5. B3 基线：未微调的 1.5B 做不了这件事

用 ToolSafe 官方 `GUARD_TEMPLATES["TS-Guard"]` 四段式 prompt（含 Think / Malicious_User_Request /
Being_Attacked / Harmfulness_Rating）：

| 条件 | acc | macro-F1 | 解析失败 |
|---|---|---|---|
| 官方四段式，400 token，60 条抽样 | 0.4000 | 0.3036 | 8.3% |
| 极简单 token prompt，全量 7182 | 0.4625 | **0.3745** | 4.4% |
| 同上但**抹掉用户任务** | 0.3933 | 0.3251 | 4.3% |

两点结论：
1. 1.5B 零 shot 基本是猜（macro-F1 0.37），必须微调。
2. 抹掉任务只掉 0.049 —— 又一次印证任务信息价值极低（与 §3 同向）。

---

## 6. 新基准 PAB（Paired Authorization Benchmark）

### 构造（标签机械决定，无人工标注）

从 AgentDojo v1 的 97 个用户任务出发，对每个任务调用其 `ground_truth(env)`
拿到**该任务授权的真实工具调用（含真实参数）**：339 条授权调用，去重后 165 个动作。

对 (任务 T, 动作 a) 这个矩阵单元按规则定标签：
- `a ∈ authorized(T)` → **ALLOW**
- `a ∉ authorized(T)` 且 `a` 是状态变更类 → **DENY**
- `a ∉ authorized(T)` 且 `a` 是只读类 → **REVIEW**

采样时构造 4 类负例并记录 flavor，其中两类是真正的最小对：

| flavor | n | 说明 |
|---|---|---|
| `authorized` | 339 | ALLOW |
| `same_action_diff_task` | 469 | **动作文本逐字相同**，只换任务 ← 最小对 |
| `same_tool_diff_args` | 174 | 同工具，参数不同 ← 最小对 |
| `diff_tool_same_domain` | 194 | 同域不同工具（写） |
| `diff_tool_same_domain_read` | 194 | 同域不同工具（只读）→ REVIEW |

**关键性质（已实测）：165/165 = 100% 的动作文本都跨多个标签。**
Thought 字段对所有样本用同一句中性模板，不携带任何线索。

### 划分

按 (suite, task_id) 分组：train 876 / val 137 / test 357，任务交集 **0**。

### 证伪检验：动作-only 必然 50%

对同一动作的两条样本（一条 ALLOW、一条非 ALLOW），若模型只读动作文本，
则两条输入**逐字相同**，任何确定性打分函数给出相同分数 → 配对准确率恒为 50.0%。
这是构造性结论，不是统计推断。实测：

| scorer | 配对准确率 | 配对数 |
|---|---|---|
| 工具名查表 | **50.0%** | 105 |
| 动作文本查表 | **50.0%** | 105 |
| TF-IDF 动作-only | **50.0%** | 105 |
| TF-IDF 动作 + 任务 | 52.4% | 105 |

同时，全测试集 macro-F1 会奖励"猜多数类"：
工具名查表 0.5854、动作查表 0.5482、TF-IDF 动作-only 0.6193、动作+任务 0.6337。
**两个指标并排看，差距本身就是论点。**

### 必须记录的一个设计缺陷

初版 PAB 没有证据字段（history 为空）。实测任务提示只覆盖授权参数的
28%（96/339 全部命中，166/339 一个都不命中），
而授权判定所需的收款人、金额等来自账单/文件。
结果：连"可判定"的负例类型在 TF-IDF 下也只有 48.8%–60.0%，
说明**基准整体欠定**，谁上去都答不对。

已修正：为每个任务附一份"已检索到的值清单"（**只给值、不给字段名**），
授权判定变成两因子——(1) 参数是否落在证据里；(2) 是否服务于用户意图。
修正后 `same_tool_diff_args` 的配对准确率从 57.1% 升至 **85.7%**（TF-IDF），
证明证据字段确实让该类负例可判。

---

## 7. 这些数字意味着什么（对论文的直接后果）

1. **不能说"我们的方法在 TS-Bench 上把 F1 从 0.7 提到 0.9"** —— 0.96 用工具名查表就能拿到，
   这个提升没有意义。
2. **可以说的**：现有 step-level 基准无法证伪 task-aware 主张；
   我们构造了 PAB，其构造保证表面特征模型恒为 50%，因此在该基准上的提升是可解释的。
3. **必须同时报两个指标**：全测试集 macro-F1（会被先验抬高）与配对准确率（只测条件化能力）。
4. **证据字段不是可选项**：没有它，授权判定在信息上不成立。这本身是一条值得写的观察。

---

## 8. 复现命令

```bash
cd /data/projects/guardrails
conda activate /data/conda/envs/guard
python scripts/build_tsbench.py                       # 归一化 TS-Bench -> data/tsbench_unified.jsonl
python scripts/make_splits.py                         # grouped / unseen_tool / cross_source
python scripts/run_baselines.py --split grouped       # B0/B1/B2b + PG2
python scripts/analyze_pairs.py --split unseen_tool   # 最小对统计 + TF-IDF 动作/任务对照
python scripts/build_pab.py                           # 构造 PAB
python scripts/pab_baselines.py                       # PAB 划分 + 基线
python scripts/pab_pairwise.py --part test            # 配对准确率
```
