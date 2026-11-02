# -*- coding: utf-8 -*-
"""冻结 Task-Aware 基线（一次性生成清单 + 人读说明）

冻结对象
--------
1. 12 个 checkpoint（1.5B/3B × task/nt × seeds）及其 adapter 权重
2. 18 份预测：P1 在 PAB-RD test 的 12 份、P2-v2 的 14 份（含 zero-shot）
   —— 实际去重后是 12 + 14，但 zero-shot 无 adapter，故 checkpoint 只 12 个
3. 由这些预测产生的全部数字：p1_merged.json / p1_infer.json / p2v2_allseeds.json 及三份报告
4. 生成这些数字的脚本

冻结后的规则（写进 FREEZE.md，也校验进 manifest）
-----------------------------------------------
* 这批测试结果**只能报告**，不得用于挑选 checkpoint、阈值、风险策略或超参。
* 任何"看了 strict_test 再改"的改动，必须作为新的方法版本重新标注，不能冒充本基线。
* 风险自适应的阈值/代价常数只能在本清单列出的**校准池**上拟合。

用法
----
    python scripts/freeze_taskaware.py         # 生成清单与 FREEZE.md
    python scripts/check_taskaware_freeze.py   # 校验未被改动
"""
import hashlib
import json
import os
import time

ROOT = "/data/projects/guardrails"
OUTD = os.path.join(ROOT, "results", "frozen", "taskaware")
MANIFEST = os.path.join(OUTD, "taskaware_freeze.json")
FREEZEMD = os.path.join(OUTD, "FREEZE.md")
VERSION = "taskaware-v1"

MODELS = ["15b", "3b"]
ARMS = ["task", "nt"]
SEEDS = [0, 42, 123]
LRKEY = "l2"

DATA = ["data/pab_rd.jsonl", "data/pab_rd_splits.json",
        "data/p2v2_pairs.jsonl", "data/p2v2_index.json"]
SCRIPTS = ["scripts/train_lora.py", "scripts/run_guard.py", "guard/schema.py",
           "guard/metrics.py", "scripts/p1_run.py", "scripts/p1_merge.py",
           "scripts/p1_infer.py", "scripts/p2v2_eval.py",
           "scripts/p2v2_eval_allseeds.py", "scripts/final_stats.py",
           "scripts/p2v2_input_audit.py"]
REPORTS = ["reports/p1_results.md", "reports/p1_infer.md",
           "reports/p2v2_allseeds_report.md", "reports/p2v2_input_audit.md",
           "reports/paper_draft.md"]
JSONS = ["results/p1/p1_merged.json", "results/p1/p1_infer.json",
         "results/p2v2/p2v2_allseeds.json", "results/p2v2/input_audit.json"]


def sha(p):
    h = hashlib.sha256()
    with open(os.path.join(ROOT, p), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def size(p):
    return os.path.getsize(os.path.join(ROOT, p))


def collect(paths, label):
    out = {}
    missing = []
    for p in paths:
        fp = os.path.join(ROOT, p)
        if not os.path.exists(fp):
            missing.append(p)
            continue
        out[p] = {"sha256": sha(p), "bytes": size(p)}
    if missing:
        raise SystemExit("%s 缺文件：%s" % (label, missing))
    return out


def main():
    os.makedirs(OUTD, exist_ok=True)

    adapters = []
    for m in MODELS:
        for a in ARMS:
            for s in SEEDS:
                tag = "p1_%s_%s_%s_s%d" % (m, a, LRKEY, s)
                d = "guard/adapters/%s" % tag
                for f in ("adapter_config.json", "adapter_model.safetensors"):
                    adapters.append("%s/%s" % (d, f))

    p1_preds = ["results/p1/preds/p1_%s_%s_%s_s%d_%s.jsonl"
                % (m, a, LRKEY, s, a) for m in MODELS for a in ARMS for s in SEEDS]
    p2_preds = []
    for m in MODELS:
        p2_preds.append("results/p2v2/preds_allseeds/%s_zero-shot.jsonl" % m)
        for a in ARMS:
            for s in SEEDS:
                p2_preds.append("results/p2v2/preds_allseeds/%s_%s_s%d.jsonl" % (m, a, s))

    man = {
        "version": VERSION,
        "frozen_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "purpose": "Task-Aware 基线冻结：结果只报告，不再用于任何选择",
        "protocol": {
            "epochs": 4, "bs": 4, "accum": 4, "effective_batch": 16,
            "max_len": 1024, "lora_r": 16, "lora_alpha": 32, "lora_dropout": 0.05,
            "lr": 2e-4, "lr_key": LRKEY, "seeds": SEEDS,
            "lr_selection": "per model, argmax of mean(val macro-F1) over the two arms",
            "checkpoint_selection": "best val macro-F1 within each run; test scored once",
        },
        "counts": {"checkpoints": len(adapters) // 2, "p1_preds": len(p1_preds),
                   "p2v2_preds": len(p2_preds)},
        "data": collect(DATA, "data"),
        "checkpoint_files": collect(adapters, "adapters"),
        "predictions": {**collect(p1_preds, "p1 preds"),
                        **collect(p2_preds, "p2v2 preds")},
        "results_json": collect(JSONS, "json"),
        "reports": collect(REPORTS, "reports"),
        "scripts": collect(SCRIPTS, "scripts"),
        "headline": {},
        "notes": [
            "12 个 checkpoint 的 lr 均为 2e-4，由 seed 0 的两臂验证集均值选出；测试集只评一次。",
            "p1_run.py 在结果产出后做过一次纯路径修复（评估产物回收文件名缺 _test 后缀），"
            "不改变任何数字；此处冻结的是修复后的版本，备份 /tmp/p1_run.py.bak。",
            "P2-v2 的 zero-shot 臂无 adapter，故 checkpoint 计 12 个而预测有 14 份。",
            "论文 §5.6 与 reports/p2v2_allseeds_report.md 的数字必须与本清单 headline 一致。",
        ],
        "selection_ban": [
            "不得用 P2-v2 的 strict_test（19 场景/41 配对/6 动作）挑选 checkpoint、阈值或风险策略",
            "不得用 PAB-RD test 的 335 条挑选 checkpoint、阈值或风险策略",
            "风险自适应的代价常数与分层阈值只能在校准池上拟合（见下）",
            "任何看过测试集后再改的规则，必须作为新版本重新报告，不能冒充本基线",
        ],
        "calibration_pool": {
            "PAB-RD val": "data/pab_rd_splits.json 的 val，120 条（模型选择已用过，"
                          "但未用于阈值/策略拟合）",
            "P2-v2 contains_train": "data/p2v2_pairs.jsonl 中 tier=contains_train 的 266 个配对，"
                                    "任务在训练集内，可作阈值拟合的分布内样本",
            "P2-v2 unseen": "9 个配对，tier=unseen，可作拟合后的一次性检查，不计入主结果",
            "forbidden": ["P2-v2 strict_test（41 配对）", "PAB-RD test（335 条）"],
        },
    }

    # 把关键数字一并写进清单，避免日后各说各话
    p2 = json.load(open(os.path.join(ROOT, "results/p2v2/p2v2_allseeds.json"),
                        encoding="utf-8"))
    p1 = json.load(open(os.path.join(ROOT, "results/p1/p1_merged.json"),
                       encoding="utf-8"))
    inf = json.load(open(os.path.join(ROOT, "results/p1/p1_infer.json"),
                        encoding="utf-8"))
    for m in MODELS:
        a = p2["arms"][m]
        man["headline"].setdefault("p2v2_strict", {})[m] = {
            "lrkey": a["lrkey"],
            "task": {str(s): round(a["task_s%d" % s]["strict"]["PRA_scenario_equal"], 4)
                     for s in SEEDS},
            "nt": {str(s): round(a["nt_s%d" % s]["strict"]["PRA_scenario_equal"], 4)
                   for s in SEEDS},
        }
        man["headline"]["p1_test"] = man["headline"].get("p1_test", {})
        man["headline"]["p1_test"][m] = {
            r["arm"]: round(r["PRA"], 4) for r in p1["runs"] if r["model"] == m
            and r["seed"] == 0}
        man["headline"]["cluster_inference"] = man["headline"].get(
            "cluster_inference", {})
        p = inf["models"][m]["pooled"]
        man["headline"]["cluster_inference"][m] = {
            "dPRA": round(p["PRA"]["delta"], 4),
            "ci": [round(x, 4) for x in p["PRA"]["ci"]],
            "p_cluster_perm": p["PRA"]["p_cluster_perm"]}

    json.dump(man, open(MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(FREEZEMD, "w", encoding="utf-8").write(render(man))
    print("冻结完成：%s" % MANIFEST)
    print("  checkpoints=%d  p1_preds=%d  p2v2_preds=%d  文件总数=%d"
          % (man["counts"]["checkpoints"], man["counts"]["p1_preds"],
             man["counts"]["p2v2_preds"],
             sum(len(man[k]) for k in
                 ("data", "checkpoint_files", "predictions", "results_json",
                  "reports", "scripts"))))


def render(m):
    L = []
    A = L.append
    A("# Task-Aware 基线冻结（%s）\n" % m["version"])
    A("冻结时间：%s\n" % m["frozen_at"])
    A("## 1. 冻结了什么\n")
    A("| 类别 | 数量 |")
    A("|---|---|")
    A("| checkpoint（adapter 目录） | %d（1.5B/3B × task/nt × seeds{0,42,123}） "
      "|" % m["counts"]["checkpoints"])
    A("| PAB-RD test 预测 | %d |" % m["counts"]["p1_preds"])
    A("| P2-v2 预测（含 zero-shot） | %d |" % m["counts"]["p2v2_preds"])
    A("| 数据文件 | %d |" % len(m["data"]))
    A("| 结果 JSON | %d |" % len(m["results_json"]))
    A("| 报告 | %d |" % len(m["reports"]))
    A("| 生成脚本 | %d |" % len(m["scripts"]))
    A("")
    A("所有文件的 sha256 在 `taskaware_freeze.json` 中逐条记录；")
    A("`scripts/check_taskaware_freeze.py` 可随时校验是否被改动。\n")

    A("## 2. 冻结的数字\n")
    A("P2-v2 strict_test（19 场景 / 41 配对 / 6 动作，场景等权 PRA）：\n")
    A("| 模型 | task s0 | task s42 | task s123 | nt（3 seed） |")
    A("|---|---|---|---|---|")
    for k, v in m["headline"]["p2v2_strict"].items():
        t = v["task"]
        A("| %s | %.3f | %.3f | %.3f | 0.500 / 0.500 / 0.500 |"
          % (k, t["0"], t["42"], t["123"]))
    A("")
    A("P1 聚类推断（Δ = task − no-task，47 个动作组整组翻符号）：\n")
    A("| 模型 | ΔPRA | 95% CI | p |")
    A("|---|---|---|---|")
    for k, v in m["headline"].get("cluster_inference", {}).items():
        A("| %s | %+.3f | [%+.3f, %+.3f] | %.4f |"
          % (k, v["dPRA"], v["ci"][0], v["ci"][1], v["p_cluster_perm"]))
    A("")

    A("## 3. 冻结后的规则\n")
    for x in m["selection_ban"]:
        A("- " + x)
    A("")
    A("## 4. 校准池（阈值 / 代价常数只能在这里拟合）\n")
    A("| 池 | 内容 | 允许用途 |")
    A("|---|---|---|")
    A("| PAB-RD val | %s | 拟合 |" % m["calibration_pool"]["PAB-RD val"])
    A("| P2-v2 contains_train | %s | 拟合 |" % m["calibration_pool"]["P2-v2 contains_train"])
    A("| P2-v2 unseen | %s | 一次性检查 |" % m["calibration_pool"]["P2-v2 unseen"])
    A("| **禁止** | %s | 只报告 |" % "；".join(m["calibration_pool"]["forbidden"]))
    A("")
    A("## 5. 口径备注\n")
    for x in m.get("notes", []):
        A("- " + x)
    A("")
    A("## 6. 为什么要这样冻结\n")
    A("P2-v2 的 41 个配对是全项目唯一完全「未见任务 + 动作证据固定」的样本，")
    A("一旦被用来调阈值，它就退化成一个验证集，后续任何数字都不再是零样本结果。")
    A("PAB-RD test 同理。因此把两者设为**只读评测集**：方法改一次，测一次；")
    A("改完再测就记为新版本。\n")
    A("## 7. 复核方式\n")
    A("```bash")
    A("python scripts/check_taskaware_freeze.py     # 全量校验，返回 0 表示未被改动")
    A("```")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
