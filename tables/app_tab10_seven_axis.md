# app_tab10_seven_axis

Seven-axis ablation summary.

| Axis | Comparison | Result (metric as reported) | Source |
|---|---|---|---|
| Task field (training) | E0 / M0 / M1 | banking 8/32->0/32->0/32; slack 21/42->4/42->0/42; travel 13/40->6/40->1/40 | final_metrics.csv::C2_task_aware |
| Task field (inference) | full vs task field removed (E1) | ACB .918->.893; clean non-interference .905->.619 | frozen P1M2 / P2_ablation.md |
| History length | none / last3 / full | ACB .560 / .837 / .918 (M1) | results/diag/metrics.json |
| Data recipe | E0 -> S -> M0 -> M1 | ASR 50.0->11.9->9.5->0.0; utility 61.9->47.6->33.3->66.7 | final_metrics.csv::B10 |
| Paired positives | HB vs HB-sm | offline CCB_inj .036 vs .439; online, call level 15.9% vs 62.4%; same at task level | b10e_hbsm.md |
| Deployment component | string rule / M1 / M1 + rule | ASR 28.6 / 0 / 0; utility 4.8 / 66.7 / 4.8 | final_metrics.csv::B10 |
| Decision policy | check all / gammage2 / gammage3 | ACB .981/.818/.761; checked fraction 100/27.0/23.6%; read-type .929/0/0 | results/classifier/routing_ablation.json |
| Action prior vs task info | M1 only / M0 only | 6 / 4; intersection 20; robust net gain 2 | probes/net_gain_sets.json |

**Notes**

- Metrics differ per axis (ASR, ACB, call counts, set sizes): rows are not comparable with each other, and the table is a map of the ablation, not a ranking.
- Every cell is copied from `reports/b9_notes.md` section 2; the source column names the artefact that produced it.
- Axis 7 is the set view of the denial attribution (M1 only 6, M0 only 4, intersection 20, robust 2), not a proportion.

LaTeX: `tables/app_tab10_seven_axis.tex` · CSV: `tables/app_tab10_seven_axis.csv`
