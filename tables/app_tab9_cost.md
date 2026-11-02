# app_tab9_cost

Cost comparison: latency, VRAM, ACB and false blocks per arm.

| Arm | Suite | Latency mean/P95 (ms) | Device | Extra VRAM (GB) | ACB (n) | Clean false block (%) |
|---|---|---|---|---|---|---|
| M1 (1.5B) | slack | 251 / 265 | GPU fp16 | +4.1 | 0.981 (2370) | 4/123 (3.3) |
| Task-Shield (7B judge) | slack | 574 / 610 | GPU fp16 | 0 (shared) | 0.518 (300) | 71/117 (60.7) |
| String rule (gamma=3) | slack | 0.0012 / 0.0012 | CPU, 416 calls | 0 | – | 55/129 (42.6) |
| 0.5B guard | travel | 1461 / 4182 | CPU, n=95 | – (not measured) | 0.849 (2370) | 21/99 (21.2) |

**Notes**

- Latency is never compared across devices: the two upper rows are GPU fp16 end-to-end calls, the lower two are CPU-only string / 0.5B measurements.
- ACB denominators differ: 2370 diagnostic calls for the guards, 300 calibration calls for Task-Shield. The two are not interchangeable.
- The false-block column mixes suites by design (M1, Task-Shield and the string rule on slack; 0.5B on travel, its only end-to-end run): read it as within-row only.
- 0.5B GPU latency and VRAM were never measured (`reports/b5_lightweight.md`); the cell stays empty rather than guessed.

LaTeX: `tables/app_tab9_cost.tex` · CSV: `tables/app_tab9_cost.csv`
