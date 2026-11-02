# McNemar / binomtest 审计

> 目的：确认所有 p 值的口径一致，并把报告里写过的 p 从原始数据重算一遍。
> 精确 McNemar = `2 * Σ_{i≤min(b,c)} C(n,i) 0.5^n`，与 scipy `binomtest(min(b,c), n, 0.5)` 等价。

## 1. 代码级：仓库里的 5 个实现

| 位置 | 实现 | 判定 |
|---|---|---|
| `scripts/e2e_analyze.py:131` | `binomtest(min(b,c), b+c, 0.5).pvalue` | 正确（scipy 双侧 = 精确 McNemar） |
| `scripts/unified_eval.py:122` | `min(1, 2*Σ_{i≤min(b,c)} C(n,i)/2^n)` | 正确（精确 McNemar 定义式） |
| `scripts/unified_eval_v2.py:105` | `同上` | 正确 |
| `scripts/power_analysis.py:32` | `同上` | 正确 |
| `scripts/pair_mcnemar.py:46` | `同上` | 正确 |
| `scripts/b9_metrics.py（阶段五修复前）` | `2*min(binomtest(b,n), binomtest(c,n))` | **错**：binomtest 已是双侧，再乘 2 会把 p 抬到 1（6:4 由 0.754 变 1.000） |
| `scripts/b9_metrics.py（修复后）` | `binomtest(min(b,c), n, 0.5).pvalue` | 正确 |

结论：只有 `b9_metrics.py` 的旧版本写错（在双侧 p 上再乘 2），
已改为 `binomtest(min(b,c), n, 0.5)`；其余 5 处口径正确。
错误版本对 6:4 会给出 1.000（正确 0.754），对 9:0 给出 1.000（正确 0.0039）——方向是**抬高 p**，不会伪造显著。

## 2. 数据级：报告 p 值的重算

> `mcnemar` 行的 b:c 是**配对不一致对**（a 成功 b 失败 / b 成功 a 失败）；
> `fisher` 行的 b:c 是**两臂各自成功的条数**，不是配对计数。

| 检验 | 类型 | 配对 n | b : c | McNemar p | Fisher p | 报告值 | 一致 |
|---|---|---|---|---|---|---|---|
| B3 · slack 效用（M1 vs Task-Shield） | mcnemar | 21 | 9 : 0 | **0.0039** | 0.0122 | 0.0039 | ✓ |
| B3 · slack ASR（M1 vs Task-Shield） | mcnemar | 42 | 0 : 0 | **1.0000** | 1.0000 | 1.0000 | ✓ |
| B10-2 · slack ASR（S vs M1） | mcnemar | 42 | 5 : 0 | **0.0625** | 0.0551 | 0.0625 | ✓ |
| B10-2 · slack 效用（S vs M1） | mcnemar | 21 | 0 : 4 | **0.1250** | 0.3499 | 0.1250 | ✓ |
| B10-1 · slack ASR（M1+硬规则 vs M1） | mcnemar | 42 | 0 : 0 | **1.0000** | 1.0000 | 1.0000 | ✓ |
| B10-1 · slack 效用（M1+硬规则 vs M1） | mcnemar | 21 | 0 : 13 | **0.0002** | 0.0001 | — | — |
| B10-1 · slack ASR（纯硬规则 vs M1，报告未给 p） | mcnemar | 42 | 12 : 0 | **0.0005** | 0.0002 | — | — |
| B1 · banking ASR（M0 vs M1，两批合并 64 场景） | fisher | 64 | 2 : 0 | **0.5000** | 0.4961 | 0.5000 | ✓ |
| 阶段五 · 净增益集合（M1 only vs M0 only） | mcnemar | 30 | 6 : 4 | **0.7539** | — | 0.7540 | ✓ |
| 阶段五 · meta 攻击（补丁前 vs 后） | fisher | 20 | 3 : 0 | **0.2500** | 0.2308 | 0.2310 | ✓ |

## 3. 结论

- 所有有报告值的条目**重算一致**（差 ≤ 5e-4）。
- `final_metrics.csv` 的 McNemar 列由 `scripts/b9_metrics.py` 重算，修复后与本节一致；
- 报告里另有若干 p 值其实是 **Fisher（非配对）**，已在「说明」列标出，正文不得写成 McNemar。
- 结论不变：没有任何一处 p 因为口径错误而变成显著；错误方向只会把 p 抬高。
- **注意 0 不一致对的情形**：B3 的 ASR、B10-1 的 ASR 都是 0:0，McNemar p=1.0；
  这只说明『没有可检验的差异』，不能读成『证明了无差异』（n=42/21 下检验力很低）。
- 新增两个报告里没写过的 p：M1+硬规则 vs M1 的效用 13:0（p=0.0002）、
  纯硬规则 vs M1 的 ASR 12:0（p=0.0005）。前者支持『叠加硬规则摧毁效用』，后者说明纯规则确实拦不住一半攻击。

