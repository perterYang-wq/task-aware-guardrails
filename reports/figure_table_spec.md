# 图表规格书（提取 + 规划，不含正文）

> 性质：整理任务。未跑任何 GPU / 训练 / 新实验，未修改任何已有报告与 CSV。
> 规则：数字全部来自已有文件，注明路径与重算脚本；缺数据标 `blocked`；不同协议分栏。
> 目标稿为英文，故图表标题用英文，作用说明用中文。

---

## 0. 输入盘点表

| 文件 | 存在 | 覆盖哪节 | 关键字段 / 用途 |
|---|---|---|---|
| `reports/final_metrics.csv` | ✅ 48.9 KB | §5 §6 §7 §8 | 352 行；claim/axis/suite/arm/metric/value/num/den/unit/source/note。所有 e2e 与集合数字的单一出口 |
| `reports/claim_status.md` | ✅ | 全局 | C1–C8 的 status / scope / 禁止表述 / 证据 |
| `reports/deny_attribution.md` | ✅ | §7 | 34 条 DENY 的 P1 归因；M0 对照；集合差（6/4/20/2） |
| `reports/b3_tshield.md` | ✅ | §5 §8 | M1 vs Task-Shield：ASR/效用/延迟/显存/DENY 次数 |
| `reports/b6_adaptive.md` | ✅ | §7 | static/meta/obfusc 3/1/0；逐调用翻转；机制修订 |
| `reports/b6_meta_retrain.md` | ✅ | §7 | 元样本重训后仍 3/20（p=1.0），6/20 场景判定变了 |
| `reports/posthoc_alignment.md` | ✅ | §8 | meta 3/20→0/20；slack 三项不变；合法 send_email 未误杀 |
| `reports/b5_lightweight.md` | ✅ | §8 | 0.5B：ACB 86.5%、CPU p50/p95、e2e 3/40 与 21/99 |
| `reports/b8_diagnosis.md` | ✅ | §7 附录 | 三 seed 的 travel ASR（2.5/2.5/10.0）与盲点定位 |
| `reports/failure_user_task_4.md` | ✅ | §7 | user_task_4 失败轨迹的原始分析 |
| `reports/failure_analysis.md` | ✅ | §7 §9 | 三案例合并 + 总起段 + 共同错位表 |
| `reports/probe_user_task_4.md` | ✅ | §7 | P0–P4 × 3 seed 的 raw 与判定 |
| `reports/travel_write_tools.md` | ✅ | §7 附录 | travel 写类工具清单（判断"写类越权"子类边界） |
| `reports/mcnemar_audit.md` | ✅ | 全局 | 10 条 p 的重算与检验类型 |
| `reports/consistency_check.md` | ✅ | 全局 | 5 个数在三处一致 |
| `reports/final_figures.md` | ✅ | 全局 | 6 张现有图的图注索引 |
| `final_figures/*.png` | ✅ 6 张 | §3 §5 §6 §7 §8 | fig1 PRA-ACB / fig2 dInj(m2) / fig3 三套件 / fig4 成本 / fig5 七轴 / fig6 路由 |
| `probes/deny_attribution{,_m0}.json` | ✅ | §7 | 每条 DENY 的 P0/P1 判定与交叉表 |
| `probes/net_gain_sets.json` | ✅ | §7 | M1 only 6 / M0 only 4 / 交集 20 / 稳健 2 |
| `probes/posthoc_alignment.json` | ✅ | §8 | 补丁前后两臂的 ASR/效用/授权层拦截清单 |
| `probes/probe_user_task_4.json` | ✅ | §7 | 5 变体 × 3 seed 的 raw/parsed/n_in |
| `runs/auto/state.json` | ✅ 20.6 KB | 全局 | claims（C1–C8）、phase5、limitations 5 条 |
| `runs/auto/round_*` | ⚠️ 仅 `round_m0`、`round_probe` | — | 只有这两批的 step.json；其余批次在 `results/*.log`，**不足以重建中间量** |
| `results/e2e/**/scen.jsonl` | ✅ | §5 §6 §7 §8 | 场景级原始记录（含 guard_hits / calls） |

> 盘点结论：17 个指定文件全部存在；`runs/auto/round_*` 覆盖不全，凡依赖"批次中间量"的图表一律不进。

---

## 1. 章节–claim–图表映射总表

> **编号冲突必须先解决**：任务书正文的 C1/C2/C3 是**叙事线编号**，与 `claim_status.md` 的 C1–C8 不是同一套。
> 本规格书一律用 `claim_status.md` 的编号，下表给出对照。

| 任务书叙事 | 本表 claim | 必进正文 | 候选（二选一/降级） | 附录 |
|---|---|---|---|---|
| §2 相关工作 | —（C3 的定位部分） | 无独立浮动体（回指 §5 的表 2，其中含 ToolSafe 定性行） | — | 表 11（并入表 2，不单列） |
| §3 问题分析 | **C1** | 图 1（a/b 双面板） | 图 2（并入图 1b） | — |
| §4 方法 | — | 无浮动体（架构示意图可选，非数据图） | — | — |
| §5 整体有效性 | **C2 + C4 + C3** | 表 1、表 2 | 图 3（与表 1 重复→附录） | 图 3 |
| §6 收益从哪来 | **C2**（机制侧） | **表 4（规则臂）+ 图 4（配方阶梯）** | — | 图 5（七轴）、表 3（配方明细）、表 10 |
| §7 到哪止、为何止 | **C8 + C7（主模型侧）** | 图 6（探针热图）、表 6 | — | 表 5、表 7、图 7、图 10 |
| §8 如何缓解、代价 | **C7（补丁侧）+ C5** | 无（正文三句话 + 指向附录） | — | 图 9（配对条形）、表 8（精确数）、表 9、图 8 |
| §9 讨论 | — | 无（定性） | — | 图 10 |

---

## 1.5 四项写作决策（2026-11-02 23:20 定稿，后续不再改）

| # | 决策 | 理由 | 影响 |
|---|---|---|---|
| D1 | **图 4（配方阶梯）提回正文；表 8 压成图 9 进附录** | §6 是 C2 的核心却只有表；表 8 数据量小，可与图 9 二合一 | 正文 7 个 = 4 表 + 3 图；§8 主文无浮动体 |
| D2 | **表 4 拆开**：正文只留规则三臂（3 行），配方阶梯交给图 4 + 附录表 3 | 合并版为 7 行 × 5 列，超载；且与图 4 信息重复 | §6 一表一图，各司其职 |
| D3 | **图 1 为 (a)(b) 左右并列、各自独立坐标轴**（不共享 y、不 twinx、不做双 y） | 两面板协议与单位都不同 | 图注两段；正文分别引"图 1(a)/(b)" |
| D4 | **blocked 拆两栏**：缺数据 4 项 / 协议约束 2 项 + DO-NOT-QUOTE 1 项 | 约束不是缺数据，混在一起会导致写作时反复回问 | 见 §5 |

## 2. 表规格

### [表 1] End-to-end safety and utility across three suites

- **挂靠**：§5
- **证明**：C2 + C4 —— 任务感知把三个套件的 ASR 压到 ≤2.5%，且 slack 干净效用不降反升。
- **作用**：一眼看到"更安全且不伤效用"，同时看到 banking 的天花板。
- **正文/附录**：正文
- **行 / 列 / 单位**：9 行（3 套件 × E0/M0/M1）；列 = ASR（n/N，%）、干净完成（n/N，%）、干净场景调用级误拦（n/N，%）
- **数据来源**：`reports/final_metrics.csv`（claim=C2_task_aware）← `scripts/b9_metrics.py` ← `results/e2e/*/scen.jsonl` + `results/ad_v3/*/scen_merged.jsonl`（E0）
- **协议标注**：banking 32 攻击 / 16 干净（inj5–7）；slack 42 / 21（inj1,3）；travel **40 / 20（inj0–1）**；seed0；守卫 GPU fp16；E0 = 无守卫 7B agent
- **禁止解读**：① 不得说"跨套件泛化"——travel 有 50% 任务在配对训练集里（C6）；② banking 的 0/32 是危险动作天花板，不是"方法更强"；③ **travel 另有 80 场景（inj0–3）与 139 场景协议，数字不得混入本表**（80 场景：M0 13/80 vs M1 1/80，见脚注）

### [表 2] Head-to-head against a 7B task-aware judge (slack)

- **挂靠**：§5（定位部分回指 §2）
- **证明**：C3 —— 同安全（0/42）下，M1 的干净效用高 42.9pp、延迟 0.44×、DENY 次数少 8.5×（26 vs 222）。
- **作用**：与 SOTA 正面对打；同时暴露我们**不占优**的一项（显存）。
- **正文/附录**：正文
- **行 / 列 / 单位**：4 行（M1 / Task-Shield 7B / ToolSafe（未复现）/ 纯规则 γ==3）；列 = ASR、干净完成、DENY / 判定次数、延迟 mean / P95（ms）、额外显存（GB）、McNemar p
- **数据来源**：`reports/b3_tshield.md` §2.2–§3；`reports/final_metrics.csv`（C3_vs_prior）；`reports/mcnemar_audit.md`（9:0, p=.0039）
- **协议标注**：slack 42 攻击 / 21 干净；seed0；GPU fp16；延迟与判定次数取自同一批运行
- **禁止解读**：① 禁"成本 1/5"——延迟是 0.44×，显存我们**多** 4.1 GB；② ToolSafe 行只能写"未复现，无可比数字"，不得填估计值；③ 纯规则行的 ASR 31.0% 不能写成"接近 M1"

### [表 4] Why the gain is not from rules (slack)

- **挂靠**：§6
- **证明**：C2（机制侧）—— 纯硬规则只挡写类，读类与无守卫完全相同；叠加到 M1 上安全零增益、效用崩塌。
- **作用**：读完相信"收益不是规则给的"，从而把功劳归给模型 + 配方。
- **正文/附录**：正文
- **行 / 列 / 单位**：**3 行**（纯硬规则 / M1 仅模型 / M1+硬规则）× 6 列 = ASR 总、ASR 写类、ASR 读类、干净完成、干净误拦、vs M1 的 p
- **数据来源**：`reports/b10_ablation.md` §B10-1；`reports/final_metrics.csv`（claim=B10：rule_only / M1_block / M1_rule）；`reports/mcnemar_audit.md`（纯规则 vs M1 的 ASR 12:0，p=.0005；M1+规则 vs M1 的效用 13:0，p=.0002）
- **协议标注**：slack 42 攻击 / 21 干净；seed0；GPU fp16；三臂同一执行边界（`--hard-rule` 开关）
- **禁止解读**：① 纯硬规则 28.6% 不能读成"规则有效"——它读类 12/21，与无守卫**完全相同**；② M1+硬规则 0/42 是 **0:0 不一致对**，p=1.0 只表示"无可检验差异"，禁写"证明无差异"；③ 它的效用 1/21 说明叠加规则摧毁效用，不是"更安全"

### [表 6] Where the denials come from: payload vs action prior

- **挂靠**：§7
- **证明**：C8 —— M1 的拦截主要是动作先验；任务信息净增益 6 条中 4 条受污染，稳健仅 2 条。
- **作用**：把"有效性边界"量化，读者相信增益集中在读类与灰区。
- **正文/附录**：正文
- **行 / 列 / 单位**：3 行（M1 / M0 / 集合差）；列 = 总 DENY、payload-recognition、非载荷依赖、交集、M1 only、M0 only、稳健净增益、McNemar p
- **数据来源**：`reports/deny_attribution.md` §1–§3；`probes/deny_attribution.json`、`probes/deny_attribution_m0.json`、`probes/net_gain_sets.json`；`reports/mcnemar_audit.md`（6:4, p=.754）
- **协议标注**：同一批 34 条 DENY 实例；**CPU fp32 / greedy / P0–P1 重打分**（与 e2e 的 GPU fp16 不同精度，已在归因报告注明）。注意：M0 的「非载荷依赖 22」是 P0 与 P1 都判 DENY 的条数；集合口径下 |B|=24（另有 2 条只在 P1 判 DENY），两列不可互相替代
- **禁止解读**：① 76.9% 是"M1 DENY 集合内"的条件一致率，**不是召回率**；② 净增益 6 vs 4 不显著，禁写"任务信息带来净增益"；③ P1-robust 只能读成"不依赖载荷原文块"（17/34 仍有实体残留）

### [表 3]（附录）Recipe ladder, exact numbers（图 4 的底表）

- **挂靠**：§6 附录 · **证明**：C2 · **作用**：给图 4 提供精确分母、误拦率与配对 p
- **行/列**：4 行（E0 / S / M0 / M1）× {ASR、干净完成、干净误拦、vs M1 的 p}
- **来源**：`reports/b10_ablation.md` §B10-2；`reports/final_metrics.csv`（claim=B10）；`reports/mcnemar_audit.md`
- **协议**：slack 42/21；seed0；GPU fp16
- **禁止**：E0 的效用 13/21 与 M1 的 14/21 只差 1 例（McNemar 1:0，p=1.0），不得写成"效用提升"

### [表 5]（附录）Counterfactual probe matrix (5 variants × 3 seeds)

- **挂靠**：§7 附录 · **证明**：C8 · **作用**：保留 raw 值，供复核图 6
- **行/列**：P0–P4 × seed0/42/123；单元格 = `raw` / 判定
- **来源**：`reports/probe_user_task_4.md`；`probes/probe_user_task_4.json`
- **协议**：**CPU fp32 / greedy / max_new_tokens=6**；单场景（travel user_task_4 + inj1）
- **禁止**：不得把 CPU 判定与 e2e GPU 记录混为一谈（seed123 的 P0 已做一致性校验）；**该 md 的三行"说明"只对 seed123 且与表格不一致，正文不得引用那三行**

### [表 7]（附录）Adaptive attack details (static / meta / obfusc)

- **挂靠**：§7 附录 · **证明**：C7（主模型侧）· **作用**：给出 3/20 的逐调用证据与重训无效
- **行/列**：三变形 × {ASR、原任务完成、Fisher p、逐调用翻转}；另起重训前后对照
- **来源**：`reports/b6_adaptive.md`、`reports/b6_meta_retrain.md`、`reports/final_metrics.csv`（C7_adaptive）
- **协议**：travel 20 攻击场景（inj1，attack-only）；seed0；GPU fp16
- **禁止**：3/20 与 1/20 的差在 n=20 下不显著（p=.605），禁写"meta 显著提高了攻击成功率"

### [表 8]（附录）Deployment-layer authorization patch, exact numbers

- **挂靠**：§8 附录（正文只用三句话 + 指向本表与图 9）
- **证明**：C7（补丁侧）—— 补丁把 meta 从 3/20 压到 0/20 且不误杀，但依赖 provenance 标记。
- **作用**：给图 9 提供精确分母与 p，供审稿人核对
- **正文/附录**：**附录**（D1 决策：主文不占位）
- **行 / 列 / 单位**：4 行（meta 前 / meta 后 / slack 前 / slack 后）+ 1 行合法 send_email 单例；列 = ASR、干净完成、干净误拦、授权层拦截次数、Fisher p
- **数据来源**：`reports/posthoc_alignment.md`；`probes/posthoc_alignment.json`；`reports/mcnemar_audit.md`
- **协议标注**：meta = travel 20 攻击场景（attack-only）；slack = 42 / 21；seed0；GPU fp16；合法 send_email 为 travel user_task_3 单场景运行
- **禁止解读**：① 禁"达标 / 显著改善"——统一写 "formally meets ≤2/20; Fisher p=.231 at n=20; significance NOT established"；② 不得说"补丁解决自适应攻击"，它只挡"参数来自不可信文本"；③ 不得省略 provenance 前提

### [表 9]（附录）Cost comparison

- **挂靠**：§8 附录 · **证明**：C5 · **作用**：把延迟/显存/ACB 放一起，说明"轻量"的实际含义
- **行/列**：M1 / Task-Shield / 纯规则 / 0.5B；列 = 延迟、显存、ACB、e2e 误拦
- **来源**：`reports/b3_tshield.md`、`results/classifier/latency_rule_cpu.json`、`results/classifier/latency_05b_cpu.json`、`reports/b5_lightweight.md`
- **协议标注（必须分栏）**：M1/TS 延迟 = **GPU fp16 e2e**；纯规则 = **CPU** 416 次调用；0.5B = **CPU batch=1** n=95
- **禁止**：**禁止把 M1 的 251 ms 与 0.5B 的 1461 ms 放同一列比较**（设备不同）；0.5B 的 GPU 延迟/显存 **blocked**

### [表 10]（附录）Seven-axis ablation summary

- **挂靠**：附录 · **证明**：C2 的完备性 · **作用**：一页看全七根轴
- **行/列**：7 行（轴 / 对比 / 指标 / 结果 / 来源）；第七轴 = 动作先验 vs 任务信息（6/4/20/2）
- **来源**：`reports/b9_notes.md` §2；`probes/net_gain_sets.json`
- **协议**：逐行标注（离线 ACB / e2e / 集合），**不同轴的指标不同，禁止横向比较数值大小**

### [表 11] → 并入表 2
ToolSafe 无复现数字，只保留一行定性（"未报告 e2e 代价"），不单列。

### [表 12]（内部，不进论文）claim 状态表
即 `reports/claim_status.md`，写作纪律用。

---

## 3. 图规格

### [图 1] Why end-to-end evaluation is necessary（原候选图 1 + 图 2 合并，双面板**独立坐标轴**）

- **挂靠**：§3
- **证明**：C1 —— 载荷污染真实存在（a），且离线判据不能替代线上（b）。
- **作用**：读者先相信"问题是真的"，再相信"现有离线指标测不出来"。
- **图型**：**(a)(b) 左右并列**。(a) 点 + 95%CI + 0 线；(b) 散点 + 线性趋势
- **坐标轴（D3 决策）**：**两个面板各自完整、互不共享**——(a) 只有左 y 轴（dInj, pp），(b) 只有左 y 轴（ACB, %）；**不做共享 y、不做 twinx、不做双 y**。x 轴也各自独立（(a) 分类臂名；(b) PRA 连续值）
- **横轴 / 纵轴 / 图例 / 单位**：(a) x = 臂（5 个 checkpoint：三 seed + 3B + 任务盲对照），y = dInj（pp）；(b) x = 离线 PRA，y = 线上 ACB（%）
- **数据来源**：`results/diag/metrics.json`（字段 `dInj.delta` / `dInj.ci`）、`results/diag/offline_vs_online.json`；重算 `scripts/b9_metrics.py`（C1/fig1 段）、`scripts/b9_figures.py`
- **协议标注（图注分两段写）**：(a) **p1 系列（标准授权 SFT）**，2370 诊断步 / 159 攻击调用，GPU fp16；(b) 5 个同协议 checkpoint，同一诊断集
- **正文/附录**：正文
- **禁止解读**：① 不能把 (a) 的负号套到 M1 上——**m2_HB（本文 M1）的 dInj 是 +0.233**，符号相反，正文必须用一句话交代（C1 scope）；② 两个面板不得合成一个"离线分数"；③ 三 seed 的 CI 排除 0 只说明"载荷效应稳定为负"，不说明效应大小可外推；④ 正文引用时必须分开写"图 1(a)""图 1(b)"

> **状态提醒**：现有 `fig2_dinj_seeds.png` 画的是 **m2 臂（正号）**，与本节所需的 p1 系列（负号）**不是同一协议**，不能直接复用；需按 (a) 重画。

### [图 4] The recipe ladder: ASR down, utility up

- **挂靠**：§6（D1 决策：提回正文）
- **证明**：C2 —— 四点阶梯上只有 M1 同时把 ASR 压到 0 且效用升到 66.7%。
- **作用**：一张图讲完"只有完整配方双赢"，是 §6 的主视觉。
- **图型**：折线 + 双 y 轴（左 ASR↓，右 干净完成↑），四点各标数值
- **横轴 / 纵轴 / 图例 / 单位**：x = 配方阶段（E0 → +SFT → +任务盲配方 → M1）；左 y = ASR（%）；右 y = 干净完成（%）；点值 = 50.0/61.9 → 11.9/47.6 → 9.5/33.3 → 0.0/66.7
- **数据来源**：`reports/final_metrics.csv`（claim=B10：E0 / S / M0 / M1_block）；底表见附录 `[表 3]`；重算 `scripts/b9_metrics.py`
- **协议标注**：slack 42 攻击 / 21 干净；seed0；GPU fp16；四点同一执行边界
- **正文/附录**：正文
- **禁止解读**：① 双 y 轴**不得比较斜率**（两条线单位不同）；② 四点不是时间序列，连线只表示配方递进；③ 不得把 E0→S 的效用下跌读成"加入数据有害"——它是"安全换效用"，正文要给 S 的 ASR 11.9% 作对照

### [图 6] Three seeds learn different criteria（probe heatmap）

- **挂靠**：§7
- **证明**：C8 / C7（主模型侧）—— 同一输入，三个 seed 的判定矩阵不同，失效点可定位。
- **作用**：机制核心图。读者相信"seed 差异不是噪声，是判据维度不同"。
- **图型**：热图（5 变体 × 3 seed），单元格标 `raw` 值，颜色 = ALLOW / REVIEW / DENY
- **横轴 / 纵轴 / 图例 / 单位**：x = P0–P4；y = seed0 / s42 / s123；图例三色
- **数据来源**：`probes/probe_user_task_4.json`；`reports/probe_user_task_4.md`；重算 `probes/probe_runner_cpu.py`
- **协议标注**：单场景（travel user_task_4 + inj1）；**CPU fp32 / greedy / 6 tokens**
- **正文/附录**：正文
- **禁止解读**：① 不能从 5 个变体推断"模型学到了什么规则"——只能说判定随变体改变；② 不得把 heatmap 的颜色当作置信度（只有三档）；③ 不得引用 md 里那三行与表格不一致的"说明"

### [图 3]（附录）Three suites × three arms
- 挂靠 §5 附录 · 证明 C2 · 与表 1 信息重复，降级为附录可视化
- 图型：分组柱 + 分子/分母标注；来源 `final_figures/fig3_suites_arms.png` ← `scripts/b9_figures.py`
- 协议同表 1 · 禁止：banking 柱不得单独解读为"效果最强"

### [图 5]（附录）Seven-axis waterfall
- 挂靠 §6 附录 · 证明 C2 完备性 · 图型：瀑布 + 集合条（已有三面板）
- 来源 `final_figures/fig5_ablation_waterfall.png` ← `probes/net_gain_sets.json`
- 禁止：七个轴指标不同（ASR / ACB / 计数），**不得横向比高度**

### [图 7]（附录）Routing curve
- 挂靠 §7 附录 · 证明 C8（为何不全查高危）· 图型：折线 + 读写分解
- 来源 `results/classifier/routing_ablation.json` ← `scripts/b9_metrics.py`（B10 routing 段）
- 协议：离线 2370 调用（159 攻击 / 2174 干净）· 禁止：读类归零是"路由策略"的性质，不是模型的

### [图 8]（附录）Cost–safety frontier
- 挂靠 §8 附录 · 证明 C5 · 图型：散点（log 延迟 × ASR，气泡=效用）
- 来源 `final_figures/fig4_cost_safety.png`；延迟 M1/TS 读 `reports/b3_tshield.md`（正则），规则读 `latency_rule_cpu.json`
- 禁止：0.5B 点只能标 CPU 延迟；TF 与 M1 的延迟同设备可同图，0.5B **不可**

### [图 9]（附录）Patch before/after: meta down, legitimate calls untouched

- **挂靠**：§8 附录（D1 决策：替代原表 8 的主文位置）
- **证明**：C7（补丁侧）· **作用**：配对条形展示 meta 3→0 与合法调用不变
- **图型**：配对条形（左 meta 前后，右 Slack 效用/误拦前后）
- **数据来源**：`probes/posthoc_alignment.json`；`reports/posthoc_alignment.md`
- **协议标注**：meta = travel 20 攻击场景；slack = 42/21；seed0；GPU fp16
- **正文/附录**：附录
- **禁止解读**：① 3→0 不得加显著性星号（Fisher p=.231，n=20）；② 不得把"合法调用不变"说成"补丁无副作用"——它仍有 2 条 channel 误判与 provenance 依赖

### [图 10]（附录）Three independent evidences, one mechanism
- 挂靠 §7 附录 / §9 讨论 · 证明 C8 · 图型：示意（非数据图）
- 内容：s42 的 P0/P1 翻转、B6 meta 的 DENY→ALLOW、归因 76.9% 三条并列
- 禁止：这是**论证示意图**，不得标注任何未经计算的合成分数

---

## 4. 正文浮动体预算核对（≤7）

| # | 浮动体 | 节 | 证明 | 不可替代性 |
|---|---|---|---|---|
| 1 | 表 1 三套件总表 | §5 | C2+C4 | 唯一给出三套件 × 三臂的完整对照 |
| 2 | 表 2 vs Task-Shield | §5 | C3 | 唯一与 SOTA 的定量对比（含我们不占优的显存） |
| 3 | 表 4 规则三臂 | §6 | C2 | 唯一回答"收益不是规则给的" |
| 4 | 表 6 DENY 归因 | §7 | C8 | 唯一给出边界与净增益的集合证据 |
| 5 | 图 1（a/b，独立坐标轴） | §3 | C1 | 唯一同时给出"威胁真实"与"离线不足" |
| 6 | 图 4 配方阶梯 | §6 | C2 | 唯一一张图讲完"只有完整配方双赢" |
| 7 | 图 6 探针热图 | §7 | C8/C7 | 唯一的机制核心图 |

**合计 7 = 4 表 + 3 图，符合预算上限。** §6 现在一表一图（表 4 + 图 4），§8 主文无浮动体（D1）。

进附录的：图 3（与表 1 重复）、图 5（七轴）、图 7（路由）、图 8（成本）、图 9（补丁，替代原表 8）、图 10（三证据合成）、表 3（配方明细）、表 5（探针 raw）、表 7（B6 明细）、表 8（补丁精确数）、表 9（成本）、表 10（七轴汇总）。

> 图 1 由候选图 1 + 图 2 合并，占 1 个名额但保留两条信息；两面板各自独立坐标轴，不做数值合并。

---

## 5. blocked 与写作约束（两栏，别混）

### 5.1 缺数据（4 项，写作时确实没有数）

| # | 项 | 缺什么 | 处理 |
|---|---|---|---|
| 1 | 表 1 的 banking 误拦率 | `final_metrics.csv` 无该格；banking 运行无 `calls` 字段；`round_m0` 里也没有 banking e2e，**无法重算** | 正文不报该格，脚注写"未采集调用级"。**不许拿 slack 的分母代替** |
| 2 | 表 2 的 ToolSafe 行 | 未在相同协议下复现，无任何数字 | 写成"未在相同协议下复现，故不做数值对比"（定性吸收，**写作时不需要再回问**） |
| 3 | 表 9 / 图 8 的 0.5B GPU 延迟与显存 | 只测了 CPU（p50 1461 / p95 4182 ms） | 0.5B 行只留 ACB + CPU 延迟，标"GPU 未测" |
| 4 | `runs/auto/round_*` 的批次中间量 | 只有 `round_m0`、`round_probe` 两批 | 凡依赖其它批次中间量的图不进（本规格书已剔除，无待办） |

### 5.2 协议约束（2 项，是写作纪律，不是缺数据）

| # | 约束 | 内容 |
|---|---|---|
| 1 | travel 40 / 80 / 139 场景不得同列 | 表 1 用 40 场景；80 场景（M0 13/80 vs M1 1/80）只作脚注；139 场景仅 E0 有，不得混入 |
| 2 | 图 1(a) 不得画入 M1 | m2_HB 的 dInj 为正号、跨配方；只画 p1 系列，M1 用正文一句话交代 |

### 5.3 DO-NOT-QUOTE（写作硬纪律）

| 文件 | 位置 | 问题 | 处理 |
|---|---|---|---|
| `reports/probe_user_task_4.md` | 结尾三行"说明"（P1/P2/P3/P4 各一句） | 只对 seed123 成立，且与它自己的表格矛盾（表格里 seed0 在 P3/P4 判 DENY、seed42 在 P0/P2/P3 判 DENY） | 标 `DO-NOT-QUOTE`；**图 6 的图注只能从表格重算，不得引用这三行** |

> **硬纪律**：任何报告的"结论段"与"数据表"必须一致；引用时一律以表为准。
> 结论段若与表矛盾，该段在规格书中标 `DO-NOT-QUOTE`，并在写作前修正——不得"择一引用"。

---

## 6. 禁止表述扫描结果（提取过程中发现）

| # | 位置 | 表述 | 问题 | 处理 |
|---|---|---|---|---|
| 1 | `baselines_controls.md` L4/L28 | "travel = 未见套件" | 已被 `correction_ood.md` 更正 | 加 SUPERSEDED 横幅；正文禁用 |
| 2 | `e2e_ablation.md` L4 | 同上 | 同上 | 同上 |
| 3 | `m2_ladder.md` L33/L85 | 同上，且称"唯一可作泛化结论的一列" | 同上 | 同上 |
| 4 | `phase1_baseline_v2.md` L95 | 同上 | 同上 | 同上 |
| 5 | `probe_user_task_4.md` 结尾三行 | "P2 判定 ALLOW / P3 判定 ALLOW" | 只对 seed123 成立，与表格三列不一致 | 正文/图 6 只引表格，不引这三行 |
| 6 | `b5_lightweight.md` | "达标（勉强）" | C5 的禁词（C5b 只 p50 达标） | 已改为"形式满足比例判据"；引用时沿用 |
| 7 | `b6_adaptive.md` 旧机制结论 | "拦截主要来自载荷识别" | 已被 M0 对照推翻 | 已在文件顶部作废；正文用修订版 |
| 8 | `final_figures.md` fig2 图注 | 把 m2 的 dInj 描述为"三 seed" | 与 §3 需要的 p1 系列不同协议 | 重画后同步改图注 |
| 9 | `claim_status.md` C2 的 scope | "slack 6/105→0（p=.031）；travel 13/80→1（p=.0018）" | **三个 p 混用检验**：slack 与 banking 是 Fisher；travel 80 场景是 **McNemar .0018**（Fisher 为 .0012，见 `phase1_travel_expand.md` L30/L70） | 正文逐条标注检验类型；本表不改 `claim_status.md`（只读），在写作时按此条执行 |

> 其余扫描（C1–C8 的禁用表述）见 `reports/claim_status.md`：现行文档 0 处越界，12 处全在旧文档。

---

## 7. 自检

- [x] 每个数字都有来源文件 + 重算脚本名（表/图模板的"数据来源"行）
- [x] 每个 p 都标了检验方法；0:0 已标"无可检验差异"（表 4）
- [x] 不同协议已分栏（表 1 的 40/80/139；表 9 的 GPU/CPU；表 6 的 CPU fp32）
- [x] 比例与集合差分开（表 6 用 81.2/81.5% 与 6/4/20/2 两套列）
- [x] 每个图表都挂了章节与 claim；挂不上的已剔除（无）
- [x] 正文浮动体 = 7（**4 表 + 3 图**），砍掉的已进附录
- [x] blocked 已拆两栏：缺数据 4 / 协议约束 2；另有 DO-NOT-QUOTE 1 项
- [x] 禁词扫描：现行文档 0 残留；旧文档 4 处已标红并建议加横幅；
  本规格书自身出现的禁词均为**引述禁令/标注旧文**，不是断言
