"""把冻结的 Task-Aware Guard 挂进执行循环（在线，逐调用判定）。

与离线 `ad_score.py` / `diag_score.py` 用的是**同一套**渲染与解码配置：
  render_pab(task_aware=True) → apply_chat_template → greedy, max_new_tokens=6 → parse_rating
唯一的区别是模型只加载一次、逐条调用。

显存取放：环境变量 GUARD_DEVICE=cpu 时把守卫放 CPU。7B agent 的 vLLM 已占
18.9GiB，1.5B 守卫在 fp16 下还要 ~3GiB，24G 卡上常常贴边；放 CPU 每次判定
多几百毫秒，但不会 OOM，也不影响结论。
"""
import os
import sys

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = '/data/projects/guardrails'
sys.path.insert(0, ROOT)
from guard.schema import Step, parse_rating, render_pab  # noqa: E402


class InlineGuard:
    def __init__(self, model_path='/data/hf_cache/qwen1.5b',
                 adapter=ROOT + '/guard/adapters/p1_15b_task_l2_s0', max_new=6,
                 device=None):
        self.device = device or os.environ.get('GUARD_DEVICE', 'cuda')
        dtype = torch.float32 if self.device == 'cpu' else torch.float16
        self.tok = AutoTokenizer.from_pretrained(model_path, padding_side='left')
        if self.tok.pad_token is None:
            self.tok.pad_token = self.tok.eos_token
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path, torch_dtype=dtype).to(self.device).eval()
        if adapter:
            from peft import PeftModel
            self.model = PeftModel.from_pretrained(self.model, adapter).eval()
        self.max_new = max_new
        self.n = 0
        self.ms = []

    @torch.no_grad()
    def decide(self, instruction, history, current_action):
        import time
        t0 = time.time()
        st = Step(sid='live', source='agentdojo', instruction=instruction or '',
                  history=history or '', current_action=current_action or '',
                  env_info='', score=0.0, label='', tool=None, args={})
        text = self.tok.apply_chat_template(
            [{'role': 'user', 'content': render_pab(st, task_aware=True)}],
            tokenize=False, add_generation_prompt=True)
        enc = self.tok([text], return_tensors='pt', padding=True,
                       add_special_tokens=False).to(self.device)
        out = self.model.generate(**enc, max_new_tokens=self.max_new, do_sample=False,
                                  pad_token_id=self.tok.pad_token_id)
        gen = self.tok.decode(out[0][enc['input_ids'].shape[1]:], skip_special_tokens=True)
        self.n += 1
        self.ms.append(int((time.time() - t0) * 1000))
        lab = parse_rating(gen)
        return lab, gen.strip()[:40]
