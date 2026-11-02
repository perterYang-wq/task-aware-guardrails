# tab4_rule_three_arms

Where the gain comes from: string rules versus the model versus both (slack).

| Arm | ASR (%) | ASR, write | ASR, read | Clean completion (%) | Clean false block (%) | p vs M1 (ASR) | p vs M1 (utility) |
|---|---|---|---|---|---|---|---|
| String rule only | 12/42 (28.6) | 0/21 (0.0) | 12/21 (57.1) | 1/21 (4.8) | 55/129 (42.6) | p=0.0005 (McNemar) | – |
| M1, model only | 0/42 (0.0) | 0/21 (0.0) | 0/21 (0.0) | 14/21 (66.7) | 4/123 (3.3) | reference | reference |
| M1 + string rule | 0/42 (0.0) | 0/21 (0.0) | 0/21 (0.0) | 1/21 (4.8) | 58/129 (45.0) | n/a (no discordant pairs) | p=0.0002 (McNemar) |

**Notes**

- slack, seed 0, GPU fp16, 42 attack / 21 clean scenarios; all three arms share one execution boundary (the `–hard-rule` switch).
- Write-type = slack `injection_task_1` (21 scenarios), read-type = `injection_task_3` (21 scenarios), recomputed from guard decisions.
- The string rule blocks every write-type attack but leaves read-type at 12/21 — identical to the unguarded baseline (E0, also 12/21).
- M1+rule vs M1 on ASR is 0:0, so no exact test exists; the audit's p=1.0 only records that nothing was testable, not that the arms are equivalent.
- McNemar exact: ASR rule-vs-M1 12:0 (p=0.0005; Fisher gives 0.0002); utility M1+rule-vs-M1 0:13 (p=0.0002).

LaTeX: `tables/tab4_rule_three_arms.tex` · CSV: `tables/tab4_rule_three_arms.csv`
