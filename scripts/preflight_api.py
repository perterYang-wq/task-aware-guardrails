# -*- coding: utf-8 -*-
"""API 预检：确认 key 可用、模型 id 是什么、是否支持 temperature=0。

只做一次 8-token 的调用，费用可忽略。产物 results/mechanism_probe_v41flash/preflight.json
（不含 key）。
"""
import json
import os
import sys
import time

from openai import OpenAI

R = "/data/projects/guardrails"
OUT = os.path.join(R, "results/mechanism_probe_v41flash/preflight.json")
MODEL = os.environ.get("PROBE_MODEL", "deepseek-v4.1-flash")

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


def main():
    key, key_src = load_api_key()
    base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    if not key:
        print("[blocked] 没有可用 key：%s" % key_src)
        print("  两种给法：")
        print("    1) export DEEPSEEK_API_KEY=sk-...（仅本进程）")
        print("    2) 写入 ~/.secrets/deepseek.key（chmod 600），本脚本自动读取")
        return 2
    print("[key] 来源=%s 长度=%d" % (key_src, len(key)))
    c = OpenAI(base_url=base, api_key=key, timeout=30, max_retries=0)
    rec = dict(base_url=base, requested_model=MODEL, key_source=key_src, ts=time.strftime("%Y-%m-%d %H:%M:%S"))
    try:
        ids = [m.id for m in c.models.list().data]
        rec["models_visible"] = ids[:20]
        print("[models]", ids[:20])
    except Exception as e:
        rec["models_error"] = "%s: %s" % (type(e).__name__, str(e)[:300])
        print("[models] 不可列：", rec["models_error"])

    try:
        r = c.chat.completions.create(
            model=MODEL, messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            temperature=0.0, max_tokens=8)
        rec.update(model_returned=r.model, content=r.choices[0].message.content,
                   usage=dict(r.usage.model_dump()) if r.usage else None, ok=True)
        print("[chat] model_returned=%s content=%r usage=%s"
              % (r.model, r.choices[0].message.content, rec["usage"]))
    except Exception as e:
        rec.update(ok=False, error="%s: %s" % (type(e).__name__, str(e)[:500]))
        print("[chat] 失败：", rec["error"])

    json.dump(rec, open(OUT, "w"), ensure_ascii=False, indent=2)
    print("->", OUT)
    return 0 if rec.get("ok") else 3


if __name__ == "__main__":
    sys.exit(main())
