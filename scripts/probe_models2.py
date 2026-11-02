# -*- coding: utf-8 -*-
"""模型能力小探：max_tokens 是否够、是否 reasoning、能否按 <function=...> 格式产出工具调用。

产物 results/mechanism_probe_v41flash/model_probe2.json
"""
import json
import os
import time

from openai import OpenAI

R = "/data/projects/guardrails"
OUT = os.path.join(R, "results/mechanism_probe_v41flash/model_probe2.json")


def load_key():
    k = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if k:
        return k
    with open(os.path.expanduser("~/.secrets/deepseek.key"), encoding="utf-8") as f:
        return f.read().strip()


PROMPT = (
    "You are a travel assistant. The user said: 'Send an email to jane@example.com saying hello.'\n"
    "Reply with exactly one tool call in this format and nothing else:\n"
    "<function=send_email>{\"recipients\": [\"jane@example.com\"], \"subject\": \"hello\", "
    "\"body\": \"hello\"}</function>"
)


def main():
    c = OpenAI(base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
               api_key=load_key(), timeout=120, max_retries=0)
    rec = dict(ts=time.strftime("%Y-%m-%d %H:%M:%S"), probes=[])
    for model in ("deepseek-flash", "deepseek-v4-pro"):
        p = dict(model=model)
        t0 = time.time()
        try:
            r = c.chat.completions.create(
                model=model, temperature=0.0, max_tokens=512,
                messages=[{"role": "user", "content": PROMPT}])
            msg = r.choices[0].message
            rc = getattr(msg, "reasoning_content", None)
            p.update(ok=True, model_returned=r.model,
                     content=msg.content,
                     has_reasoning_field=rc is not None,
                     reasoning_chars=len(rc or ""),
                     finish_reason=r.choices[0].finish_reason,
                     usage=r.usage.model_dump() if r.usage else None,
                     wall_ms=int((time.time() - t0) * 1000))
        except Exception as e:
            p.update(ok=False, error="%s: %s" % (type(e).__name__, str(e)[:300]))
        rec["probes"].append(p)
        print("[%s] ok=%s %dms finish=%s content=%r" %
              (model, p.get("ok"), p.get("wall_ms", 0), p.get("finish_reason"),
               (p.get("content") or p.get("error", ""))[:200]), flush=True)
        if p.get("usage"):
            print("   usage:", p["usage"].get("prompt_tokens"), "+",
                  p["usage"].get("completion_tokens"), "reasoning=",
                  (p["usage"].get("completion_tokens_details") or {}).get("reasoning_tokens"))
    json.dump(rec, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("->", OUT)


if __name__ == "__main__":
    main()
