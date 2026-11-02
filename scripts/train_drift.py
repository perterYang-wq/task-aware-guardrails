# -*- coding: utf-8 -*-
"""M1/M2 训练器：在标准授权 SFT 上加「攻击轨迹 hard negative」与「成对偏好」两项。

三个臂（同一份代码路径，只改开关）
--------------------------------
    S  : 只用 PAB-RD                    （= 标准授权 SFT，同协议重训）
    D  : PAB-RD + hard negative         （M2：数据对齐）
    DP : PAB-RD + hard negative + 偏好  （M1：目标对齐，与 D 的差就是目标本身的贡献）

偏好项的定义
------------
对同一 (用户目标, 污染历史) 下的两个调用——攻击调用 a 与同工具干净替代 c——
要求 s(a) − s(c) ≥ margin，其中 s ∈ [0,1] 是**期望档位**：
    s = Σ_c P(c) · rating_c,  c ∈ {"0.0","0.5","1.0"}, rating ∈ {0,0.5,1}
P(c) 用答案前缀的联合概率算，一次前向即可拿到（三个答案共享 "0." 前缀，
"1.0" 的第二个 token 近似用 "0." 分支，实测该位置几乎确定）。
损失 = CE + λ·relu(margin − (s_neg − s_pos))。

为什么这样写而不是 DPO：档位是**有序三分类**，s 已经是序数标量，
直接做 margin 比对偏好概率更稳，也不需要在策略模型之外再挂一个参考模型。
"""
import argparse
import json
import os
import random
import sys
import time

import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = "/data/projects/guardrails"
sys.path.insert(0, ROOT)
from guard.metrics import evaluate  # noqa: E402
from guard.schema import parse_rating, render_fitted, step_from_dict  # noqa: E402

ANSWER = {"ALLOW": "0.0", "REVIEW": "0.5", "DENY": "1.0"}
RATING = {"0.0": 0.0, "0.5": 0.5, "1.0": 1.0}


def ids_of(tok, s):
    return tok(s, add_special_tokens=False).input_ids


def load_pab(split, data_p, splits_p):
    steps = [step_from_dict(json.loads(l)) for l in open(data_p, encoding="utf-8")]
    by = {s.sid: s for s in steps}
    sp = json.load(open(splits_p))
    sp = sp[split] if split in sp else sp
    return [by[i] for i in sp["train"]], [by[i] for i in sp["val"]]


def load_hardneg(p):
    out = []
    for l in open(p, encoding="utf-8"):
        d = json.loads(l)
        st = step_from_dict(d)
        st.meta.update(d.get("meta") or {})
        out.append(st)
    return out


def build(tok, st, max_len, task_aware, style):
    prompt = render_fitted(tok, st, max_len - 8, style=style, task_aware=task_aware)
    pids = tok.apply_chat_template([{"role": "user", "content": prompt}], tokenize=True,
                                   add_generation_prompt=True, return_dict=False)
    aid = ids_of(tok, ANSWER[st.label]) + [tok.eos_token_id]
    return dict(ids=pids + aid, lab=[-100] * len(pids) + aid, n_prompt=len(pids),
                sid=st.sid, label=st.label,
                pair_id=(st.meta or {}).get("pair_id"),
                kind=(st.meta or {}).get("kind", "pab"))


def collate(batch, pad_id):
    L = max(len(x["ids"]) for x in batch)
    ids, lab, att = [], [], []
    for x in batch:
        pad = L - len(x["ids"])
        ids.append(x["ids"] + [pad_id] * pad)
        lab.append(x["lab"] + [-100] * pad)
        att.append([1] * len(x["ids"]) + [0] * pad)
    return torch.tensor(ids), torch.tensor(lab), torch.tensor(att)


def class_logprobs(logits, lab, pad_id, tok, a0, a1, a2):
    """从 teacher-forcing logits 里取三个档位的近似联合对数概率。

    a0/a1/a2 是 "0.0"/"0.5"/"1.0" 的 token id 列表（各 3 个 token）。
    位置：答案首 token 在 n_prompt-1 的预测上，依次往后。
    这里用最小 token 索引方式统一取：以 batch 内答案起始位置对齐。
    """
    # 答案起始位置 = 第一个非 -100 的位置
    B, T, V = logits.shape
    dev = logits.device
    idx = (lab != -100).float().argmax(dim=1)          # [B] 首个答案位置
    ar = torch.arange(B, device=dev)
    lp = logits.log_softmax(-1)
    p1 = lp[ar, idx - 1]        # 预测答案第 1 个 token
    p2 = lp[ar, idx]            # 第 2 个
    p3 = lp[ar, idx + 1]        # 第 3 个
    t0 = tok.decode([a0[0]])
    t1 = tok.decode([a0[1]])
    l00 = p1[:, a0[0]] + p2[:, a0[1]] + p3[:, a0[2]]
    l05 = p1[:, a0[0]] + p2[:, a0[1]] + p3[:, a1[2]]
    l10 = p1[:, a2[0]] + p2[:, a0[1]] + p3[:, a2[2]]
    return torch.stack([l00, l05, l10], dim=1), (t0, t1)


@torch.no_grad()
def gen_labels(model, tok, steps, max_len, task_aware, style, bs=16):
    model.eval()
    old = tok.padding_side
    tok.padding_side = "left"
    preds = []
    for i in range(0, len(steps), bs):
        texts = [tok.apply_chat_template(
            [{"role": "user", "content": render_fitted(tok, s, max_len - 8, style=style,
                                                       task_aware=task_aware)}],
            tokenize=False, add_generation_prompt=True) for s in steps[i:i + bs]]
        enc = tok(texts, return_tensors="pt", padding=True,
                  add_special_tokens=False).to("cuda")
        out = model.generate(**enc, max_new_tokens=6, do_sample=False, temperature=None,
                             top_p=None, top_k=None, pad_token_id=tok.pad_token_id)
        for t in tok.batch_decode(out[:, enc["input_ids"].shape[1]:], skip_special_tokens=True):
            preds.append(parse_rating(t))
    tok.padding_side = old
    model.train()
    return preds


def build_units(pab_ex, hn_ex, seed):
    """一个 unit = 单样本，或一对 (neg, pos)。保证配对项同批出现。"""
    pairs = {}
    singles = []
    for x in hn_ex:
        if x["pair_id"] and x["label"] == "DENY":
            pairs.setdefault(x["pair_id"], {})["neg"] = x
        elif x["pair_id"] and x["label"] == "ALLOW":
            pairs.setdefault(x["pair_id"], {})["pos"] = x
        else:
            singles.append(x)
    units = [("single", x) for x in pab_ex] + [("single", x) for x in singles]
    for pid, d in pairs.items():
        if "neg" in d and "pos" in d:
            units.append(("pair", d))
        elif "neg" in d:
            units.append(("single", d["neg"]))
    random.Random(seed).shuffle(units)
    return units


def flatten(units):
    out = []
    for t, u in units:
        if t == "pair":
            out += [u["neg"], u["pos"]]
        else:
            out.append(u)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="/data/hf_cache/qwen1.5b")
    ap.add_argument("--split", default="pab")
    ap.add_argument("--data", default=os.path.join(ROOT, "data/pab_rd.jsonl"))
    ap.add_argument("--splits", default=os.path.join(ROOT, "data/pab_rd_splits.json"))
    ap.add_argument("--hardneg", default=os.path.join(ROOT, "data/hardneg.jsonl"))
    ap.add_argument("--use-hardneg", action="store_true")
    ap.add_argument("--hn-noinj", action="store_true",
                    help="额外纳入「剥掉注入载荷」的反事实视图（标签不变）")
    ap.add_argument("--pref", type=float, default=0.0, help="偏好项权重 λ，0 表示关闭")
    ap.add_argument("--margin", type=float, default=0.5)
    ap.add_argument("--max-len", type=int, default=1024)
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--bs", type=int, default=4)
    ap.add_argument("--accum", type=int, default=4)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--style", default="pab")
    ap.add_argument("--no-task", action="store_true",
                    help="抹掉用户请求（任务盲对照臂）")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    torch.manual_seed(a.seed)
    random.seed(a.seed)
    tok = AutoTokenizer.from_pretrained(a.model)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    a0, a1, a2 = ids_of(tok, "0.0"), ids_of(tok, "0.5"), ids_of(tok, "1.0")

    ta = not a.no_task
    tr_s, va_s = load_pab(a.split, a.data, a.splits)
    pab_ex = [build(tok, s, a.max_len, ta, a.style) for s in tr_s]
    hn_ex = []
    if a.use_hardneg:
        hn_s = load_hardneg(a.hardneg)
        if not a.hn_noinj:
            n0 = len(hn_s)
            hn_s = [s for s in hn_s if (s.meta or {}).get("kind") != "hardneg_noinj"]
            print("hardneg: 只用 full 视图 %d/%d 条" % (len(hn_s), n0), flush=True)
        hn_ex = [build(tok, s, a.max_len, ta, a.style) for s in hn_s]
    if a.limit:
        pab_ex, hn_ex = pab_ex[:a.limit], hn_ex[:max(8, a.limit // 4)]
    units = build_units(pab_ex, hn_ex, a.seed)
    n_pair = sum(1 for t, _ in units if t == "pair")
    L = [len(x["ids"]) for x in flatten(units)]
    print("tag=%s pab=%d hn=%d units=%d pairs=%d tokens mean=%.0f max=%d"
          % (a.tag, len(pab_ex), len(hn_ex), len(units), n_pair,
             sum(L) / len(L), max(L)), flush=True)

    model = AutoModelForCausalLM.from_pretrained(a.model, torch_dtype=torch.float16,
                                                 device_map="cuda")
    model.config.use_cache = False
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    from peft import LoraConfig, get_peft_model
    model = get_peft_model(model, LoraConfig(
        r=a.lora_r, lora_alpha=32, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"]))
    model.print_trainable_parameters()
    model.train()

    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],
                            lr=a.lr, weight_decay=0.0)
    nb = len(units) // a.bs + 1
    sched = torch.optim.lr_scheduler.OneCycleLR(
        opt, max_lr=a.lr, total_steps=nb * a.epochs, pct_start=0.05)

    def fwd(exs, need_lp=False):
        ids, lab, att = collate(exs, tok.pad_token_id)
        ids, lab, att = ids.to("cuda"), lab.to("cuda"), att.to("cuda")
        out = model(input_ids=ids, attention_mask=att, labels=lab)
        if not need_lp:
            return out.loss, None, len(exs)
        lp, _ = class_logprobs(out.logits, lab, tok.pad_token_id, tok, a0, a1, a2)
        return out.loss, lp, len(exs)

    best_f1, best_ep, hist = -1.0, -1, []
    for ep in range(1, a.epochs + 1):
        idx = list(range(len(units)))
        random.Random(a.seed * 100 + ep).shuffle(idx)
        run_sft = run_pref = 0.0
        nstep = npref = 0
        t1 = time.time()
        opt.zero_grad()
        for k in range(0, len(idx), a.bs):
            chunk = [units[i] for i in idx[k:k + a.bs]]
            # ---- 配对项单独算 margin（需要两次前向）
            pair_loss = None
            if a.pref > 0:
                ps = [u for t, u in chunk if t == "pair"]
                if ps:
                    for d in ps:
                        _, lp_n, _ = fwd([d["neg"]], True)
                        _, lp_p, _ = fwd([d["pos"]], True)
                        rv = torch.tensor([0.0, 0.5, 1.0], device=lp_n.device,
                                          dtype=lp_n.dtype)   # 必须跟随 logits 的 dtype
                        p_n = lp_n.log_softmax(-1).exp() @ rv
                        p_p = lp_p.log_softmax(-1).exp() @ rv
                        l = F.relu(a.margin - (p_n - p_p)).float()
                        pair_loss = l if pair_loss is None else pair_loss + l
                    pair_loss = pair_loss / len(ps)
                    run_pref += float(pair_loss)
                    npref += 1
            # ---- SFT 项
            exs = []
            for t, u in chunk:
                exs += ([u["neg"], u["pos"]] if t == "pair" else [u])
            loss, _, n = fwd(exs)
            run_sft += float(loss) * n
            nstep += n
            total = loss
            if pair_loss is not None:
                total = total + a.pref * pair_loss
            (total / a.accum).backward()
            if (k // a.bs + 1) % a.accum == 0:
                torch.nn.utils.clip_grad_norm_(
                    [p for p in model.parameters() if p.requires_grad], 1.0)
                opt.step()
                sched.step()
                opt.zero_grad()
            if (k // a.bs + 1) % 40 == 0:
                print("  ep%d %d/%d ce=%.4f pref=%s %.0fs"
                      % (ep, k // a.bs + 1, nb, run_sft / max(nstep, 1),
                         ("%.4f" % (run_pref / max(npref, 1))) if a.pref > 0 else "-",
                         time.time() - t1), flush=True)
        vp = gen_labels(model, tok, va_s, a.max_len, ta, a.style)
        vres = evaluate([s.label for s in va_s], vp, "ep%d" % ep)
        hist.append(dict(epoch=ep, ce=run_sft / max(nstep, 1),
                         pref=(run_pref / max(npref, 1)) if a.pref > 0 else None,
                         val_macro_f1=vres["macro_f1"], val_acc=vres["acc"]))
        print("  [val ep%d] macro-F1=%.4f acc=%.4f" % (ep, vres["macro_f1"], vres["acc"]),
              flush=True)
        if vres["macro_f1"] > best_f1:
            best_f1, best_ep = vres["macro_f1"], ep
            model.save_pretrained(os.path.join(ROOT, "guard/adapters", a.tag))
            print("  saved ep%d f1=%.4f" % (ep, best_f1), flush=True)

    json.dump(dict(tag=a.tag, task_aware=ta, best_epoch=best_ep,
                  best_val_macro_f1=best_f1, hist=hist,
                   n_units=len(units), n_pairs=n_pair, n_pab=len(pab_ex), n_hn=len(hn_ex),
                   args=vars(a)),
              open(os.path.join(ROOT, "results/train_%s.json" % a.tag), "w"),
              ensure_ascii=False, indent=1)
    print("best=%d f1=%.4f -> guard/adapters/%s" % (best_ep, best_f1, a.tag))


if __name__ == "__main__":
    main()
