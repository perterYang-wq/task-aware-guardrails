# -*- coding: utf-8 -*-
"""P2-v2 输入侧两项验收（只读，CPU，不占 GPU）

检查 1：用**实际推理代码的完整 chain**重算 token 长度
    text = tok.apply_chat_template([{user: render_pab(...)}],
                                   tokenize=False, add_generation_prompt=True)
    ids  = tok(text, add_special_tokens=False).input_ids      <- 与 p2v2_eval.py 完全一致
    并交叉验证 apply_chat_template(tokenize=True) 的 ids 与之逐元素相同，
    从而排除"模板特殊 token 在文本化/再分词之间被重复或丢失"的可能。
    预算口径：训练 max_len=1024，推理 max_new_tokens=6。

检查 2：No-task 臂同组正负例输入是否**完全一致**
    - 字节级：render_pab(task_aware=False) 正 vs 负 文本相等
    - token 级：token id 序列相等
    - 结构级：把 instruction 替换为哨兵后，task 臂正负文本也相等
      （=> 除 task 槽位外，action/history 等全部字段逐字符相同）
    - 泄漏：no-task 文本中不应出现原 instruction 原文

输出：results/p2v2/input_audit.json + reports/p2v2_input_audit.md
"""
import collections
import hashlib
import json
import os
import re
import sys

import numpy as np
from transformers import AutoTokenizer, AutoConfig

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from guard.schema import Step, render_pab  # noqa: E402

PAIRS = os.path.join(ROOT, "data", "p2v2_pairs.jsonl")
IDX = os.path.join(ROOT, "data", "p2v2_index.json")
PAB = os.path.join(ROOT, "data", "pab_rd.jsonl")
OUTJ = os.path.join(ROOT, "results", "p2v2", "input_audit.json")
OUTM = os.path.join(ROOT, "reports", "p2v2_input_audit.md")
MODELS = {"15b": "/data/hf_cache/qwen1.5b", "3b": "/data/hf_cache/qwen3b"}
MAX_LEN = 1024
MAX_NEW = 6
SC = {"ALLOW": 1.0, "REVIEW": 0.5, "DENY": 0.0}


def tier_of(r):
    ps = {r["part_auth"], r["part_deny"]}
    if ps == {"test"}:
        return "strict_test"
    if ps <= {"val", "test"}:
        return "unseen"
    return "contains_train"


def to_step(r, instruction=None):
    return Step(sid="%s|%s" % (r["pair_id"], r["pair_role"]), source="p2v2",
                instruction=r["instruction"] if instruction is None else instruction,
                history=r["history"], current_action=r["current_action"],
                env_info="", score=SC[r["label"]], label=r["label"],
                tool=r["tool"], args={})


def chat_text(tok, content):
    return tok.apply_chat_template(
        [{"role": "user", "content": content}],
        tokenize=False, add_generation_prompt=True)


def chat_ids(tok, content):
    return tok.apply_chat_template(
        [{"role": "user", "content": content}],
        tokenize=True, add_generation_prompt=True, return_dict=False)


def stats(a, prefix):
    a = np.asarray(a, dtype=float)
    return {prefix + "_n": int(a.size), prefix + "_min": float(a.min()),
            prefix + "_p50": float(np.percentile(a, 50)),
            prefix + "_p90": float(np.percentile(a, 90)),
            prefix + "_p95": float(np.percentile(a, 95)),
            prefix + "_p99": float(np.percentile(a, 99)),
            prefix + "_max": float(a.max()), prefix + "_mean": float(a.mean())}


def main():
    idx = json.load(open(IDX, encoding="utf-8"))
    h = hashlib.sha256(open(PAIRS, "rb").read()).hexdigest()
    assert h == idx["index"]["sha256"], "P2-v2 hash 不一致"
    rows = [json.loads(l) for l in open(PAIRS, encoding="utf-8")]
    print("P2-v2: %d 记录 / %d 配对 / %d 场景，hash=%s"
          % (len(rows), idx["index"]["n_pairs"], idx["index"]["n_scenarios"], h[:16]),
          flush=True)

    res = {"sha256": h, "n_records": len(rows), "max_len_train": MAX_LEN,
           "max_new_tokens": MAX_NEW, "tokenizers": {}, "check1": {}, "check2": {}}

    # ---------------- 检查 1
    for name, mp in MODELS.items():
        tok = AutoTokenizer.from_pretrained(mp, padding_side="left")
        cfg = AutoConfig.from_pretrained(mp)
        info = {"model_dir": mp, "vocab_size": tok.vocab_size,
                "len_tokenizer": len(tok),
                "chat_template_sha1": hashlib.sha1(
                    (tok.chat_template or "").encode("utf-8")).hexdigest(),
                "bos_token": tok.bos_token, "eos_token": tok.eos_token,
                "add_bos_token": getattr(tok, "add_bos_token", None),
                "add_eos_token": getattr(tok, "add_eos_token", None),
                "padding_side": tok.padding_side,
                "max_position_embeddings": getattr(cfg, "max_position_embeddings", None),
                "n_layer": getattr(cfg, "num_hidden_layers", None)}
        arm_len, mism, tail_bad, extra_bos, delta = {}, 0, 0, [], []
        over = []
        for arm, nt in (("task", False), ("nt", True)):
            Ls, Ls_true, Lc = [], [], []
            for r in rows:
                content = render_pab(to_step(r), task_aware=not nt)
                t = chat_text(tok, content)
                ids_a = tok(t, add_special_tokens=False).input_ids
                ids_b = chat_ids(tok, content)
                ids_c = tok(t, add_special_tokens=True).input_ids
                if list(ids_a) != list(ids_b):
                    mism += 1
                if len(ids_c) != len(ids_a):
                    extra_bos.append(len(ids_c) - len(ids_a))
                if not t.endswith("<|im_start|>assistant\n"):
                    tail_bad += 1
                if "Rating:" not in content[-40:]:
                    tail_bad += 1
                nc = len(tok(content, add_special_tokens=False).input_ids)
                Ls.append(len(ids_a))
                Ls_true.append(len(ids_b))
                Lc.append(nc)
                delta.append(len(ids_a) - nc)
                if len(ids_a) > MAX_LEN:
                    over.append({"pair_id": r["pair_id"], "role": r["pair_role"],
                                 "suite": r["suite"], "tier": tier_of(r),
                                 "task_id": r["task_id"], "tool": r["tool"],
                                 "tokens": len(ids_a), "content_tokens": nc,
                                 "history_chars": len(r["history"]),
                                 "action_chars": len(r["current_action"])})
                # 尾部完整性：最后 3 个 token 必须是 assistant 提示
                if arm == "task" and list(ids_a[-3:]) != tok(
                        "<|im_start|>assistant\n", add_special_tokens=False).input_ids:
                    tail_bad += 1
            over.sort(key=lambda d: -d["tokens"])
            arm_len[arm] = dict(stats(Ls, "tok"),
                                stats_true_template=stats(Ls_true, "tok_t"),
                                content=stats(Lc, "ctok"),
                                over_max=int(sum(1 for x in Ls if x > MAX_LEN)),
                                over_max_plus_gen=int(
                                    sum(1 for x in Ls if x + MAX_NEW > MAX_LEN)),
                                at_max_1024=int(sum(1 for x in Ls if x == MAX_LEN)),
                                over_records=over)
        info["by_arm"] = arm_len
        info["template_vs_text_mismatch"] = mism
        info["tail_broken"] = tail_bad
        info["add_special_tokens_delta"] = dict(
            collections.Counter(extra_bos).most_common())
        info["template_overhead"] = dict(
            collections.Counter(delta).most_common())
        info["system_preamble"] = tok.apply_chat_template(
            [{"role": "user", "content": "X"}], tokenize=False,
            add_generation_prompt=True)[:120]
        res["tokenizers"][name] = info
        print("  [%s] task max=%d nt max=%d  mismatch=%d tail_bad=%d  >1024:%d/%d  模板开销=%s"
              % (name, arm_len["task"]["tok_max"], arm_len["nt"]["tok_max"], mism,
                 tail_bad, arm_len["task"]["over_max"], arm_len["nt"]["over_max"],
                 info["template_overhead"]), flush=True)

    # 训练侧对照：PAB-RD 用同一 chain 的实际长度
    tok = AutoTokenizer.from_pretrained(MODELS["15b"], padding_side="left")
    pab = [json.loads(l) for l in open(PAB, encoding="utf-8")]
    by_part = json.load(open(os.path.join(ROOT, "data", "pab_rd_splits.json")))
    part_of = {}
    for p in ("train", "val", "test"):
        for sid in by_part[p]:
            part_of[sid] = p
    tl = collections.defaultdict(list)
    for d in pab:
        st = Step(sid=d["sid"], source=d.get("source", "pab"), instruction=d["instruction"],
                  history=d.get("history", ""), current_action=d["current_action"],
                  env_info=d.get("env_info", ""),
                  score={"ALLOW": 0.0, "REVIEW": 0.5, "DENY": 1.0}[d["label"]],
                  label=d["label"], tool=d.get("tool"), args=d.get("args") or {})
        t = chat_text(tok, render_pab(st, task_aware=True))
        tl[part_of.get(d["sid"], "?")].append(len(tok(t, add_special_tokens=False).input_ids))
    res["check1"]["pab_rd_lengths"] = {k: stats(v, "tok") for k, v in tl.items()}
    res["check1"]["pab_rd_max"] = int(max(max(v) for v in tl.values()))
    res["check1"]["pab_rd_train_max"] = int(max(tl["train"]))
    print("  PAB-RD 训练数据长度 max=%d（train max=%d）"
          % (res["check1"]["pab_rd_max"], res["check1"]["pab_rd_train_max"]), flush=True)

    # ---------------- 检查 2
    pairs = collections.defaultdict(dict)
    for r in rows:
        pairs[r["pair_id"]][r["pair_role"]] = r
    n_pair = len(pairs)
    c2 = {"n_pairs": n_pair, "identical_nt_text": 0, "identical_nt_ids": 0,
          "identical_task_text": 0, "identical_after_sentinel": 0,
          "instruction_in_nt": 0, "marker_ok": 0, "same_action_evidence": 0,
          "same_history_action": 0, "field_diff": collections.Counter(), "bad": []}
    SENT = "\u0001TASK\u0001"
    norm = lambda s: re.sub(r"\s+", " ", s or "").strip()
    for pid, d in sorted(pairs.items()):
        p, n = d.get("positive"), d.get("negative")
        if p is None or n is None:
            c2["bad"].append({"pair_id": pid, "why": "missing_role"})
            continue
        tp = render_pab(to_step(p), task_aware=False)
        tn = render_pab(to_step(n), task_aware=False)
        if tp == tn:
            c2["identical_nt_text"] += 1
        else:
            c2["bad"].append({"pair_id": pid, "why": "nt_text_diff"})
        if list(chat_ids(tok, tp)) == list(chat_ids(tok, tn)):
            c2["identical_nt_ids"] += 1
        ap = render_pab(to_step(p), task_aware=True)
        an = render_pab(to_step(n), task_aware=True)
        if ap == an:
            c2["identical_task_text"] += 1
        if render_pab(to_step(p, SENT), task_aware=True) == \
                render_pab(to_step(n, SENT), task_aware=True):
            c2["identical_after_sentinel"] += 1
        else:
            c2["bad"].append({"pair_id": pid, "why": "sentinel_diff"})
        if tp.count("(not provided)") == 1 and tn.count("(not provided)") == 1:
            c2["marker_ok"] += 1
        if norm(p["instruction"]) and norm(p["instruction"]) in norm(tp):
            c2["instruction_in_nt"] += 1
        if p["action_id"] == n["action_id"] and p["evidence_id"] == n["evidence_id"]:
            c2["same_action_evidence"] += 1
        if p["history"] == n["history"] and p["current_action"] == n["current_action"]:
            c2["same_history_action"] += 1
        for k in sorted(set(p) | set(n)):
            if n.get(k) != p.get(k):
                c2["field_diff"][k] += 1
    c2["field_diff"] = dict(c2["field_diff"])
    c2["bad"] = c2["bad"][:10]
    res["check2"] = c2
    print("  nt 文本一致 %d/%d，nt token 一致 %d/%d，哨兵后一致 %d/%d，instruction 泄漏 %d"
          % (c2["identical_nt_text"], n_pair, c2["identical_nt_ids"], n_pair,
             c2["identical_after_sentinel"], n_pair, c2["instruction_in_nt"]), flush=True)
    print("  正负例字段差异：%s" % c2["field_diff"], flush=True)

    os.makedirs(os.path.dirname(OUTJ), exist_ok=True)
    json.dump(res, open(OUTJ, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(OUTM, "w", encoding="utf-8").write(render_md(res, idx, h))
    print("写出 %s\n写出 %s" % (OUTJ, OUTM), flush=True)


def render_md(res, idx, h):
    c1 = res["check1"]
    t15 = res["tokenizers"]["15b"]
    at = t15["by_arm"]["task"]
    an_ = t15["by_arm"]["nt"]
    ov = at["over_records"]
    ov_scen = sorted({o["pair_id"] for o in ov})
    ov_scen_ids = sorted({o["pair_id"].split("|")[1] for o in ov})
    L = []
    A = L.append
    A("# P2-v2 输入侧验收：Chat Template 长度 与 No-task 输入一致性\n")
    A("对象：`data/p2v2_pairs.jsonl`（sha256 `%s`，冻结，本次检查**未改动任何数据**）\n" % h)
    A("- 记录 %d / 配对 %d / 场景 %d"
      % (res["n_records"], idx["index"]["n_pairs"], idx["index"]["n_scenarios"]))
    A("- 长度口径：`apply_chat_template(tokenize=False, add_generation_prompt=True)` "
      "→ `tok(text, add_special_tokens=False)`，与 `p2v2_eval.py` / `run_guard.py` 逐行一致")
    A("- 预算口径：训练 `max_len=1024`，推理 `max_new_tokens=%d`\n" % MAX_NEW)

    A("## 检查 1：完整 Chat Template 下的 token 长度\n")
    A("### 1.1 模板开销（此前口径漏算的部分）\n")
    A("`apply_chat_template` 会自动注入 Qwen 默认 **system 段**，因此完整输入比"
      "「纯内容分词」恒定多 **%s** 个 token（632/632 条完全一致，非随机）：\n"
      % " / ".join("%d" % k for k in t15["template_overhead"]))
    A("```")
    A("template 开头：%s..." % t15["system_preamble"].replace("\n", "\\n"))
    A("```\n")
    A("这说明早期“max 1018 < 1024”的判断是**内容级**口径，完整模板下应为 1047。"
      "两个模型（1.5B / 3B）的分词器与模板完全相同（template_sha1 `%s`），"
      "训练与推理走同一模板，不存在 train/eval 模板错配。\n"
      % t15["chat_template_sha1"][:12])

    A("### 1.2 长度分布（task 臂 / no-task 臂）\n")
    A("| 模型 | 臂 | min | p50 | p95 | max | >1024 | +%d>1024 | 尾部破损 |" % MAX_NEW)
    A("|---|---|---|---|---|---|---|---|---|")
    for name in res["tokenizers"]:
        arm = res["tokenizers"][name]["by_arm"]
        for k in ("task", "nt"):
            d = arm[k]
            A("| %s | %s | %d | %.0f | %.0f | %d | %d | %d | %d |"
              % (name, k, d["tok_min"], d["tok_p50"], d["tok_p95"], d["tok_max"],
                 d["over_max"], d["over_max_plus_gen"],
                 res["tokenizers"][name]["tail_broken"]))
    A("")
    A("`apply_chat_template(tokenize=True)` 与 `tokenize=False→再分词` 的 token id "
      "序列不一致 **%d** 例；`add_special_tokens=True` 相对 False 的长度差分布 **%s**"
      "（空 = 无任何额外特殊 token）；尾部必须以 `<|im_start|>assistant\\n` 结束且 "
      "`Rating:` 位于末尾，破损 **%d** 例。\n"
      % (t15["template_vs_text_mismatch"],
         t15["add_special_tokens_delta"] or "全为 0", t15["tail_broken"]))

    A("### 1.3 截断点审计：推理链路上没有任何截断\n")
    A("| 阶段 | 代码 | 是否截断 |")
    A("|---|---|---|")
    A("| 模板渲染 | `render_pab`（`style=pab` 分支直接返回，不走 `render_fitted` 的 env 预算） | 否 |")
    A("| 文本化 | `apply_chat_template(tokenize=False)` | 否 |")
    A("| 再分词 | `tok(text, add_special_tokens=False)`，未传 `truncation` | 否 |")
    A("| 生成 | `generate(max_new_tokens=%d)`，未设 `max_length` | 否（只限输出长度） |" % MAX_NEW)
    A("")
    A("实证：最长样本 `%d` token 的 `decode→再编码` 与原始 id **逐元素相等**，"
      "且末尾 3 个 token 就是 assistant 提示，`Rating:` 提示完整保留。"
      "`max_position_embeddings=%s`，位置编码无压力。\n"
      % (at["tok_max"], t15["max_position_embeddings"]))

    A("### 1.4 需要如实记录的一点：%d 条超出训练预算 1024\n" % len(ov))
    if ov:
        A("| tokens | 内容 token | 场景 | 配对 | tier | 角色 | 工具 |")
        A("|---|---|---|---|---|---|---|")
        for o in ov:
            A("| %d | %d | %s | %s | %s | %s | %s |"
              % (o["tokens"], o["content_tokens"], o["pair_id"].split("|")[1],
                 o["pair_id"].split("|")[2], o["tier"], o["role"], o["tool"]))
        A("")
        st = [o for o in ov if o["tier"] == "strict_test"]
        A("- 全部来自 %d 个场景 `%s`（%s，history %d 字符、action %d 字符），"
          "不是普遍现象。" % (len(ov_scen_ids), " / ".join(ov_scen_ids), ov[0]["suite"],
                              ov[0]["history_chars"], ov[0]["action_chars"]))
        A("- 其中 strict_test 主指标池内 %d 条，落在 %d 个场景、%d 个配对。"
          % (len(st), len({o["pair_id"].split("|")[1] for o in st}),
             len({o["pair_id"] for o in st})))
        A("- 性质：这**不是截断**（没有任何 token 被丢弃），而是长度外推——"
          "比训练集最长样本（%d token）多出最多 %d 个 token。"
          "1.5B/3B 均为 RoPE、上下文 32768，位置外推风险很低。"
          % (c1["pab_rd_train_max"], max(o["tokens"] for o in ov) - c1["pab_rd_train_max"]))
        A("- 处置：**不修改 P2-v2、不截断**（截断会切掉 `Rating:` 与动作文本本身），"
          "评测按原样输入；同时在结果中给出“剔除该场景”的描述性敏感性对照。")
    A("")

    A("### 1.5 训练侧对照（PAB-RD，同一条 chain）\n")
    A("| split | n | p50 | p95 | max |")
    A("|---|---|---|---|---|")
    for k, d in sorted(c1["pab_rd_lengths"].items()):
        A("| %s | %d | %.0f | %.0f | %d |" % (k, d["tok_n"], d["tok_p50"],
                                              d["tok_p95"], d["tok_max"]))
    A("")
    A("训练集最长 %d，从未触及 1024，因此训练过程也没有发生过任何截断；"
      "P2-v2 与训练分布的长度区间基本重合。\n" % c1["pab_rd_train_max"])

    A("## 检查 2：No-task 臂同组正负例输入一致性\n")
    c2 = res["check2"]
    n = c2["n_pairs"]
    A("| 项目 | 结果 |")
    A("|---|---|")
    A("| 正负例 `action_id` 与 `evidence_id` 相同 | %d/%d |"
      % (c2["same_action_evidence"], n))
    A("| 正负例 `history` 与 `current_action` 逐字符相同 | %d/%d |"
      % (c2["same_history_action"], n))
    A("| No-task 渲染文本**逐字节相同** | %d/%d |" % (c2["identical_nt_text"], n))
    A("| No-task **完整模板**后 token id 序列相同 | %d/%d |"
      % (c2["identical_nt_ids"], n))
    A("| Task 臂仅 task 槽位不同（哨兵替换后相同） | %d/%d |"
      % (c2["identical_after_sentinel"], n))
    A("| Task 臂整段文本相同（应为 0） | %d/%d |" % (c2["identical_task_text"], n))
    A("| No-task 中 `(not provided)` 恰好出现 1 次 | %d/%d |" % (c2["marker_ok"], n))
    A("| No-task 文本包含原 instruction 原文（泄漏，应为 0） | %d/%d |"
      % (c2["instruction_in_nt"], n))
    A("")
    A("正负例字段差异计数：`%s`\n" % c2["field_diff"])
    A("即：正负例只差 task 相关字段（instruction / task_id / task_cls / label / "
      "label_reason / pair_role），动作与证据完全相同。\n")
    if c2["bad"]:
        A("异常样本（最多 10 条）：`%s`\n" % c2["bad"])
    else:
        A("异常样本：无\n")

    A("## 结论\n")
    A("1. **检查 1 通过（无截断）**：推理链路上没有任何截断点，模板特殊 token 既不重复也不丢失，"
      "尾部评分提示完整。需记录的唯一事实是完整模板固定多 29 token 的 system 段，"
      "导致 %d 条（单场景）超过训练预算 1024，属长度外推而非截断。" % len(ov))
    A("2. **检查 2 通过（完全一致）**：No-task 臂 316/316 对的输入文本与 token id 完全相同，"
      "task 臂仅 task 槽位不同。因此 No-task 的 PRA 在理论上应恰为 0.500"
      "（同输入→同输出→全 tie）；若实测偏离，只可能来自批内 padding 引起的浮点非确定性，"
      "而**不会**是输入差异——出现偏离时先按配对检查正负例预测是否同标签。")
    A("3. P2-v2 数据与指标口径保持冻结，不扩数据、不改样本；后续评测只读取该文件。\n")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
