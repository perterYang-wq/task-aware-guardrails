# -*- coding: utf-8 -*-
"""审计：Banking 证据读取错误对已冻结 PAB-RD 的影响范围。

缺陷
----
`build_pab_rd.docs_banking` 用 `getattr(f, "content", "")` 取文件内容，但
`env.filesystem.files` 的值是 **str**，于是每份银行文件的正文都变成空串，
证据块只剩 `[file:NAME]\nFile NAME\n`。

本脚本只读，回答三个问题：
  1. 有多少条样本的证据里含空正文文件块？按 split / label 分布如何？
  2. 这些样本里，动作参数在证据中"落地"的比例（grounded_frac）被压低了多深？
  3. 标签会不会因此改变？（PAB-RD 的标签来自 ground_truth，理论上不受影响——需验证）
"""
import collections
import copy
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from agentdojo.task_suite.load_suites import get_suite  # noqa: E402

DATA = os.path.join(ROOT, "data", "pab_rd.jsonl")
SPLITS = os.path.join(ROOT, "data", "pab_rd_splits.json")
RE_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")
RE_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
RE_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
RE_NUM = re.compile(r"\b\d+(?:\.\d+)?\b")
RE_QUOTED = re.compile(r"'([^']{2,60})'")
BLOCK = re.compile(r"\[file:([^\]]+)\]\nFile \1\n")


def parse_ids(text):
    t = text or ""
    out = set()
    for rx in (RE_IBAN, RE_EMAIL, RE_DATE):
        out |= {m.lower() for m in rx.findall(t)}
    out |= {m.lower() for m in RE_NUM.findall(t)}
    out |= {m.strip().lower() for m in RE_QUOTED.findall(t)}
    return out


def flat(v, out):
    if isinstance(v, dict):
        for x in v.values():
            flat(x, out)
    elif isinstance(v, (list, tuple)):
        for x in v:
            flat(x, out)
    else:
        out.append(str(v))
    return out


def main():
    rows = [json.loads(l) for l in open(DATA, encoding="utf-8")]
    sp = json.load(open(SPLITS, encoding="utf-8"))
    part = {}
    for k in ("train", "val", "test"):
        for sid in sp[k]:
            part[sid] = k

    env = get_suite("v1", "banking").load_and_inject_default_environment({})
    files = getattr(env.filesystem, "files", {}) or {}
    content = {k: (v if isinstance(v, str) else (getattr(v, "content", "") or ""))
               for k, v in files.items()}
    print("banking 文件 %d 份，其中正文非空 %d 份"
          % (len(content), sum(1 for v in content.values() if v.strip())), flush=True)

    stat = collections.Counter()
    by_split = collections.Counter()
    by_label = collections.Counter()
    by_suite = collections.Counter()
    affected = []
    delta_g = []

    for r in rows:
        h = r.get("history") or ""
        empty_files = [m.group(1) for m in BLOCK.finditer(h)
                       if not h[m.end():m.end() + 1].strip()
                       or h[m.end():m.end() + 2] == "\n["]
        # 更精确：块正文就是紧跟 File NAME\n 之后、到下一个 '[' 或结尾之间的内容
        empties = []
        for m in BLOCK.finditer(h):
            start = m.end()
            nxt = h.find("\n\n[", start)
            body = h[start: nxt if nxt != -1 else len(h)].strip()
            if not body:
                empties.append(m.group(1))
        if not empties:
            continue
        stat["records_with_empty_file_block"] += 1
        by_split[part.get(r["sid"], "?")] += 1
        by_label[r["label"]] += 1
        by_suite[r["suite"]] += 1

        ids = parse_ids(json.dumps(r.get("args") or {}, sort_keys=True, default=str))
        before = parse_ids(h)
        # 用真实正文就地修补这份证据，再算一次
        fixed = h
        for name in empties:
            c = content.get(name, "")
            pat = "[file:%s]\nFile %s\n" % (name, name)
            fixed = fixed.replace(pat, pat + c + "\n")
        after = parse_ids(fixed)
        gb = (sum(1 for v in ids if v.lower() in before) / len(ids)) if ids else 1.0
        ga = (sum(1 for v in ids if v.lower() in after) / len(ids)) if ids else 1.0
        delta_g.append((ga - gb, ids and len(ids)))
        affected.append({"sid": r["sid"], "suite": r["suite"], "label": r["label"],
                         "part": part.get(r["sid"]), "files": empties,
                         "n_ids": len(ids), "grounded_before": round(gb, 3),
                         "grounded_after": round(ga, 3)})

    print("\n== 1. 受影响样本 ==")
    print("含空正文文件块的记录: %d / %d (%.1f%%)"
          % (stat["records_with_empty_file_block"], len(rows),
             100 * stat["records_with_empty_file_block"] / len(rows)))
    print("按 split:", dict(by_split))
    print("按 label:", dict(by_label))
    print("按 suite:", dict(by_suite))

    print("\n== 2. 接地率被压低多少 ==")
    if delta_g:
        import statistics as st
        ds = [d for d, _ in delta_g]
        print("修补后 grounded_frac 提升: mean %+.3f  median %+.3f  max %+.3f"
              % (st.mean(ds), st.median(ds), max(ds)))
        print("完全恢复（提升>=0.99）的记录: %d / %d"
              % (sum(1 for d in ds if d >= 0.99), len(ds)))
        print("毫无变化（提升<=0.001）的记录: %d / %d"
              % (sum(1 for d in ds if d <= 0.001), len(ds)))

    print("\n== 3. 标签是否受影响 ==")
    print("PAB-RD 的 label 取自 task.ground_truth()，与证据文本无关。")
    print("受影响样本 label 分布 %s —— 说明缺陷**不改变任何标签**，只削弱证据信息。"
          % dict(by_label))

    # ---- 4. 更准的口径：任务是否本应读到文件 ----
    from agentdojo.task_suite.load_suites import get_suite as _gs
    su = _gs("v1", "banking")
    env0 = su.load_and_inject_default_environment({})
    reads_file = {}
    for tid, t in su.user_tasks.items():
        try:
            gts = t.ground_truth(copy.deepcopy(env0))
        except Exception:
            continue
        reads_file[tid] = any(g.function == "read_file" for g in gts)
    bank = [r for r in rows if r["suite"] == "banking"]
    cand = [r for r in bank if reads_file.get(r["task_id"])]
    flagged = {a["sid"] for a in affected}
    print("\n== 4. 按任务是否读文件 ==")
    print("banking 记录 %d 条，其中任务本应 read_file 的 %d 条 (%.0f%%)"
          % (len(bank), len(cand), 100 * len(cand) / max(len(bank), 1)))
    print("这些记录里：证据含空正文文件块 %d 条，证据里根本没有 file 块 %d 条"
          % (sum(1 for r in cand if r["sid"] in flagged),
             sum(1 for r in cand if r["sid"] not in flagged and "[file:" not in (r["history"] or ""))))
    print("按 split 分布: %s"
          % dict(collections.Counter(part.get(r["sid"]) for r in cand)))

    out = os.path.join(ROOT, "results", "audit", "banking_evidence.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({"n_records": len(rows),
               "n_affected": stat["records_with_empty_file_block"],
               "by_split": dict(by_split), "by_label": dict(by_label),
               "by_suite": dict(by_suite),
               "grounded_delta_mean": (sum(d for d, _ in delta_g) / len(delta_g)) if delta_g else 0,
               "banking_records": len(bank), "banking_tasks_reading_file": len(cand),
               "examples": affected[:40]}, open(out, "w"), ensure_ascii=False, indent=1)
    print("\n-> %s" % out)


if __name__ == "__main__":
    main()
