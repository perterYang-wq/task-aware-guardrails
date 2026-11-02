# -*- coding: utf-8 -*-
"""定位 DeepSeek thinking 模式对 reasoning_content 的硬要求。

四种历史形态各发一次，看哪些被接受。产物 results/mechanism_probe_v41flash/thinking_probe.json
"""
import json
import os

from openai import OpenAI

R = "/data/projects/guardrails"
OUT = os.path.join(R, "results/mechanism_probe_v41flash/thinking_probe.json")

SYS = "You are a helpful assistant."
U = "What is 2+2? Use the tool if needed."


def hist(with_tc, with_reason):
    a = {"role": "assistant", "content": None if with_tc else "Let me compute."}
    if with_tc:
        a["tool_calls"] = [{"id": "call_1", "type": "function",
                            "function": {"name": "add", "arguments": "{\"a\":2,\"b\":2}"}}]
    if with_reason:
        a["reasoning_content"] = "The user asks 2+2; I should call add."
    msgs = [{"role": "system", "content": SYS}, {"role": "user", "content": U}, a]
    if with_tc:
        msgs.append({"role": "tool", "tool_call_id": "call_1", "content": "{\"result\": 4}"})
    else:
        msgs.append({"role": "user", "content": "{\"result\": 4}"})
    return msgs


def main():
    key = (os.environ.get("DEEPSEEK_API_KEY") or
           open(os.path.expanduser("~/.secrets/deepseek.key")).read()).strip()
    c = OpenAI(base_url="https://api.deepseek.com/v1", api_key=key, timeout=60, max_retries=0)
    rec = dict(probes=[])
    for with_tc, with_reason in [(True, True), (True, False), (False, True), (False, False)]:
        p = dict(tool_calls=with_tc, reasoning=with_reason)
        try:
            r = c.chat.completions.create(model="deepseek-flash", temperature=0.0,
                                          messages=hist(with_tc, with_reason), max_tokens=32)
            p.update(ok=True, content=(r.choices[0].message.content or "")[:60])
        except Exception as e:
            p.update(ok=False, error="%s" % str(e)[:180])
        rec["probes"].append(p)
        print("tc=%-5s reason=%-5s -> %s %s" % (with_tc, with_reason,
                                                 "OK" if p.get("ok") else "FAIL",
                                                 p.get("content") or p.get("error", "")))
    json.dump(rec, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("->", OUT)


if __name__ == "__main__":
    main()
