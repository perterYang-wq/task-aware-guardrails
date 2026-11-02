# -*- coding: utf-8 -*-
"""判定 7B 能否在 24G 卡上做 LoRA：一个真实的 forward+backward 步，量峰值显存。

不是估算，是实测：加载权重 -> 挂 LoRA -> 梯度检查点 -> 用最长的实际 prompt 跑一步。
"""
import json
import os
import sys
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from guard.schema import render_fitted, step_from_dict  # noqa: E402

MODEL = "/home/linux/.cache/huggingface/hub/models--Qwen--Qwen2.5-7B-Instruct/snapshots"
DATA = os.path.join(ROOT, "data", "pab.jsonl")


def snap():
    d = MODEL
    subs = [x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x))]
    return os.path.join(d, subs[0])


def main():
    path = snap()
    print("model:", path)
    tok = AutoTokenizer.from_pretrained(path)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    max_len = int(sys.argv[1]) if len(sys.argv) > 1 else 1280
    bs = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    rows = [step_from_dict(json.loads(l)) for l in open(DATA, encoding="utf-8")]
    rows.sort(key=lambda r: -len(r.current_action) - len(r.instruction))
    prompts = [tok.apply_chat_template(
        [{"role": "user", "content": render_fitted(tok, r, max_len - 8, style="pab")}],
        tokenize=True, add_generation_prompt=True, return_dict=False) for r in rows[:bs]]
    aid = tok("0.0", add_special_tokens=False).input_ids + [tok.eos_token_id]
    seqs = [(p + aid, [-100] * len(p) + aid) for p in prompts]
    L = max(len(x[0]) for x in seqs)
    print("bs=%d  seq_len=%d  (max_len=%d)" % (bs, L, max_len))

    t0 = time.time()
    m = AutoModelForCausalLM.from_pretrained(path, torch_dtype=torch.float16,
                                             device_map="cuda")
    m.config.use_cache = False
    m.gradient_checkpointing_enable()
    m.enable_input_require_grads()
    from peft import LoraConfig, get_peft_model
    m = get_peft_model(m, LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"]))
    n_tr = sum(p.numel() for p in m.parameters() if p.requires_grad)
    print("loaded in %.0fs  trainable=%.1fM (%.2f%%)"
          % (time.time() - t0, n_tr / 1e6, 100 * n_tr / sum(p.numel() for p in m.parameters())))
    m.train()

    ids = torch.tensor([x[0] + [tok.pad_token_id] * (L - len(x[0])) for x in seqs]).cuda()
    lab = torch.tensor([x[1] + [-100] * (L - len(x[1])) for x in seqs]).cuda()
    att = torch.ones_like(ids)
    torch.cuda.reset_peak_memory_stats()
    t1 = time.time()
    out = m(input_ids=ids, attention_mask=att, labels=lab)
    out.loss.backward()
    torch.cuda.synchronize()
    peak = torch.cuda.max_memory_allocated() / 2 ** 30
    print("one step: loss=%.4f  %.1fs  peak_alloc=%.2f GiB" % (out.loss.item(),
                                                               time.time() - t1, peak))
    print("total(reserved)=%.2f GiB  free=%.2f GiB"
          % (torch.cuda.memory_reserved() / 2 ** 30,
             (torch.cuda.get_device_properties(0).total_memory
              - torch.cuda.memory_reserved()) / 2 ** 30))
    print("VERDICT:", "FITS" if peak < 21.5 else "TOO TIGHT")


if __name__ == "__main__":
    main()
