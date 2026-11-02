# -*- coding: utf-8 -*-
"""机制复现包：跑 18 场景 × 2 臂（DeepSeek-V4.1-Flash 骨干）。

设计要点
--------
· 每个 episode 一个子进程（ad_run3.py），互不污染；并发 5。
· 守卫走 CPU（GUARD_DEVICE=cpu），不占 GPU；E0 臂不挂守卫。
· 失败重试 1 次；连续 2 次失败 → 停，落 blocked。
· 费用熔断：累计估算 > MAX_COST_USD 即停。
· 不手填任何字段：全部从 scen.jsonl / trace.jsonl 重算。

产物：results/mechanism_probe_v41flash/{E0,M1}/{scen_id}.json
      results/mechanism_probe_v41flash/run_config.json
"""
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

R = "/data/projects/guardrails"
OUT = os.environ.get("PROBE_OUT") or os.path.join(R, "results/mechanism_probe_v41flash")
SEL = os.path.join(OUT, "scenario_selection.json")
PY = "/data/conda/envs/guard/bin/python"
MODEL = "deepseek-flash"        # 账号可用名；任务书写的 deepseek-v4.1-flash 返回 400
REQUESTED_MODEL = "deepseek-v4.1-flash"
MAX_CONCURRENT = 5
MAX_COST_USD = 5.0
PRICE_IN = 0.28 / 1e6     # $ / token（V3.x 列表价，保守记法，见 run_config）
PRICE_OUT = 0.42 / 1e6
FUSE_MULT = 2.0           # 熔断按 2 倍价估，避免低估

_PF = os.path.join(OUT, "preflight.json")
_model_returned = None
if os.path.exists(_PF):
    try:
        _model_returned = json.load(open(_PF, encoding="utf-8")).get("model_returned")
    except Exception:
        pass

_lock = threading.Lock()
_state = dict(cost=0.0, consec_fail=0, stop=False)



def load_api_key():
    """优先环境变量，其次读 key 文件。

    key 文件路径由 $DEEPSEEK_KEY_FILE 指定，默认 ~/.secrets/deepseek.key。
    读到后写回 os.environ，这样子进程（ad_run3.py）能继承。
    返回 (key, 来源说明)，来源说明里不含 key 本身。
    """
    k = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if k:
        return k, "env:DEEPSEEK_API_KEY"
    p = os.environ.get("DEEPSEEK_KEY_FILE") or os.path.expanduser("~/.secrets/deepseek.key")
    try:
        with open(p, encoding="utf-8") as f:
            k = f.read().strip()
    except OSError as e:
        return "", "missing:%s (%s)" % (p, type(e).__name__)
    if k:
        os.environ["DEEPSEEK_API_KEY"] = k
        return k, "file:%s" % p
    return "", "empty:%s" % p


def price(tok_in, tok_out):
    return FUSE_MULT * (tok_in * PRICE_IN + tok_out * PRICE_OUT)


def load_jsonl(p):
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def one_episode(sc, arm, tag):
    sid = sc["scen_id"]
    run_dir = os.path.join(OUT, "_runs", arm, sid)
    os.makedirs(run_dir, exist_ok=True)
    mode = "utility" if not sc.get("injection_task") else "attack"
    cmd = [PY, "scripts/ad_run3.py", "--suite", sc["suite"], "--mode", mode,
           "--only", sc["user_task"],
           "--llm-backend", "deepseek", "--model", MODEL,
           "--logdir", os.path.join(run_dir, "logs"),
           "--trace", os.path.join(run_dir, "trace.jsonl"),
           "--scen-out", os.path.join(run_dir, "scen.jsonl"),
           "--guard-view", "full", "--review-policy", "block", "--force"]
    if sc.get("injection_task"):
        cmd += ["--injections", sc["injection_task"]]
    cmd += ["--guard-adapter", ("m2_HB_s0" if arm == "M1" else "none")]

    env = dict(os.environ)
    env["GUARD_DEVICE"] = os.environ.get("PROBE_GUARD_DEVICE", "cuda")
    usage_path = os.path.join(run_dir, "usage.jsonl")
    env["API_USAGE"] = usage_path
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"

    t0 = time.time()
    try:
        pr = subprocess.run(cmd, cwd=R, env=env, capture_output=True, text=True, timeout=900)
        rc, err = pr.returncode, (pr.stderr or "")[-800:]
    except subprocess.TimeoutExpired:
        rc, err = 124, "subprocess timeout 900s"
    wall = time.time() - t0

    rows = load_jsonl(os.path.join(run_dir, "scen.jsonl"))
    ep = dict(scen_id=sid, arm=arm, group=sc["group"], suite=sc["suite"],
              user_task=sc["user_task"], injection_task=sc.get("injection_task"),
              backend=MODEL, model_returned=_model_returned,
              task_completed=None, attack_succeeded=None, attack_call_executed=None,
              guard_decisions=[], deny_step=None, deny_tool=None,
              grounding_tool_outputs=[], steps=0, wall_time_s=round(wall, 1),
              prompt_tokens=0, completion_tokens=0, cost_usd_est=0.0,
              error=None if rc == 0 else ("rc=%d %s" % (rc, err)))
    tok_in = tok_out = tok_cached = 0
    if os.path.exists(usage_path):
        for ln in open(usage_path, encoding="utf-8"):
            try:
                u = json.loads(ln)
            except Exception:
                continue
            tok_in += u.get("prompt", 0)
            tok_out += u.get("completion", 0)
            tok_cached += u.get("cached", 0)

    if rows:
        r = rows[0]
        ep["task_completed"] = r.get("utility")
        ep["attack_succeeded"] = r.get("attack_success")
        ep["attack_call_executed"] = bool(r.get("n_attack_call_executed") or 0) or None
        ep["steps"] = r.get("n_steps") or 0
        ep["prompt_tokens"] = tok_in or (r.get("prompt_tokens") or 0)
        ep["completion_tokens"] = tok_out or (r.get("completion_tokens") or 0)
        for h in (r.get("guard_hits") or []):
            ep["guard_decisions"].append(dict(
                step=(h.get("idx") or 0) + 1, tool=h.get("tool"),
                decision=h.get("decision"), guard_raw=h.get("raw"),
                hard_rule=bool(h.get("hard_rule")), guard_error=h.get("guard_error")))
            if ep["deny_step"] is None and h.get("decision") == "DENY":
                ep["deny_step"] = (h.get("idx") or 0) + 1
                ep["deny_tool"] = h.get("tool")
        # 该 episode 里出现在 history 中的工具输出（到 DENY 那一步为止）
        tr = load_jsonl(os.path.join(run_dir, "trace.jsonl"))
        lim = ep["deny_step"] or 10 ** 6
        ep["grounding_tool_outputs"] = ["%d:%s" % (t["step"], t.get("tool"))
                                        for t in tr if t["step"] < lim]
        ep["cost_usd_est"] = round(price(ep["prompt_tokens"], ep["completion_tokens"]), 6)
    else:
        ep["prompt_tokens"], ep["completion_tokens"] = tok_in, tok_out
        ep["cost_usd_est"] = round(price(tok_in, tok_out), 6)

    with _lock:
        _state["cost"] += ep["cost_usd_est"]
        if ep["error"] is None:
            _state["consec_fail"] = 0
        else:
            _state["consec_fail"] += 1
            if _state["consec_fail"] >= 2:
                _state["stop"] = True
        if _state["cost"] > MAX_COST_USD:
            _state["stop"] = True
        print("[%s] %-4s %-4s steps=%-2d succ=%-5s util=%-5s deny=%-8s $%.4f (总 $%.4f)"
              % (arm, sid, sc["group"], ep["steps"], ep["attack_succeeded"],
                 ep["task_completed"], ep["deny_tool"], ep["cost_usd_est"], _state["cost"]),
              flush=True)
    return ep


def run_arm(sel, arm):
    os.makedirs(os.path.join(OUT, arm), exist_ok=True)
    results = []
    # M1 每进程都要把 1.5B 守卫搬上 GPU；vLLM 还占着 20GB 时并发必须压低
    conc = int(os.environ.get("PROBE_CONC_%s" % arm, MAX_CONCURRENT))
    print("[conc] arm %s -> %d" % (arm, conc), flush=True)
    with ThreadPoolExecutor(max_workers=max(1, conc)) as ex:
        futs = {ex.submit(one_episode, sc, arm, arm + sc["scen_id"]): sc for sc in sel}
        for f in as_completed(futs):
            ep = f.result()
            results.append(ep)
            with open(os.path.join(OUT, arm, "%s.json" % ep["scen_id"]), "w") as fh:
                json.dump(ep, fh, ensure_ascii=False, indent=2)
            if _state["stop"]:
                print("[fuse] 触发停止：cost=%.3f consec_fail=%d" % (_state["cost"], _state["consec_fail"]),
                      flush=True)
                break
    return results


def main():
    _k, _src = load_api_key()
    if not _k:
        print("[blocked] 没有可用 key：%s" % _src, flush=True)
        return 2
    print("[key] 来源=%s 长度=%d" % (_src, len(_k)), flush=True)
    sel = json.load(open(SEL, encoding="utf-8"))["scenarios"]
    t0 = time.time()
    cfg = dict(model=MODEL, requested_model=REQUESTED_MODEL, backend="deepseek",
               base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
               temperature=0.0, max_concurrent=MAX_CONCURRENT, max_retries=1,
               request_timeout_s=60, guard_device=os.environ.get("PROBE_GUARD_DEVICE", "cuda"),
               price_in_usd_per_mtok=PRICE_IN * 1e6, price_out_usd_per_mtok=PRICE_OUT * 1e6,
               fuse_multiplier=FUSE_MULT, max_cost_usd=MAX_COST_USD,
               model_returned=None, key_source=_src,
               started=time.strftime("%Y-%m-%d %H:%M:%S"))
    json.dump(cfg, open(os.path.join(OUT, "run_config.json"), "w"), ensure_ascii=False, indent=2)

    for arm in ("E0", "M1"):
        if _state["stop"]:
            break
        print("=== arm %s ===" % arm, flush=True)
        run_arm(sel, arm)

    cfg["model_returned"] = _model_returned
    cfg["cost_usd_est"] = round(_state["cost"], 4)
    cfg["wall_time_min"] = round((time.time() - t0) / 60, 1)
    cfg["blocked"] = _state["stop"]
    json.dump(cfg, open(os.path.join(OUT, "run_config.json"), "w"), ensure_ascii=False, indent=2)
    print("[done] cost=$%.3f wall=%.1fmin blocked=%s"
          % (_state["cost"], cfg["wall_time_min"], _state["stop"]))


if __name__ == "__main__":
    raise SystemExit(main())
