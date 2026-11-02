# tab2_vs_tshield

Head-to-head against a 7B task-aware judge on slack.

| Arm | ASR (%) | Clean completion (%) | DENY/checked | Latency mean/P95 (ms) | Extra VRAM (GB) | McNemar p |
|---|---|---|---|---|---|---|
| M1 (1.5B guard, ours) | 0/42 (0.0) | 14/21 (66.7) | 26/411 | 251 / 265 | +4.1 | reference |
| Task-Shield (7B judge) | 0/42 (0.0) | 5/21 (23.8) | 222/331 | 574 / 610 | 0 (shares agent 7B) | p=0.0039 |
| ToolSafe | not reproduced | – | – | – | – | – |
| String rule (gamma=3) | 13/42 (31.0) | 1/21 (4.8) | 154/408 | 0.0012 / 0.0012 | 0 | – |

**Notes**

- slack, seed 0, GPU fp16, 42 attack / 21 clean scenarios; latency and decision counts come from the same runs as ASR and utility.
- Task-Shield latency is read from `reports/b3_tshield.md` (slack table); the string rule runs on CPU (416 calls), so its latency column is not comparable with the two GPU rows.
- The only formally tested contrast is M1 vs Task-Shield on clean-task completion (McNemar exact, 9:0, p=0.0039); the string-rule arm is reported descriptively.
- Extra VRAM is guard-only: the 7B judge reuses the agent's weights, the 1.5B guard adds 4.1 GB. ToolSafe was not reproduced under this protocol, so no number is given.

LaTeX: `tables/tab2_vs_tshield.tex` · CSV: `tables/tab2_vs_tshield.csv`
