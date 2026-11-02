# -*- coding: utf-8 -*-
"""模型名探测：账号只认 deepseek-flash / deepseek-v4-pro，确认哪个可用、temperature=0 是否接受。

产物 results/mechanism_probe_v41flash/model_probe.json（不含 key、不含 key 路径以外的凭据）
"""
import json
import os
import time

from openai import OpenAI

R = "/data/projects/guardrails"
OUT = os.path.join(R, "results/mechanism_probe_v41flash/model_probe.json")


def load_key():
    k = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if k:
        return k
    with open(os.path.expanduser("~/.secrets/deepseek.key"), encoding="utf-8") as f:
        return f.read().strip()


def main():
    key = load_key()
    base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    c = OpenAI(base_url=base, api_key=key, timeout=60, max_retries=0)
    rec = dict(base_url=base, ts=time.strftime("%Y-%m-%d %H:%M:%S"), probes=[])

    for model in ("deepseek-flash", "deepseek-v4-pro"):
        for temp in (0.0, None):
            p = dict(model=model, temperature=temp)
            t0 = time.time()
            try:
                kw = dict(model=model,
                          messages=[{"role": "user", "content": "Reply with exactly: OK"}],
                          max_tokens=8)
                if temp is not None:
                    kw["temperature"] = temp
                r = c.chat.completions.create(**kw)
                p.update(ok=True, model_returned=r.model,
                         content=(r.choices[0].message.content or "")[:40],
                         finish_reason=r.choices[0].finish_reason,
                         usage=(r.usage.model_dump() if r.usage else None),
                         wall_ms=int((time.time() - t0) * 1000))
            except Exception as e:
                p.update(ok=False, error="%s: %s" % (type(e).__name__, str(e)[:240]))
            rec["probes"].append(p)
            print("%-16s temp=%-4s %s %s" % (model, temp, "OK" if p.get("ok") else "FAIL",
                                             p.get("model_returned") or p.get("error", "")[:110]),
                  flush=True)

    json.dump(rec, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("->", OUT)


if __name__ == "__main__":
    main()
