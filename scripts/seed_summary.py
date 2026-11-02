# -*- coding: utf-8 -*-
"""S / H / HB 多 seed 汇总（均值 ± 标准差）。

只读 results/diag/metrics.json；每个臂按 seed 后缀分组。
"""
import json
import statistics as st

P = "/data/projects/guardrails/results/diag/metrics.json"
FAM = {"S": "m2_S_s", "H": "m2_H_s", "HB": "m2_HB_s", "HB-sm": "m2_SM_s"}


def main():
    m = json.load(open(P))
    print("%-6s %-4s %8s %8s %9s %9s %8s" % ("arm", "seed", "ACB", "CCBcl", "CCBinj", "Intact", "PRA?"))
    agg = {}
    for name, pre in FAM.items():
        rows = []
        for a in sorted(m):
            if not a.startswith(pre):
                continue
            d = m[a]["full"]
            seed = a[len(pre):]
            rows.append(dict(seed=seed, ACB=d["ACB"], CCB=d["CCB_clean"],
                             CCBinj=d["CCB_inj"], Intact=d["clean_intact"]))
            print("%-6s %-4s %8.3f %8.3f %9.3f %9.3f" %
                  (name, seed, d["ACB"], d["CCB_clean"], d["CCB_inj"], d["clean_intact"]))
        if rows:
            agg[name] = rows

    print("\n%-6s %14s %14s %14s" % ("arm", "ACB", "CCB_clean", "CCB_inj"))
    out = {}
    for name, rows in agg.items():
        def f(k):
            v = [r[k] for r in rows]
            return "%.3f±%.3f" % (st.mean(v), st.stdev(v)) if len(v) > 1 else "%.3f" % v[0]
        out[name] = dict(n=len(rows), ACB=f("ACB"), CCB=f("CCB"), CCBinj=f("CCBinj"),
                         Intact=f("Intact"))
        print("%-6s %14s %14s %14s   n=%d" % (name, out[name]["ACB"], out[name]["CCB"],
                                              out[name]["CCBinj"], len(rows)))
    json.dump(out, open("/data/projects/guardrails/results/m2/seed_summary.json", "w"),
              ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
