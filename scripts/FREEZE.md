# P0 冻结清单

**状态：CLOSED（2026-10-30 22:40）**

自此之后，以下内容只读，任何改动都必须作为新版本（p0-1.2 起）重新走一遍一致性检查，
不得就地修改。

## 1. 冻结的版本号

| 项 | 值 |
|---|---|
| metric_version | **`p0-1.1`** |
| 指标定义所在 | `scripts/unified_eval_v2.py`（PRA / SPA / TieRate / Macro-F1） |
| 推断实现所在 | `scripts/final_stats.py`（动作聚类 bootstrap + 整组翻符号置换） |
| 表格生成 | `scripts/final_report.py` → `results/frozen/final_report.json` |

指标定义（逐字冻结）：

```
wins(a,o) = 1[s(a) > s(o)],  ties = 1[s(a) = s(o)],  losses = 1[s(a) < s(o)]
PRA = (wins + 0.5*ties)/n,  SPA = wins/n,  TieRate = ties/n
恒等式：PRA = SPA + 0.5*TieRate        （逐臂断言，20/20 通过）
```

## 2. 冻结的哈希

| 文件 | sha256（前 16 位） | 说明 |
|---|---|---|
| `data/pab_rd.jsonl` | `9af72b7559f51888` | 数据集 |
| `data/pab_rd_splits.json` | `1a1a6323ef421cb1` | 划分（train/val/test） |
| — | `10751fff54a90ae1` | pair_id 集合哈希（由数据决定） |
| `results/frozen/final_report.json` | `ca3456fb3360190b` | 唯一表格源 |
| `reports/paper_draft.md` | `3ce77ddcc972bead` | 论文（P1 后将更新，本哈希仅记录 P0 状态） |

## 3. 冻结的规模

335 测试样本 / 90 配对 / 47 动作组 / 25 任务组。

## 4. 已标 SUPERSEDED 的旧结论

以下结论在 P0 阶段被**推翻或降级**，论文中已改为"曾报告过，现已更正"的写法，
不得再作为结论引用。详见 `reports/SUPERSEDED.md`。

| # | 旧结论 | 状态 | 原因 |
|---|---|---|---|
| S1 | 合并 4 个 Guard 的 360 对得 p=1.1e-10 / CMH 7.9e-7 | **SUPERSEDED** | 同一 90 对被重复测量，360 不是 360 个独立观测 |
| S2 | 合并 p=0.0007 是"动作聚类检验" | **SUPERSEDED** | 它是 SPA 的配对层普通符号检验（41:15），不含聚类 |
| S3 | 三指标只在一格分歧，因 Macro-F1 有 4 倍分辨率 | **SUPERSEDED** | 335 样本只落在 25 个任务组，按任务重采样后含 0 |
| S4 | task-awareness 只在 7B 出现（容量门槛） | **SUPERSEDED** | 被 0.5B/3B 的显著结果推翻 |
| S5 | 任务贡献在 1.5B 上不显著（p=0.42） | **SUPERSEDED** | 训练伪影：aware 臂 ep1 见顶、blind 臂 ep4 见顶；同 lr 重训后 +17.8pp |
| S6 | 0.5B / 7B / 1.5B_lr4 的 ΔPRA 显著 | **SUPERSEDED** | 仅在配对独立假设下成立；聚类置换后为 0.166 / 0.060 / 0.075 |
| S7 | 单次运行的逐尺寸点估计可作结论 | **SUPERSEDED** | 每格仅 1 个种子，方差未知；由 P1 多随机种子取代 |

## 5. 冻结后仍然成立的结论

| # | 结论 | 证据 |
|---|---|---|
| K1 | 表面特征（工具名/动作文本/TF-IDF）在配对指标上恒为 50.0%，SPA = 0 | 构造性定理 + 6 个基线实测 |
| K2 | TS-Bench 上工具名查表 macro-F1 0.960，留出 5 个跨标签工具后跌到 0.143，最小对仅 0.48% | `reports/p1_findings.md` |
| K3 | 去任务后守卫仍有 0.71–0.78 PRA，接地是主体能力 | 动作聚类 CI |
| K4 | 3B 的 ΔPRA 在动作聚类置换下仍显著（0.0038） | `final_report.json` |
| K5 | 等权合并（0.5B/1.5B/3B 各 1/3）ΔPRA=+0.085、ΔSPA=+0.189 | 聚类 CI/p |

## 6. 复现入口

```bash
# 指标层（冻结，勿改）
python scripts/emit_all_preds.py
python scripts/unified_eval_v2.py
# 推断层（冻结，勿改）
python scripts/final_stats.py
# 唯一表格产物
python scripts/final_report.py
# 一致性断言（33 项）
python scripts/check_consistency.py
```
