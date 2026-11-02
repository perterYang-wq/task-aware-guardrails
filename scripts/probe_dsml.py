# -*- coding: utf-8 -*-
"""观察 deepseek-flash 的真实工具调用格式（多参数情形）。

用 AgentDojo 自己的 _tool_calling_prompt 构造系统提示，确保与实际链路一致。
产物 results/mechanism_probe_v41flash/dsml_probe.json
"""
import json
import os

from agentdojo.agent_pipeline.llms.local_llm import _tool_calling_prompt
from openai import OpenAI

R = "/data/projects/guardrails"
OUT = os.path.join(R, "results/mechanism_probe_v41flash/dsml_probe.json")

FUNCS = [
    {"name": "send_email", "description": "Send an email",
     "parameters": {"type": "object", "properties": {
         "recipients": {"type": "array", "items": {"type": "string"}},
         "subject": {"type": "string"}, "body": {"type": "string"}},
         "required": ["recipients", "subject", "body"]}},
    {"name": "create_calendar_event", "description": "Create a calendar event",
     "parameters": {"type": "object", "properties": {
         "title": {"type": "string"}, "start_time": {"type": "string"},
         "end_time": {"type": "string"}, "location": {"type": "string"}},
         "required": ["title", "start_time", "end_time"]}},
]

USER = ("Send an email to jane@example.com with subject 'Booking' and body 'Hotel booked'. "
        "Also create a calendar event titled 'Booking hotel' on 2024-04-25 from 09:00 to 10:00 "
        "at 12 Rue de Rivoli, Paris.")


def main():
    key = (os.environ.get("DEEPSEEK_API_KEY") or
           open(os.path.expanduser("~/.secrets/deepseek.key")).read()).strip()
    c = OpenAI(base_url="https://api.deepseek.com/v1", api_key=key, timeout=120, max_retries=0)
    functions = "\n\n".join(json.dumps(f, indent=2) for f in FUNCS)
    sysmsg = _tool_calling_prompt.format(functions=functions) + \
        "\n\n## Additional Instructions\n\nYou are a helpful assistant."

    rec = dict(ts=None, probes=[])
    for temp in (0.0,):
        r = c.chat.completions.create(
            model="deepseek-flash", temperature=temp, top_p=1.0,
            messages=[{"role": "system", "content": sysmsg},
                      {"role": "user", "content": USER}])
        msg = r.choices[0].message
        has = [n for n in ("reasoning_content", "tool_calls") if getattr(msg, n, None)]
        rec["probes"].append(dict(model=r.model, temperature=temp,
                                  content=msg.content,
                                  extra_fields=has,
                                  finish_reason=r.choices[0].finish_reason,
                                  usage=r.usage.model_dump() if r.usage else None))
        print("=== content repr ===")
        print(repr(msg.content)[:2000])
        print("extra:", has, "finish:", r.choices[0].finish_reason)
    json.dump(rec, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("->", OUT)


if __name__ == "__main__":
    main()
