# -*- coding: utf-8 -*-
"""阶段 0：项目盘点。只读，不改任何既有产物。

产出：
  runs/experiment_manifest.json   机器可读清单（代码/数据/模型哈希、进程、复用判定）
  reports/phase0_inventory.md     人读报告

规则：不假定任何文件名存在；找不到就如实记 missing。
"""
import hashlib
import json
import os
import subprocess
import sys
import time

R = "/data/projects/guardrails"
SKIP_DIRS = {"__pycache__", "frozen", ".git"}
MANIFEST = os.path.join(R, "runs/experiment_manifest.json")


def sha(p, chunk=1 << 20):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def walk(root, pats, skip=SKIP_DIRS, depth=3):
    out = []
    base_depth = root.rstrip("/").count("/")
    for dp, dns, fns in os.walk(root):
        if dp.count("/") - base_depth >= depth:
            dns[:] = []
        dns[:] = [d for d in dns if d not in skip]
        for fn in fns:
            if any(fn.endswith(p) for p in pats):
                out.append(os.path.join(dp, fn))
    return sorted(out)


def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                              timeout=60).stdout.strip()
    except Exception as e:                                    # noqa: BLE001
        return "ERR:%s" % e


def main():
    t0 = time.time()
    man = {"phase": 0, "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "root": R}

    # ---------------- 1. 环境 ----------------
    man["env"] = dict(
        host=sh("hostname"), user=sh("whoami"), date=sh("date"),
        gpu=sh("nvidia-smi --query-gpu=name,memory.used,memory.total,driver_version "
               "--format=csv,noheader"),
        python=sh("/data/conda/envs/guard/bin/python -V"),
        torch=sh("/data/conda/envs/guard/bin/python -c 'import torch;print(torch.__version__,"
                 "torch.cuda.is_available())'"),
        transformers=sh("/data/conda/envs/guard/bin/python -c 'import transformers;"
                        "print(transformers.__version__)'"),
        peft=sh("/data/conda/envs/guard/bin/python -c 'import peft;print(peft.__version__)'"),
        agentdojo=sh("/data/conda/envs/guard/bin/python -c 'import agentdojo;"
                     "print(agentdojo.__file__)'"),
        disk=sh("df -h /data | tail -1"),
    )

    # ---------------- 2. 进程 ----------------
    man["running_processes"] = [
        x for x in sh("ps -eo pid,etime,cmd --no-headers").splitlines()
        if any(k in x for k in ("train_drift", "diag_score", "ad_run3",
                                "vllm.entrypoints", "run_chain"))
        and "ps -eo" not in x
    ]

    # ---------------- 3. 代码哈希 ----------------
    code = []
    for p in walk(os.path.join(R, "scripts"), (".py", ".sh")) + \
            walk(os.path.join(R, "guard"), (".py",)):
        code.append(dict(path=os.path.relpath(p, R), bytes=os.path.getsize(p), sha256=sha(p)))
    man["code"] = code
    man["code_count"] = len(code)

    # ---------------- 4. 数据哈希 ----------------
    data = []
    for p in sorted(walk(os.path.join(R, "data"), (".jsonl", ".json"), skip=set(), depth=1)):
        data.append(dict(path=os.path.relpath(p, R), bytes=os.path.getsize(p), sha256=sha(p),
                         lines=sum(1 for _ in open(p, "rb")) if p.endswith(".jsonl") else None))
    man["data"] = data

    # ---------------- 5. 模型与权重 ----------------
    models = []
    pg2 = "/data/hf_cache/pg2-86m"
    models.append(dict(name="pg2-86m", path=pg2, kind="sequence_classifier",
                       exists=os.path.isdir(pg2),
                       files=sorted(os.listdir(pg2)) if os.path.isdir(pg2) else []))
    for b in ("qwen1.5b", "qwen3b", "qwen7b"):
        p = "/data/hf_cache/" + b
        models.append(dict(name=b, path=p, kind="causal_lm", exists=os.path.isdir(p)))
    ad = os.path.join(R, "guard/adapters")
    adapters = []
    for d in sorted(os.listdir(ad)) if os.path.isdir(ad) else []:
        f = os.path.join(ad, d, "adapter_model.safetensors")
        if os.path.isfile(f):
            adapters.append(dict(name=d, path=os.path.relpath(f, R),
                                 bytes=os.path.getsize(f), sha256=sha(f)))
    man["models"] = models
    man["adapters"] = adapters

    # ---------------- 6. 遗留文件核对 ----------------
    legacy = {}
    for name in ("ad_ws2_trace.jsonl", "ad_bank2_trace.jsonl", "contract_v4.py"):
        hits = sh("find %s -name '%s' -not -path '%s/frozen/*' 2>/dev/null"
                  % (R, name, R)).splitlines()
        legacy[name] = dict(found=bool(hits), paths=[os.path.relpath(h, R) for h in hits])
    man["legacy_names"] = legacy

    # trace 内容统计
    traces = {}
    for key in ("runs/ad_bank2_trace.jsonl", "runs/ad_ws2_trace.jsonl"):
        p = os.path.join(R, key)
        if not os.path.isfile(p):
            continue
        rows = [json.loads(l) for l in open(p, encoding="utf-8")]
        traces[key] = dict(
            calls=len(rows),
            scenarios=len({(r.get("user_task"), r.get("injection_task")) for r in rows}),
            tasks=len({r.get("user_task") for r in rows}),
            injection_tasks=sorted({r.get("injection_task") for r in rows
                                    if r.get("injection_task")}),
            suites=sorted({r.get("suite") for r in rows if r.get("suite")}),
            attacked_calls=sum(1 for r in rows if r.get("injection_task")),
            has_env_state=any(k in rows[0] for k in ("security", "utility", "executed")),
            fields=sorted(rows[0].keys()),
        )
    man["legacy_traces"] = traces

    # ---------------- 7. 指标可追溯性 ----------------
    trace = {}
    for pat, label in (("results/diag/metrics.json", "diag_metrics"),
                       ("results/p2/diag/metrics.json", "p2_metrics"),
                       ("results/e2e/compare.json", "e2e_compare")):
        p = os.path.join(R, pat)
        trace[label] = dict(exists=os.path.isfile(p),
                            sha256=sha(p) if os.path.isfile(p) else None)
    trains = {}
    for f in sorted(os.listdir(os.path.join(R, "results"))):
        if f.startswith("train_") and f.endswith(".json"):
            d = json.load(open(os.path.join(R, "results", f), encoding="utf-8"))
            trains[f] = dict(tag=d.get("tag"), best_epoch=d.get("best_epoch"),
                             best_val_macro_f1=d.get("best_val_macro_f1"),
                             has_args="args" in d, seed=(d.get("args") or {}).get("seed"),
                             task_aware=d.get("task_aware"))
    trace["train_records"] = trains
    man["traceability"] = trace

    # ---------------- 8. 输出目录 ----------------
    for d in ("runs/phase0", "runs/dataset_audit", "runs/baseline", "runs/classifier",
              "runs/guard_tests", "runs/agent/e0_baseline", "runs/agent/e1_non_task_aware",
              "runs/agent/e2_task_aware", "runs/ablation/a0_full",
              "runs/ablation/a1_without_task", "reports/final_figures"):
        os.makedirs(os.path.join(R, d), exist_ok=True)
    man["output_dirs"] = sorted(d for d in os.listdir(os.path.join(R, "runs")))

    man["elapsed_s"] = round(time.time() - t0, 1)
    json.dump(man, open(MANIFEST, "w"), ensure_ascii=False, indent=2)
    print("-> %s (%d code, %d data, %d adapters, %.1fs)"
          % (MANIFEST, len(code), len(data), len(adapters), man["elapsed_s"]))
    for k, v in traces.items():
        print("%-28s calls=%d scen=%d inj=%d env_state=%s"
              % (k, v["calls"], v["scenarios"], len(v["injection_tasks"]), v["has_env_state"]))
    print("processes:", man["running_processes"] or "none")


if __name__ == "__main__":
    main()
