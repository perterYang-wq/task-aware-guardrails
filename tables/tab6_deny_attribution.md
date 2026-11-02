# tab6_deny_attribution

Where the denials come from: payload recognition versus action prior.

| Arm | DENY total | Payload recog. | Non-payload (%) | A cap B | M1 only | M0 only | Robust net gain | McNemar p |
|---|---|---|---|---|---|---|---|---|
| M1 (task-aware) | 34 | 8 | 26 (76.5) | – | – | – | – | – |
| M0 (task-blind) | 27 | 5 | 22 (81.5) | – | – | – | – | – |
| Set difference | – | – | – | 20 | 6 | 4 | 2 | p=0.7539 |

**Notes**

- Same 34 DENY instances, re-scored on CPU fp32, greedy; this is a different precision from the GPU fp16 end-to-end runs.
- ``Non-payload'' means the call is still denied after the whole `<INFORMATION>` block is deleted (P1); it does not mean the input is free of attack content (17/34 keep payload entities, 6/34 are paraphrased).
- Columns 5–8 use the P1-expanded sets: |A|=26 (M1), |B|=24 (M0). The M0 *non-payload* count of 22 is the P0capP1 subset and is not the same quantity as |B|.
- M0 covers 20/26 (76.9%) of the M1 non-payload denials, so 76.9% is a within-set agreement rate, not a recall.
- Net gain 6 vs 4, McNemar exact p=0.754; after removing 4 contaminated items the robust subset is 2.

LaTeX: `tables/tab6_deny_attribution.tex` · CSV: `tables/tab6_deny_attribution.csv`
