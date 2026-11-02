# Task-Aware Guardrails for LLM Agents

A per-tool-call guard for tool-calling LLM agents. Instead of asking *"does this payload look
malicious?"*, it asks *"is this action authorized by the user's task?"* — the failure mode that
indirect prompt injection actually exploits (a legitimate-looking write call the user never asked for).

Evaluated on **AgentDojo v1.2.2** (banking / slack / travel) with a Qwen2.5-7B agent and a
1.5B LoRA guard on Qwen2.5-1.5B-Instruct. Reports are written in Chinese; code and figure
captions are in English.

## Headline results

| Setting | Result |
|---|---|
| Slack, 42 attack scenarios, same 7B agent | ASR **0/42** (guard) vs **0/42** (Task-Shield); clean utility **66.7% vs 23.8%** (McNemar 9:0, p=.0039); latency **251 vs 574 ms** |
| Travel, 80 scenarios | ASR **13/80 → 1/80** (McNemar p=.0018) |
| Banking, 64 scenarios | ASR **2/64 → 0/64** (ceiling effect, p=.50) |
| Cost of the guard | +4.1 GB VRAM, 251 ms per decision (1.5B, GPU fp16) |

Known limits, stated up front: travel utility is **lower** than the unguarded baseline (10% vs 25%);
CPU-only inference does **not** meet real-time (p50 1.46 s, p95 4.18 s); the cross-backbone probe on
a commercial agent found the mechanism does **not** transfer unchanged.

## Repository layout

```
scripts/         训练、端到端评测、指标重算、出图（每个数字都由脚本重算，不手填）
guard/           守卫代码（schema / router / metrics）；adapters/ 权重未入库
reports/         全部报告：claim 状态表、主结果 CSV、失败分析、机制探针
probes/          反事实探针与归因产物（JSON）
final_figures/   交付图（fig1–fig7b）
runs/auto/       state.json：批次、claim 状态、预算
bootstrap.sh     环境初始化
```

## Where the numbers live

- `reports/claim_status.md` — claims C1–C8 with the scope each one may be stated in, plus forbidden phrasings.
- `reports/final_metrics.csv` — every metric with value / denominator / source file / recompute script.
- `reports/failure_analysis.md` — three failure cases and what they imply.
- `reports/mechanism_probe_v41flash.md`, `..._v2.md` — what happens on a commercial backbone.
- `reports/final_figures.md` — figure index with captions and data sources.

## Not in this repository

Excluded for size; all regenerable or obtainable from the authors:

| Path | Size | Why excluded |
|---|---|---|
| `results/` | 226 MB | raw per-call e2e records and traces |
| `guard/adapters/` | 4.5 GB | LoRA weights; sha256 manifests kept in `frozen/` |
| `frozen/P1M2_20261101/` | 60 MB | frozen snapshot; manifest + tar.gz hash kept |
| `data/` | 36 MB | evaluation sets and derived data |
| `repos/` | 562 MB | upstream clones (agentdojo, toolsafe) |

## Status

Research code accompanying a paper in progress. Paths are absolute (`/data/projects/guardrails`)
in several scripts. Numbers in `reports/` are the source of truth; older reports may have been
superseded, and each one states its own protocol.
