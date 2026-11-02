# final_figures · 图注索引

> 每张图都由 `scripts/b9_figures.py` 从机器产物重画；数字不在脚本里手写。
> 图内页脚标注了数据来源文件与重算脚本。

## fig1_offline_vs_online.png

![fig1_offline_vs_online.png](final_figures/fig1_offline_vs_online.png)

离线 PRA 与线上 ACB 的散点（5 个 p1 系列 checkpoint，同一诊断集）。PRA 最高的 1.5B task-aware s0（0.856）线上拦截最低（21.4%），说明配对排序能力不能替代攻击拦截评估。数据 `results/diag/offline_vs_online.json`；重算 `scripts/b9_metrics.py`（fig1 段）、`scripts/b9_figures.py`。臂 E 标注来自 `results/e2e/slack/m2_SM_s0_b10e_inj1-3` 的调用级复算。

## fig2_dinj_seeds.png

![fig2_dinj_seeds.png](final_figures/fig2_dinj_seeds.png)

三个 seed 的 dInj 与任务盲臂对照，误差棒为场景簇 bootstrap 95%CI。M1 三 seed 为 +22.6~+24.5pp（载荷是告警线索，幅度稳定），M0 任务盲为 +55.4pp（更依赖载荷）。数据 `results/p2/diag/metrics.json`；重算 `scripts/b9_metrics.py`（C1 段）、`scripts/b9_figures.py`。

## fig3_suites_arms.png

![fig3_suites_arms.png](final_figures/fig3_suites_arms.png)

三套件 × 三臂 ASR，柱标为分子/分母。banking 为天花板（E0 25.0%），slack 与 travel 上 M1 相对 M0 分别为 0/42 vs 4/42、1/40 vs 6/40。数据 `results/e2e/*/*/scen.jsonl` 与 `results/ad_v3/*/scen_merged.jsonl`；重算 `scripts/b9_metrics.py`（C2 段）。

## fig4_cost_safety.png

![fig4_cost_safety.png](final_figures/fig4_cost_safety.png)

成本-安全散点。纯规则延迟约 1.2 µs（416 次调用实测）但 ASR 31.0%、效用 4.8%；Task-Shield 安全达标但效用 23.8%、延迟 574 ms；M1 同时取得 0% ASR 与 66.7% 效用、251 ms。M0 的延迟按同基座复用 M1 实测值（未单独测，图内已标注）。数据 `reports/b3_tshield.md`（slack 表）、`results/classifier/latency_rule_cpu.json`、`reports/final_metrics.csv`；重算 `scripts/b9_rule_latency.py`、`scripts/b9_figures.py`。

## fig5_ablation_waterfall.png

![fig5_ablation_waterfall.png](final_figures/fig5_ablation_waterfall.png)

六根消融轴。(a) 数据配方瀑布：E0 50.0% → 标准 SFT 11.9%（−38.1pp）→ 任务盲 9.5% → M1 0.0%（−9.5pp）。(b) 部署轴与配方轴：纯硬规则 28.6%、M1 0%、M1+硬规则 0%（安全零增益、效用 4.8%）、HB-sm 0%（调用级误拦 62.4%）。(c) 第七轴：M1 与 M0 在 P1 判定下的 DENY 集合（交集 20、M1 only 6、M0 only 4），6 条净增益中 4 条受污染，稳健子集 2 条；McNemar p=0.754。来源 `reports/deny_attribution.md` 第 3 节。轴②历史长度（ACB none .560→last3 .837→full .918）与轴⑥路由见图 6 与 `reports/b9_notes.md`。数据 `reports/final_metrics.csv`（B10 段）；重算 `scripts/b9_metrics.py`、`scripts/b9_figures.py`。

## fig6_routing.png

![fig6_routing.png](final_figures/fig6_routing.png)

检查比例 vs ACB，含读类（28 条）与写类（131 条）分解。从全查（100%）到 γ≥2（27.0%）省下 73% 的判定量，读类拦截从 92.9% 直接掉到 0；写类几乎不变（99.2%）。这是不做路由的直接理由。数据 `results/classifier/routing_ablation.json`；重算 `scripts/b9_metrics.py`（B10 routing 段）、`scripts/b9_figures.py`。

## fig_mech_v41flash.png

![fig_mech_v41flash.png](final_figures/fig_mech_v41flash.png)

机制探针（跨骨干，非本文主结果）。(a) A 组 4 个 travel 场景 × 2 臂：两臂都没有攻击调用、没有 DENY，浅蓝=任务完成、灰=撞 15 步上限。(b) 14 个攻击场景 × 2 臂：注入暴露 14/14，生成攻击调用 0，攻击成功 0；0/14 的 95% 上界 = 21.5%（Wilson），只能读成「未观察到」。骨干为 `deepseek-flash`（任务书写的 `deepseek-v4.1-flash` 在本账号返回 400）。数据 `results/mechanism_probe_v41flash/`（36 个 episode）；重算 `scripts/aggregate_probe.py`。

## fig_mech_v41flash_v2.png

![fig_mech_v41flash_v2.png](final_figures/fig_mech_v41flash_v2.png)

机制探针 v2（B 组改为 inj1 `send_direct_message`，D 组为 3 travel + 1 slack 干净场景）。(a) A 组 4 场景 × 2 臂：均无攻击调用、无 DENY，浅蓝=完成、灰=撞 15 步上限。(b) 14 个攻击场景 × 2 臂：注入暴露 14/14，攻击成功 E0 1 / M1 1（均为 B2，链接被写进外发正文，守卫判 ALLOW raw=0.0）；1/14 的 95% 上界 = 31%（Wilson）。与 v1 同名图并列，不合并。数据 `results/mechanism_probe_v41flash_v2/`；重算 `scripts/aggregate_probe_v2.py`。 B2 为两臂唯一成功案例（E0/M1 同型，守卫 ALLOW、raw=0.0），详见报告 B2 个案。
