# -*- coding: utf-8 -*-
"""O1：把 Qwen2.5-1.5B-Instruct 用 LoRA 训成 task-aware 三档 guard。

关键设计
--------
1. 训练目标与推理完全一致：输出单 token 档位 "0.0"/"0.5"/"1.0"。
   不用自然语言解释，避免训练/推理格式不一致（B3 官方格式 8% 解析失败就是这个坑）。
2. loss 只算在答案 token 上，prompt 部分全部 -100。
3. prompt 长度用 render_fitted 压缩，只牺牲 env_info，绝不切掉 current_action。
4. --no-task 把 user request 抹成 "(not provided)"，得到 task-blind 对照，
   用来回答"任务信息到底贡献了多少"，而不是只报一个好数字。
5. 每轮在 val 上生成并算 macro-F1，保存最好的一轮。
"""
import argparse
import json
import os
import random
import sys
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from guard.metrics import evaluate  # noqa: E402
from guard.schema import parse_rating, render_fitted, step_from_dict  # noqa: E402

DEFAULT_DATA = os.path.join(ROOT, "data", "tsbench_unified.jsonl")
DEFAULT_SPLITS = os.path.join(ROOT, "data", "splits.json")
ANSWER = {"ALLOW": "0.0", "REVIEW": "0.5", "DENY": "1.0"}


def load_split(name, data_p, splits_p):
    steps = [step_from_dict(json.loads(l)) for l in open(data_p, encoding="utf-8")]
    by = {s.sid: s for s in steps}
    sp = json.load(open(splits_p))
    sp = sp[name] if name in sp else sp   # PAB 的 splits 顶层就是 train/val/test
    return ([by[i] for i in sp["train"]], [by[i] for i in sp["val"]],
            [by[i] for i in sp["test"]])


def build_example(tok, st, max_len, task_aware, style):
    prompt = render_fitted(tok, st, max_len - 8, style=style, task_aware=task_aware)
    pids = tok.apply_chat_template([{"role": "user", "content": prompt}],
                                   tokenize=True, add_generation_prompt=True,
                                   return_dict=False)
    aid = tok(ANSWER[st.label], add_special_tokens=False).input_ids
    aid = aid + [tok.eos_token_id]
    return pids + aid, [-100] * len(pids) + aid


def collate(batch, pad_id):
    L = max(len(x[0]) for x in batch)
    ids, lab, att = [], [], []
    for x, y in batch:
        pad = L - len(x)
        ids.append(x + [pad_id] * pad)
        lab.append(y + [-100] * pad)
        att.append([1] * len(x) + [0] * pad)
    return (torch.tensor(ids), torch.tensor(lab), torch.tensor(att))


@torch.no_grad()
def gen_labels(model, tok, steps, max_len, task_aware, style, bs=16):
    """批量生成必须用左填充。右填充时模型会接着 pad 继续写，输出全乱——
    这正是第一轮 val 报出 92.9% 解析失败的原因（单条生成是正常的）。"""
    model.eval()
    old_side = tok.padding_side
    tok.padding_side = "left"
    preds = []
    for i in range(0, len(steps), bs):
        chunk = steps[i:i + bs]
        texts = [tok.apply_chat_template(
            [{"role": "user", "content": render_fitted(
                tok, s, max_len - 8, style=style, task_aware=task_aware)}],
            tokenize=False, add_generation_prompt=True) for s in chunk]
        enc = tok(texts, return_tensors="pt", padding=True,
                  add_special_tokens=False).to("cuda")
        out = model.generate(**enc, max_new_tokens=6, do_sample=False,
                             temperature=None, top_p=None, top_k=None,
                             pad_token_id=tok.pad_token_id)
        for t in tok.batch_decode(out[:, enc["input_ids"].shape[1]:],
                                  skip_special_tokens=True):
            preds.append(parse_rating(t))
    tok.padding_side = old_side
    model.train()
    return preds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="/data/hf_cache/qwen1.5b")
    ap.add_argument("--split", default="grouped")
    ap.add_argument("--no-task", action="store_true")
    ap.add_argument("--style", default="short", choices=["short", "official", "pab"])
    ap.add_argument("--data", default=DEFAULT_DATA)
    ap.add_argument("--splits", default=DEFAULT_SPLITS)
    ap.add_argument("--max-len", type=int, default=1536)
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--bs", type=int, default=4)
    ap.add_argument("--accum", type=int, default=4)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--lora-alpha", type=int, default=32)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--tag", default="")
    ap.add_argument("--limit", type=int, default=0,
                    help="冒烟用：只取前 N 条训练样本")
    a = ap.parse_args()

    tag = a.tag or ("%s_%s%s_ep%d" % (a.split, "notask" if a.no_task else "task",
                                      "", a.epochs))
    torch.manual_seed(a.seed)
    random.seed(a.seed)
    task_aware = not a.no_task

    tok = AutoTokenizer.from_pretrained(a.model)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    train_s, val_s, test_s = load_split(a.split, a.data, a.splits)
    if a.limit:
        train_s = train_s[:a.limit]
        val_s = val_s[:max(32, a.limit // 4)]
    print("split=%s  train=%d val=%d test=%d  task_aware=%s  max_len=%d"
          % (a.split, len(train_s), len(val_s), len(test_s), task_aware, a.max_len),
          flush=True)

    t0 = time.time()
    examples = [build_example(tok, s, a.max_len, task_aware, a.style) for s in train_s]
    lens = [len(e[0]) for e in examples]
    print("tokenized %d in %.1fs  len: mean=%.0f p95=%d max=%d"
          % (len(examples), time.time() - t0, sum(lens) / len(lens),
             sorted(lens)[int(0.95 * len(lens))], max(lens)), flush=True)

    model = AutoModelForCausalLM.from_pretrained(
        a.model, torch_dtype=torch.float16, device_map="cuda")
    model.config.use_cache = False
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()

    from peft import LoraConfig, get_peft_model
    cfg = LoraConfig(
        r=a.lora_r, lora_alpha=a.lora_alpha, lora_dropout=0.05, bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"])
    model = get_peft_model(model, cfg)
    model.print_trainable_parameters()
    model.train()

    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],
                            lr=a.lr, weight_decay=0.0)
    total_steps = (len(examples) // (a.bs * a.accum) + 1) * a.epochs
    sched = torch.optim.lr_scheduler.OneCycleLR(
        opt, max_lr=a.lr, total_steps=total_steps, pct_start=0.05)

    best_f1, best_ep, hist = -1.0, -1, []
    for ep in range(1, a.epochs + 1):
        idx = list(range(len(examples)))
        random.Random(a.seed + ep).shuffle(idx)
        run, nstep, t1 = 0.0, 0, time.time()
        opt.zero_grad()
        for k in range(0, len(idx), a.bs):
            batch = [examples[i] for i in idx[k:k + a.bs]]
            ids, lab, att = collate(batch, tok.pad_token_id)
            ids, lab, att = ids.to("cuda"), lab.to("cuda"), att.to("cuda")
            out = model(input_ids=ids, attention_mask=att, labels=lab)
            loss = out.loss / a.accum
            loss.backward()
            run += out.loss.item()
            nstep += 1
            if nstep % a.accum == 0:
                torch.nn.utils.clip_grad_norm_(
                    [p for p in model.parameters() if p.requires_grad], 1.0)
                opt.step()
                sched.step()
                opt.zero_grad()
            if nstep % 100 == 0:
                print("  ep%d %d/%d loss=%.4f  %.0fs"
                      % (ep, nstep, len(idx) // a.bs, run / nstep, time.time() - t1),
                      flush=True)
        vp = gen_labels(model, tok, val_s, a.max_len, task_aware, a.style)
        vres = evaluate([s.label for s in val_s], vp, "ep%d val" % ep)
        hist.append({"epoch": ep, "train_loss": run / max(nstep, 1),
                     "val_macro_f1": vres["macro_f1"], "val_acc": vres["acc"]})
        if vres["macro_f1"] > best_f1:
            best_f1, best_ep = vres["macro_f1"], ep
            model.save_pretrained(os.path.join(ROOT, "guard", "adapters", tag))
            print("  saved best (ep%d f1=%.4f)" % (ep, best_f1), flush=True)

    print("\nbest epoch=%d val macro-F1=%.4f" % (best_ep, best_f1))
    out = {"tag": tag, "split": a.split, "task_aware": task_aware,
           "best_epoch": best_ep, "best_val_macro_f1": best_f1, "hist": hist,
           "args": vars(a)}
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "results", "train_%s.json" % tag), "w"),
              ensure_ascii=False, indent=1)
    print("adapter -> guard/adapters/%s" % tag)


if __name__ == "__main__":
    main()
