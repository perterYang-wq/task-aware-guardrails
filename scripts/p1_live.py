# -*- coding: utf-8 -*-
"""P1 实时看板（只读，CPU，不碰 GPU）

只读数据源：/tmp/p1_main.log、results/p1/logs/*.log、train_*.json。
"""
import glob
import os
import re
import subprocess
import time

ROOT = "/data/projects/guardrails"
LOGD = os.path.join(ROOT, "results", "p1", "logs")
MAIN = "/tmp/p1_main.log"

STAGE_A = ["p1_%s_%s_%s_s0" % (m, arm, lr)
           for m in ("15b", "3b") for lr in ("l1", "l2") for arm in ("task", "nt")]

RE_DONE = re.compile(r"\[done \]\s+(\S+)\s+best=(\d+)\s+val=([0-9.]+)\s+(\d+)s")
RE_FAIL = re.compile(r"\[FAIL \]\s+(\S+)\s+rc=(\d+)")
RE_EP = re.compile(r"^\s*ep(\d+) (\d+)/(\d+) loss=([0-9.]+)\s+(\d+)s", re.M)
RE_VAL = re.compile(r"\[ep(\d+) val\] n=\d+\s+acc=([0-9.]+)\s+macro-F1=([0-9.]+)")


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout


def tail_text(p):
    return open(p, encoding="utf-8", errors="replace").read() if os.path.exists(p) else ""


def main():
    ml = tail_text(MAIN)
    done = {}
    for m in RE_DONE.finditer(ml):
        done[m.group(1)] = {"best": int(m.group(2)), "val": float(m.group(3)),
                            "sec": int(m.group(4))}
    fails = {m.group(1): int(m.group(2)) for m in RE_FAIL.finditer(ml)}
    lr_choice = {}
    for line in ml.splitlines():
        m = re.match(r"\[LR\]\s+(\S+)\s+->\s+(\S+)\s+\(lr=([0-9.e-]+)\)", line)
        if m:
            lr_choice[m.group(1)] = (m.group(2), float(m.group(3)))
    p1done = "P1_DONE" in ml

    cur = cur_el = None
    for line in sh("ps -eo pid,etime,args | grep '[t]rain_lora.py' | grep -v grep").splitlines():
        m = re.search(r"--tag (\S+)", line)
        if m:
            cur, cur_el = m.group(1), line.split()[1]
    cur_eval = None
    for line in sh("ps -eo pid,etime,args | grep '[r]un_guard.py' | grep -v grep").splitlines():
        m = re.search(r"--tag (\S+)", line)
        if m:
            cur_eval = m.group(1)

    eps, vals, loss, step, total = [], [], None, 0, 191
    if cur:
        t = tail_text(os.path.join(LOGD, "%s.log" % cur))
        eps = RE_EP.findall(t)
        vals = RE_VAL.findall(t)
        if eps:
            e = eps[-1]
            step, total, loss = int(e[1]), int(e[2]), float(e[3])
        else:
            step, total = 0, 191

    def avg(tag):
        v = [d["sec"] for k, d in done.items() if "_%s_" % tag in k]
        return sum(v) / len(v) if v else None

    a15, a3 = avg("15b"), avg("3b")
    # Stage B 的 tag 依赖 lr 选择；未定前用 "?" 占位显示
    plan = list(STAGE_A)
    for m in ("15b", "3b"):
        lk = lr_choice.get(m, ("?", None))[0]
        for arm in ("task", "nt"):
            for sd in (42, 123):
                plan.append("p1_%s_%s_%s_s%d" % (m, arm, lk, sd))
    if cur and cur not in plan:
        plan.append(cur)
    rest = [t for t in plan if t not in done and t != cur]
    rest_sec = sum(((a3 if "_3b_" in t else a15) or 1500) for t in rest)

    out = []
    A = out.append
    A("时间 %s" % time.strftime("%m-%d %H:%M:%S"))
    A("训练完成 %d/16   测试评估 %d/12   %s"
      % (len(done), len(glob.glob(os.path.join(ROOT, "results", "p1", "preds", "*.jsonl"))),
         "P1_DONE" if p1done else ""))
    if lr_choice:
        A("lr 选择：%s" % "   ".join("%s → %s (%g)" % (k, v[0], v[1])
                                     for k, v in sorted(lr_choice.items())))
    A("")
    A("%-24s %-9s %-8s %-7s %s" % ("run", "best_ep", "val_F1", "耗时", "状态"))
    A("-" * 68)
    for t in plan:
        if t in done:
            d = done[t]
            A("%-24s ep%-7d %.4f   %5ds   done" % (t, d["best"], d["val"], d["sec"]))
        elif t == cur:
            fra = "ep%d %d%%" % (len(set(x[0] for x in eps)) or 1,
                                 int(100 * step / total)) if eps else "启动中"
            A("%-24s %-9s %-8s %-7s 训练中 %s | %s" % (t, "-", "-", cur_el, fra,
                                                       "" if loss is None else "loss=%.4f" % loss))
        elif t in fails:
            A("%-24s rc=%d" % (t, fails[t]))
        else:
            A("%-24s %-9s %-8s %-7s 排队" % (t, "-", "-", "-"))
    A("")
    if cur:
        A("当前 run：%s（已跑 %s）" % (cur, cur_el))
        if vals:
            A("  已完成 epoch 的 val：%s" % "  ".join(
                "ep%s acc=%s F1=%s" % (a, b, c) for a, b, c in vals))
        if eps:
            A("  当前 epoch %d/%d 步（最近 %.0fs/100 步，loss=%.4f）"
              % (step, total, float(eps[-1][4]), loss))
    if cur_eval:
        A("当前在跑测试评估：%s" % cur_eval)
    A("")
    A("平均耗时：15B %.0fs（%.1f min）/ 3B %.0fs（%.1f min）"
      % (a15 or 0, (a15 or 0) / 60, a3 or 0, (a3 or 0) / 60))
    # 当前 run 的剩余时间
    cur_left = 0.0
    if cur:
        base = a3 if "_3b_" in cur else a15
        if base and eps:
            frac = max(0.0, 1.0 - (len(set(x[0] for x in eps)) - 1 + step / total) / 4.0)
            cur_left = base * frac
        elif base:
            cur_left = base * 0.5
    eta_train = (rest_sec + cur_left) / 60
    A("剩余训练 %d 个（含当前），估计 %.0f 分钟；之后 12 次测试评估" % (len(rest) + 1, eta_train))
    now = time.time()
    A("预计训练收尾 ≈ %s；含测试评估 ≈ %s"
      % (time.strftime("%H:%M", time.localtime(now + (rest_sec + cur_left))),
         time.strftime("%H:%M", time.localtime(now + (rest_sec + cur_left) + 3600))))
    print("\n".join(out))


if __name__ == "__main__":
    main()
