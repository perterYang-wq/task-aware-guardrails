

def install_tolerant_parser():
    """本地 7B 常写出 <function=name>args<function>（闭合标签错）或无参数，
    原解析器直接判为 broken JSON。这里做容错：找函数名 → 取后面第一个平衡 JSON → 没有就给空参数。"""
    import json as _json
    import re as _re
    import agentdojo.agent_pipeline.llms.local_llm as L
    from agentdojo.functions_runtime import FunctionCall
    from agentdojo.types import ChatAssistantMessage, text_content_block_from_string

    def parse(completion: str):
        base = ChatAssistantMessage(
            role="assistant",
            content=[text_content_block_from_string((completion or "").strip())],
            tool_calls=[])
        txt = completion or ""
        m = _re.search(r"<function\s*[=:]\s*([A-Za-z0-9_.\-]+)\s*>", txt)
        if not m:
            return base
        name = m.group(1).strip()
        rest = txt[m.end():]
        # 去掉可能紧跟的闭合标签 / 下一个开标签
        rest = _re.split(r"</function>|<function", rest)[0]
        # 找第一个平衡的 JSON 对象
        s = rest.find("{")
        args = {}
        if s != -1:
            depth = 0
            for i, ch in enumerate(rest[s:], start=s):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            args = _json.loads(rest[s:i + 1])
                        except Exception:
                            args = {}
                        break
        return ChatAssistantMessage(
            role="assistant",
            content=[text_content_block_from_string(txt.strip())],
            tool_calls=[FunctionCall(function=name, args=args if isinstance(args, dict) else {})])

    L._parse_model_output = parse
