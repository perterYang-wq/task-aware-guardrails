# -*- coding: utf-8 -*-
"""AgentDojo 场景级运行 + 真实轨迹采集（7B agent，本地 vLLM）

产出
----
* `--logdir` 下 AgentDojo 原生任务日志（含完整消息）
* `--trace` 逐次工具调用的 JSONL：场景 id / 用户任务 / 注入任务 / 步骤 /
  工具 / 参数 / 当步的 instruction、history、current_action（可直接喂给 Guard 与路由器）

用法
----
    python scripts/ad_run.py --suite banking --mode utility --limit 2      # 冒烟
    python scripts/ad_run.py --suite banking --mode attack                 # 全量场景
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

AD = "/data/projects/guardrails/repos/agentdojo/src"
sys.path.insert(0, AD)
sys.path.insert(0, "/data/projects/guardrails")

import openai  # noqa: E402
from agentdojo.agent_pipeline import (AgentPipeline, InitQuery, LocalLLM,  # noqa: E402
                                      SystemMessage, ToolsExecutionLoop)
from agentdojo.agent_pipeline.tool_execution import ToolsExecutor  # noqa: E402
import agentdojo.attacks.important_instructions_attacks as _iia  # noqa: E402
from agentdojo.attacks.important_instructions_attacks import (  # noqa: E402
    ImportantInstructionsAttack)

# 注入模板原先把"哪个模型"写进提示（如"GPT-4"）。本地 Qwen 不在 MODEL_NAMES 表里，
# 这里统一换成中性称呼，避免攻击模板与模型不匹配；其余注入逻辑不变。
_iia.get_model_name_from_pipeline = lambda _p: "AI model"

from tolerant_parse import install_tolerant_parser  # noqa: E402
install_tolerant_parser()   # 容错解析：本地 7B 的 <function> 闭合标签常写错
from agentdojo.benchmark import (run_task_with_injection_tasks,  # noqa: E402
                                 run_task_without_injection_tasks)
from agentdojo.logging import OutputLogger  # noqa: E402
from agentdojo.task_suite.load_suites import get_suite  # noqa: E402

SYS = "You are a helpful assistant."
CUR = {"suite": None, "user_task": None, "injection_task": None, "step": 0,
       "trace": None}


def blocks_to_text(content):
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    out = []
    for b in content:
        if isinstance(b, str):
            out.append(b)
        elif isinstance(b, dict):
            out.append(b.get("content") or "")
    return "".join(out)


class TracingExecutor(ToolsExecutor):
    """执行前记录一条轨迹（不影响执行）。"""

    def query(self, query, runtime, env, messages, extra_args):
        if messages and messages[-1]["role"] == "assistant":
            calls = messages[-1].get("tool_calls") or []
            for tc in calls:
                CUR["step"] += 1
                hist = []
                for m in messages:
                    if m.get("role") == "tool":
                        hist.append(blocks_to_text(m.get("content")))
                    elif m.get("role") == "assistant" and m.get("content"):
                        hist.append("assistant: " + blocks_to_text(m.get("content"))[:300])
                h = "\n---\n".join([x for x in hist if x])
                rec = {
                    "suite": CUR["suite"], "user_task": CUR["user_task"],
                    "injection_task": CUR["injection_task"], "step": CUR["step"],
                    "tool": tc.function,
                    "args": tc.args,
                    "instruction": query,
                    "history": h[-1600:],
                    "history_full": h,
                    "current_action": "(1) Thought: (omitted)\n(2) Action: %s\n"
                                      "(3) Action Input: %s"
                                      % (tc.function, json.dumps(tc.args, ensure_ascii=False)),
                    "ts": time.time(),
                }
                with open(CUR["trace"], "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return super().query(query, runtime, env, messages, extra_args)


def build_pipeline(base_url, model):
    client = openai.OpenAI(base_url=base_url, api_key="dummy")
    llm = LocalLLM(client, model, temperature=0.0, top_p=1.0)
    pipe = AgentPipeline([
        SystemMessage(SYS), InitQuery(), llm,
        ToolsExecutionLoop([TracingExecutor(), llm])])
    try:
        pipe.name = "local-%s" % model      # 供 AgentDojo 日志命名与 security 落盘
    except Exception:
        pass
    return pipe


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v1.2.2")
    ap.add_argument("--suite", default="banking")
    ap.add_argument("--mode", default="attack", choices=["utility", "attack", "both"])
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--model", default="qwen7b")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 个用户任务")
    ap.add_argument("--n-injections", type=int, default=0, help="每个用户任务只用前 N 个注入任务")
    ap.add_argument("--logdir", default="/data/projects/guardrails/runs/ad")
    ap.add_argument("--trace", default="/data/projects/guardrails/runs/ad_trace.jsonl")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--scen-out", default="", help="场景级 utility/security 落盘路径")
    a = ap.parse_args()

    suite = get_suite(a.version, a.suite)
    pipe = build_pipeline(a.base_url, a.model)
    attack = ImportantInstructionsAttack(suite, pipe) if a.mode in ("attack", "both") else None
    Path(a.logdir).mkdir(parents=True, exist_ok=True)
    os.makedirs(os.path.dirname(a.trace), exist_ok=True)

    ut_ids = list(suite.user_tasks)
    if a.limit:
        ut_ids = ut_ids[:a.limit]
    inj_ids = list(suite.injection_tasks)
    if a.n_injections:
        inj_ids = inj_ids[:a.n_injections]

    CUR.update(suite=a.suite, trace=a.trace)
    print("suite=%s users=%d injections=%d mode=%s"
          % (a.suite, len(ut_ids), len(inj_ids), a.mode), flush=True)

    t0 = time.time()
    if a.mode in ("utility", "both"):
        u = {}
        for i, ut_id in enumerate(ut_ids, 1):
            CUR.update(user_task=ut_id, injection_task=None, step=0)
            with OutputLogger(a.logdir):
                ok, _ = run_task_without_injection_tasks(
                    suite, pipe, suite.get_user_task_by_id(ut_id),
                    Path(a.logdir), a.force, a.version)
            u[ut_id] = ok
            if a.scen_out:
                with open(a.scen_out, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"user_task": ut_id, "injection_task": None,
                                        "utility": bool(ok), "security": None},
                                       ensure_ascii=False) + "\n")
            print("  [util %2d/%d] %-24s %s  (%.0fs)"
                  % (i, len(ut_ids), ut_id, "PASS" if ok else "fail", time.time() - t0),
                  flush=True)
        print("utility = %.1f%% (%d/%d)"
              % (100 * sum(u.values()) / max(1, len(u)), sum(u.values()), len(u)), flush=True)

    if a.mode in ("attack", "both"):
        util_all, sec_all = {}, {}
        for i, ut_id in enumerate(ut_ids, 1):
            CUR.update(user_task=ut_id, step=0)
            ut = suite.get_user_task_by_id(ut_id)
            # 逐个注入任务跑，便于记录当前场景
            for it_id in inj_ids:
                CUR.update(injection_task=it_id, step=0)
                with OutputLogger(a.logdir):
                    u, s = run_task_with_injection_tasks(
                        suite, pipe, ut, attack, Path(a.logdir), a.force,
                        [it_id], a.version)
                util_all.update(u)
                sec_all.update(s)
                if a.scen_out:
                    with open(a.scen_out, "a", encoding="utf-8") as f:
                        for k in u:
                            f.write(json.dumps({"user_task": k[0], "injection_task": k[1],
                                                "utility": bool(u[k]),
                                                "security": bool(s.get(k))},
                                               ensure_ascii=False) + "\n")
            print("  [atk %2d/%d] %-24s util=%.0f%% sec=%.0f%%  (%.0fs)"
                  % (i, len(ut_ids), ut_id,
                     100 * sum(v for k, v in util_all.items() if k[0] == ut_id)
                     / max(1, len(inj_ids)),
                     100 * sum(v for k, v in sec_all.items() if k[0] == ut_id)
                     / max(1, len(inj_ids)), time.time() - t0), flush=True)
        print("attack 场景数=%d  utility=%.1f%%  security=%.1f%%"
              % (len(util_all), 100 * sum(util_all.values()) / max(1, len(util_all)),
                 100 * sum(sec_all.values()) / max(1, len(sec_all))), flush=True)

    print("trace -> %s" % a.trace, flush=True)


if __name__ == "__main__":
    main()
