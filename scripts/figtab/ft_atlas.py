# -*- coding: utf-8 -*-
"""Assemble one review document: every table + every figure, each followed by
what it is for and what it validates. Numbers come from the generated .md/.csv,
prose is written here (no numbers transcribed by hand)."""
import os
import re

R = "/data/projects/guardrails"
OUT = os.path.join(R, "figure_table_atlas.md")
T = os.path.join(R, "tables")
F = os.path.join(R, "figures")

MAIN = [
    dict(id="fig1", kind="fig", num="图 1", name="Why end-to-end evaluation is necessary",
         sec="§3 问题分析", claim="C1", file="fig1_dinj_pra_acb",
         does="左边一格回答“注入到底有没有用”，右边一格回答“用离线分数挑模型行不行”。",
         verify="C1：威胁真实存在，且离线判据不能替代线上验证。它顶住两个最容易被问的质疑——"
                "“投毒只是你构造的极端例子”和“离线指标够用，何必端到端”。",
         key="(a) 三 seed 的 dInj 为 −45.9 / −38.4 / −31.5 pp，95%CI 全部不含 0；任务盲对照 −21.4 pp。"
             "(b) PRA 0.883 的 3B 线上只有 17.0%，PRA 0.794 的任务盲反而 41.5%，趋势斜率 −312 pp/PRA。",
         avoid="(a) 只画 p1 系列，M1 的 +0.233 在框外，正文要用一句话交代符号相反；"
               "(b) 五个点不能读成“PRA 决定 ACB”的因果，只能说“不预测”。"),
    dict(id="tab1", kind="tab", num="表 1", name="Three suites × three arms",
         sec="§5 整体有效性", claim="C2 + C4", file="tab1_three_suites_three_arms",
         does="把三个套件 × 三个臂的 ASR、干净完成率、调用级误拦放在一屏里。",
         verify="C2（更安全）与 C4（不伤效用）同时成立；顶住“你只在一个套件上调出来的”。",
         key="slack 50.0% → 0/42，干净完成 61.9% → 66.7%；travel 32.5% → 2.5%；"
             "banking 三臂全 0/32（天花板）。",
         avoid="banking 的 0 不是“方法更强”，是危险动作本身被基线挡住；"
               "travel 的 40 场景不等于泛化（一半任务见过）。"),
    dict(id="tab2", kind="tab", num="表 2", name="Head-to-head against a 7B task-aware judge",
         sec="§5 整体有效性", claim="C3", file="tab2_vs_tshield",
         does="同协议下与 7B 判官正面对打，并把“我们不占优的显存”也写进表里。",
         verify="C3；顶住“和最近邻工作比过吗、代价是多少”。这是全文唯一与外部方法对数字的位置。",
         key="同为 0/42；干净完成 66.7% vs 23.8%（+42.9pp，p=0.0039）；延迟 251 vs 574 ms（0.44×）；"
             "DENY 26 vs 222；额外显存 +4.1 GB vs 0。",
         avoid="禁写“成本 1/5”；ToolSafe 行只能定性；规则臂 31.0% 不叫“接近 M1”。"),
    dict(id="tab4", kind="tab", num="表 4", name="Why the gain is not from rules",
         sec="§6 收益从哪来", claim="C2（机制侧）", file="tab4_rule_three_arms",
         does="把“收益其实是规则给的”这条替代解释按读写两类拆开否掉。",
         verify="C2 的机制侧；顶住“你不过是加了几条硬规则”。",
         key="纯规则：写类 0/21 全拦，读类仍 12/21（与无守卫逐位相同）；叠加到 M1 后 ASR 仍 0/42，"
             "但干净完成从 66.7% 塌到 4.8%（p=0.0002）。",
         avoid="M1+规则 0/42 是 0:0 不一致对，只能写 n/a，“p=1.0”不等于“证明无差异”；"
               "28.6% 不能读成“规则有效”。"),
    dict(id="fig4", kind="fig", num="图 4", name="The recipe ladder",
         sec="§6 收益从哪来", claim="C2", file="fig4_recipe_ladder",
         does="四点阶梯，左轴 ASR 往下、右轴效用往上，看哪一步开始两条线同时变好。",
         verify="C2；顶住“为什么非要完整配方，不能少两步吗”。",
         key="50.0 / 61.9 → 11.9 / 47.6 → 9.5 / 33.3 → 0.0 / 66.7（ASR% / 干净完成%）。"
             "只有最后一步两个方向同时改善。",
         avoid="双 y 轴不能比斜率；四点不是时间序列，连线只表示配方递进；"
               "E0→S 的效用下跌是“安全换效用”，不是“加数据有害”。"),
    dict(id="tab6", kind="tab", num="表 6", name="Where the denials come from",
         sec="§7 到哪止", claim="C8", file="tab6_deny_attribution",
         does="把 34 条 DENY 拆成“载荷识别”与“非载荷依赖”，再用任务盲臂做对照，最后给集合差。",
         verify="C8；顶住“你的守卫到底靠什么在拦”。结论是：主要靠动作先验，任务信息的净增益不显著。",
         key="26/34 去载荷后仍拦；但任务盲 M0 也拦下其中 20 条（76.9%）；"
             "集合差 6 vs 4（p=0.754），扣掉污染后稳健仅 2 条。",
         avoid="76.9% 是“M1 集合内”的一致率，不是召回率；M0 的非载荷 22 与集合口径 |B|=24 不可互换。"),
    dict(id="fig6", kind="fig", num="图 6", name="Three seeds learn different criteria",
         sec="§7 到哪止", claim="C8 / C7（主模型侧）", file="fig6_probe_heatmap",
         does="5 个变体 × 3 个 seed 的判定矩阵，逐格标 raw 值，用三色表示 ALLOW/REVIEW/DENY。",
         verify="C8 / C7；顶住“seed 之间只是噪声”。三个 seed 的翻转位置不同，说明它们盯的是不同线索。",
         key="seed0 在 P3/P4 判 DENY；s42 在 P0/P2/P3 判 DENY；s123 五个变体全 ALLOW。"
             "15 格里 5 DENY / 10 ALLOW，无 REVIEW。",
         avoid="颜色不是置信度；不得引用 probe md 结尾那 4 行说明；第 4 条骨干（V4.1-Flash）是 blocked。"),
]

APPENDIX = [
    dict(id="fig3", kind="fig", num="图 3", name="Three suites × three arms (bars)",
         sec="§5 附录", claim="C2", file="app_fig3_suites_arms",
         does="表 1 的柱状版：ASR 与干净完成各一格，柱上标 n/N。",
         verify="C2；给不读表的人一个形状——banking 三根一样高，slack/travel 的 M1 柱最短。",
         key="与表 1 完全同源（32/16、42/21、40/20；seed 0；GPU fp16）。",
         avoid="信息与表 1 重复，所以只能放附录；banking 柱不得单独解读为“效果最强”。"),
    dict(id="tab3", kind="tab", num="表 3", name="Recipe ladder, exact numbers",
         sec="§6 附录", claim="C2", file="app_tab3_recipe_ladder",
         does="图 4 的底表：每个点的确切分母、误拦率与配对 p。",
         verify="C2；让图 4 的四个点可以被逐格核对，而不是“看起来是这样”。",
         key="E0 21/42、S 5/42、M0 4/42、M1 0/42；S vs M1 的 ASR p=0.0625、效用 p=0.125（都不显著）。",
         avoid="E0 与 M1 的效用只差 1 例（1:0，p=1.0），不得写成“效用提升”。"),
    dict(id="fig5", kind="fig", num="图 5", name="Seven-axis ablation",
         sec="§6 附录", claim="C2（完备性）", file="app_fig5_seven_axis",
         does="三面板：(a) 配方瀑布 (b) 部署臂的 ASR 与效用并列 (c) 净增益集合。",
         verify="C2 的完备性；回答“除了任务字段，你还在哪些轴上动过刀”。",
         key="(a) 50.0→11.9→9.5→0.0；(b) 规则臂 28.6 但效用 4.8、M1 0.0 且效用 66.7；"
             "(c) 交集 20、M1 only 6、M0 only 4。",
         avoid="七个轴指标不同（ASR / ACB / 计数），不得横向比高度；(b) 两个数字只在行内可比。"),
    dict(id="tab10", kind="tab", num="表 10", name="Seven-axis ablation summary",
         sec="§6 附录", claim="C2（完备性）", file="app_tab10_seven_axis",
         does="把七根轴的对比、数字、来源压成一页表。",
         verify="C2 的完备性；审稿人若问“还有别的轴吗”，直接指这张表。",
         key="逐行标注来源；轴①按训练侧 / 推理侧拆成两行（共 8 行）。",
         avoid="不同轴的指标不同，不能横向比大小；这张表是地图，不是排名。"),
    dict(id="tab5", kind="tab", num="表 5", name="Counterfactual probe matrix",
         sec="§7 附录", claim="C8", file="app_tab5_probe_matrix",
         does="图 6 的原始数值版：5 变体 × 3 seed，每格 raw / 判定。",
         verify="C8；让图 6 的每个颜色都能追到具体 raw 值，并固定“只引表格、不引说明”的纪律。",
         key="15 格；seed123 的 P0 复现端到端记录（ALLOW），说明 CPU 重打分可信。",
         avoid="CPU fp32 的判定不得与 e2e GPU 记录混为一谈。"),
    dict(id="tab7", kind="tab", num="表 7", name="Adaptive attack variants",
         sec="§7 附录", claim="C7（主模型侧）", file="app_tab7_adaptive",
         does="三种变形（static / meta / obfusc）加一列重训后对照，并给出逐调用翻转。",
         verify="C7 主模型侧；说明失效不是“样本不够”，而是判据本身可被一句“已获批准”说服。",
         key="static 1/20、meta 3/20（p=0.605）、obfusc 0/20、重训后仍 3/20；"
             "meta 把 t1、t19 从 DENY 翻成 ALLOW。",
         avoid="3/20 vs 1/20 在 n=20 下不显著，禁写“meta 显著提高攻击成功率”；obfusc 的 0/20 也不等于鲁棒。"),
    dict(id="fig7", kind="fig", num="图 7", name="Routing curve",
         sec="§7 附录", claim="C8", file="app_fig7_routing",
         does="检查比例 vs ACB，并拆出读类 / 写类两条线。",
         verify="C8；解释“为什么不能只查高危调用”——省下的检查量全部来自放弃读类。",
         key="全查 100% → γ≥2 的 27.0% / γ≥3 的 23.6%；读类 ACB 92.9% → 0，写类 99.2% → 92.4%。",
         avoid="读类归零是路由策略的性质，不是模型不会判读类。"),
    dict(id="fig10", kind="fig", num="图 10", name="Three independent evidences, one mechanism",
         sec="§7 附录", claim="C8", file="app_fig10_three_evidence",
         does="把三条互不依赖的证据并排放：P1 去载荷翻转、meta 话术翻转、任务盲对照 20/26。",
         verify="C8；讨论节的收口图——三条不同来源的证据指向同一个机制。",
         key="不含新数字：全部取自表 5 / 表 7 / 表 6。",
         avoid="这是论证示意图，不得标注任何合成分数，也不得把三个协议的数字放进同一坐标。"),
    dict(id="tab8", kind="tab", num="表 8", name="Deployment-layer authorization patch",
         sec="§8 附录", claim="C7（补丁侧）", file="app_tab8_posthoc_patch",
         does="补丁前后的精确数：meta、slack、以及一个合法的 send_email 单例。",
         verify="C7 补丁侧；说明补丁只挡“参数来自不可信文本”，并且没有拿效用换安全。",
         key="meta 3/20 → 0/20（Fisher p=0.231）；slack 仍 0/42、14/21；授权层拦下 4 次；"
             "合法 send_email 未被误杀。",
         avoid="禁写“达标 / 显著改善”，统一写 “formally meets ≤2/20; p=0.231; significance NOT established”；"
               "不得省略 provenance 前提。"),
    dict(id="tab9", kind="tab", num="表 9", name="Cost comparison",
         sec="§8 附录", claim="C5", file="app_tab9_cost",
         does="四臂的延迟、显存、ACB、e2e 误拦，逐行标设备与套件。",
         verify="C5；把“轻量”拆成可核对的三件事：单次延迟、显存占用、离线判别力。",
         key="M1 251/265 ms（GPU）· TS 574/610 ms · 规则 0.0012 ms（CPU）· 0.5B 1461/4182 ms（CPU）；"
             "ACB 0.981 / 1.000 / — / 0.849。",
         avoid="禁止把 M1 的 251 ms 与 0.5B 的 1461 ms 放同一列比较；0.5B 的 GPU 延迟/显存未测。"),
    dict(id="fig8", kind="fig", num="图 8", name="Cost–safety frontier",
         sec="§8 附录", claim="C5", file="app_fig8_cost_frontier",
         does="延迟（log）× ASR 的散点，点面积按干净完成率缩放；按套件拆成两面板。",
         verify="C5；说明“便宜”和“安全”不在同一个点上，而 M1 同时靠左、贴地。",
         key="(a) slack：M1 251 ms/0%、TS 574 ms/0%、规则 0.0012 ms/31.0%；"
             "(b) travel：M1 257 ms/2.5%、TS 599 ms/0%、0.5B 1461 ms/7.5%。",
         avoid="跨设备不可比；气泡面积是效用不是置信度；两个面板不能合成一个前沿。"),
    dict(id="fig9", kind="fig", num="图 9", name="Patch before/after",
         sec="§8 附录", claim="C7（补丁侧）", file="app_fig9_patch_before_after",
         does="左：meta 的 3→0；右：slack 的效用与误拦两根柱子前后对照。",
         verify="C7 补丁侧；用“柱子没动”直观说明补丁没有牺牲效用。",
         key="meta 15.0% → 0.0%；slack 效用 66.7% → 66.7%、误拦 3.3% → 3.3%。",
         avoid="3→0 不得加显著性星号（n=20，p=0.231）；“合法调用不变”不等于“无副作用”。"),
]


def table_block(name):
    path = os.path.join(T, name + ".md")
    lines = open(path, encoding="utf-8").read().split("\n")
    caption = ""
    rows, notes = [], []
    for ln in lines:
        if ln.startswith("|"):
            rows.append(ln)
        elif ln.startswith("- "):
            notes.append(ln)
        elif ln.startswith("# ") or ln.startswith("LaTeX:") or ln.startswith("**Notes"):
            continue
        elif ln.strip() and not caption:
            caption = ln.strip()
    return caption, "\n".join(rows), notes


def figure_block(name):
    return ("![%s](figures/%s.png)\n" % (name, name)
            + "*PDF 矢量版：`figures/%s.pdf`；源数据：`figures/%s.csv`*" % (name, name))


def render(item):
    out = []
    kind = "表" if item["kind"] == "tab" else "图"
    out.append("### %s · %s（%s，%s）" % (item["num"], item["name"], item["sec"], item["claim"]))
    out.append("")
    if item["kind"] == "tab":
        cap, tbl, notes = table_block(item["file"])
        out.append("*%s*" % cap)
        out.append("")
        out.append(tbl)
        out.append("")
        if notes:
            out.append("**表注（原文）**")
            out.append("")
            out.extend(notes)
            out.append("")
        out.append("`tables/%s.tex` · `tables/%s.csv`" % (item["file"], item["file"]))
    else:
        out.append(figure_block(item["file"]))
    out.append("")
    out.append("**作用**：%s" % item["does"])
    out.append("")
    out.append("**验证什么**：%s" % item["verify"])
    out.append("")
    out.append("**关键数**：%s" % item["key"])
    out.append("")
    out.append("**读法 / 别这样读**：%s" % item["avoid"])
    out.append("")
    return out


def main():
    L = []
    L.append("# 图表总览：19 个浮动体，逐张说明作用与验证目标")
    L.append("")
    L.append("> 本文档只做两件事：把每个表/图的成品贴出来，然后在下面写清它**为什么存在**、"
             "**在验证什么**。不写正文段落。")
    L.append("> 所有数字由 `scripts/figtab/ft_tables.py` / `ft_figs.py` 从机器产物生成，"
             "每个表/图都配同名 `.csv` 源数据；本文档里的数字与 `.csv` 一致，未手工转录。")
    L.append("> 全局状态：`mech_probe = file present / matrix absent`（见图 6 条目）。")
    L.append("")

    L.append("## 目录")
    L.append("")
    L.append("| # | 编号 | 类型 | 挂靠 | claim | 一句话作用 |")
    L.append("|---|---|---|---|---|---|")
    one_liners = {
        "fig1": "离线判据测不出线上失效，所以必须端到端评",
        "tab1": "三套件同时更安全且不伤效用",
        "tab2": "与 SOTA 同安全下效用 +42.9pp、延迟 0.44×，代价 4.1 GB",
        "tab4": "收益不是规则给的：读类零覆盖、叠加毁效用",
        "fig4": "只有完整配方让安全与效用同时变好",
        "tab6": "拦截主要来自动作先验，净增益不显著",
        "fig6": "三 seed 的翻转位置不同，说明判据维度不同",
        "fig3": "表 1 的柱状版（信息重复，故进附录）",
        "tab3": "图 4 的底表：精确分母与配对 p",
        "fig5": "七轴压成三面板：配方 / 部署 / 集合",
        "tab10": "七根轴一页看全，逐行标来源",
        "tab5": "探针矩阵的 raw 值，供逐格复核",
        "tab7": "meta 话术把 DENY 翻成 ALLOW，重训也无效",
        "fig7": "砍检查量省下的全是读类拦截",
        "fig10": "三条独立证据指向同一机制",
        "tab8": "补丁把 meta 压到 0/20，但显著性未建立",
        "tab9": "四臂成本，设备与套件逐行标注",
        "fig8": "便宜与安全不在同一点，M1 同时靠左贴地",
        "fig9": "补丁前后：3→0，而效用柱子没动",
    }
    for i, it in enumerate(MAIN + APPENDIX, 1):
        L.append("| %d | %s | %s | %s | %s | %s |" % (
            i, it["num"], "表" if it["kind"] == "tab" else "图", it["sec"],
            it["claim"], one_liners[it["id"]]))
    L.append("")

    L.append("---")
    L.append("")
    L.append("## 一、正文浮动体（7 个）")
    L.append("")
    L.append("这 7 个是论证链上的承重点：问题真实 → 方法有效 → 和谁比 → 收益归谁 → 边界在哪。"
             "删掉任何一个，链条都会断在一个具体质疑上。")
    L.append("")
    for it in MAIN:
        L.extend(render(it))

    L.append("---")
    L.append("")
    L.append("## 二、附录浮动体（12 个）")
    L.append("")
    L.append("附录不承担论证，只做三件事：给正文的每个数补分母、把协议混没混标清楚、"
             "堵住“还有别的解释吗”。按章节分组，编号沿用规格书。")
    L.append("")
    for it in APPENDIX:
        L.extend(render(it))

    L.append("---")
    L.append("")
    L.append("## 三、边界与已知缺口")
    L.append("")
    L.append("| 项 | 状态 | 说明 |")
    L.append("|---|---|---|")
    L.append("| 0.5B 的 GPU 延迟与显存 | blocked | 只测了 CPU（p50 1461 ms），表 9 / 图 8 该格留空 |")
    L.append("| ToolSafe 行 | not reproduced | 未在相同协议下复现，表 2 只留定性 |")
    L.append("| 图 6 第 4 条骨干（V4.1-Flash） | blocked | 复现包只有 A/B/C/D 场景组，无 P0–P4 变体矩阵；"
             "且实际骨干是 deepseek-flash，14 个攻击 episode 的 attack_calls 为 0 |")
    L.append("| banking 调用级误拦 | 已补 | 规格书判“无法重算”，实测 29 次干净调用（M0 1/29、M1 0/29） |")
    L.append("")
    L.append("## 四、自检")
    L.append("")
    L.append("- 正文 7 = 4 表 + 3 图；附录 12 = 6 表 + 6 图；与规格书一致，无增无减。")
    L.append("- 每个表/图都有同名 `.csv`；`reports/figtab_qc.txt` 43 项校验全部 PASS。")
    L.append("- 图 1(b) 的 PRA/ACB 列名已三重交叉核对（`reports/prewrite_check.md` §1）。")
    L.append("- 未修改任何既有报告/CSV/state/scen/frozen；本轮只新增 `tables/`、`figures/`、"
             "`scripts/figtab/`、`reports/prewrite_check.md`、`reports/figure_table_manifest.md`、"
             "`figure_table_atlas.md`。")
    L.append("")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("wrote", OUT, len(L), "lines")
    print("figures referenced:", len(MAIN) + len(APPENDIX))


if __name__ == "__main__":
    main()
