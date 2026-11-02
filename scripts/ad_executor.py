"""GuardedExecutor + 阶段 7 最小验证（不需要 LLM）"""
import sys, os, json, time
ROOT='/data/projects/guardrails'
sys.path.insert(0, os.path.join(ROOT,'repos/agentdojo/src'))
from agentdojo.agent_pipeline.tool_execution import ToolsExecutor
from agentdojo.functions_runtime import FunctionsRuntime, FunctionCall, EmptyEnv
from agentdojo.types import ChatToolResultMessage, text_content_block_from_string

class RecordingRuntime(FunctionsRuntime):
    def __init__(self): super().__init__(); self.calls=[]
    def run_function(self, env, function, args, **kw):
        self.calls.append((function, dict(args)))
        return ("executed:%s" % function), None

class GuardedExecutor(ToolsExecutor):
    """decision_fn(tool, args) -> ('ALLOW'|'REVIEW'|'DENY', reason, extra)"""
    def __init__(self, decision_fn, logpath=None):
        super().__init__(); self.decision_fn=decision_fn; self.logpath=logpath; self.log=[]
    def query(self, query, runtime, env=EmptyEnv(), messages=(), extra_args={}):
        if not messages or messages[-1]["role"]!="assistant":
            return super().query(query,runtime,env,messages,extra_args)
        calls = messages[-1].get("tool_calls") or []
        results=[]; blocked=False
        for tc in calls:
            try:
                dec, reason, extra = self.decision_fn(tc.function, dict(tc.args or {}))
            except Exception as e:                     # 任何异常 → 安全默认
                dec, reason, extra = 'REVIEW', 'decision_error:%s' % e, {}
            if dec not in ('ALLOW','REVIEW','DENY'):
                dec, reason = 'REVIEW', 'invalid_decision'
            rec=dict(ts=time.time(), tool=tc.function, args=tc.args, decision=dec,
                     reason=reason, executed=False, **extra)
            if dec=='ALLOW':
                out, err = runtime.run_function(env, tc.function, tc.args)
                rec['executed']=True
                results.append(ChatToolResultMessage(role="tool",
                    content=[text_content_block_from_string(str(out))],
                    tool_call_id=tc.id, tool_call=tc, error=err))
            else:
                msg = ("Blocked by guard (DENY): %s" % reason) if dec=='DENY' else \
                      ("Suspended for review (REVIEW): %s" % reason)
                err = "denied_by_guard" if dec=='DENY' else "suspended_by_guard"
                results.append(ChatToolResultMessage(role="tool",
                    content=[text_content_block_from_string(msg)],
                    tool_call_id=tc.id, tool_call=tc, error=err))
                blocked=True
            self.log.append(rec)
        if self.logpath:
            with open(self.logpath,'a',encoding='utf-8') as f:
                for r in self.log[-len(calls):]: f.write(json.dumps(r,ensure_ascii=False)+"\n")
        return query, runtime, env, [*messages, *results], extra_args

def msg(tool, args, tid="c1"):
    return [{"role":"assistant","content":[text_content_block_from_string("")],
             "tool_calls":[FunctionCall(function=tool,args=args,id=tid)]}]

if __name__=='__main__':
    out=os.path.join(ROOT,'results/ad_v2/executor_validation.jsonl')
    open(out,'w').close()
    cases=[
        ("ALLOW 正常执行", lambda t,a: ('ALLOW','safe',{}), True),
        ("DENY 必须阻断",  lambda t,a: ('DENY','attack',{}),  False),
        ("REVIEW 必须暂停",lambda t,a: ('REVIEW','uncertain',{}), False),
        ("异常时安全默认",  lambda t,a: (_ for _ in ()).throw(RuntimeError("pg2 oom")), False),
        ("非法决策值",     lambda t,a: ('allow', 'bad', {}), False),
    ]
    ok=True
    for name, fn, should_exec in cases:
        rt=RecordingRuntime(); ex=GuardedExecutor(fn, out)
        ex.query("q", rt, EmptyEnv(), msg("send_money", {"amount":1}), {})
        executed=len(rt.calls)>0
        passed = (executed==should_exec)
        ok &= passed
        print('%-16s executed=%-5s expected=%-5s %s  last=%s'%(
            name, executed, should_exec, 'PASS' if passed else 'FAIL',
            ex.log[-1]['decision'] if ex.log else '?'))
    print('\n总体:', '通过' if ok else '失败')
    sys.exit(0 if ok else 1)
