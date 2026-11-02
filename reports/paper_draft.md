# Grounding First
### What a small guard actually learns about agent tool-call authorization, and what the user request adds

Draft v5 — 2026-10-30
所有数字可由 `/data/projects/guardrails/scripts/` 复现；原始输出在 `results/`。

---

## Abstract

Step-level guards for LLM agents are evaluated by asking whether a pending tool call is
authorized given the user request, the interaction history and the call itself. F1 above
0.9 is read as evidence that the problem is nearly solved. That reading is not supported.

On TS-Bench (7,182 steps) a lookup keyed on the **tool name alone** reaches macro-F1 0.960;
a TF-IDF model reading **only the action text** reaches 0.916; adding the user request
changes the score by **−0.003**. Minimal pairs — same tool, same arguments, different
label — are **0.48%** of the data and absent from the held-out-tool test set. Holding the
tools out collapses the lookup from 0.960 to 0.143.

We rebuild the benchmark from AgentDojo's 97 tasks and 339 ground-truth tool calls, with
evidence rendered from the **real environment documents** (bill files, emails, drive files,
hotel records). In the resulting set **164 of 165 action strings occur under more than one
label**, so any deterministic function of the action text scores exactly 50.0% on
same-action pairs — a property of the construction, not an estimate — and a rule that only
checks whether the call's arguments appear in the documents scores **50.5%**. Every surface
baseline sits at 50.0–52.2%.

Across four guard sizes (0.5B, 1.5B, 3B, 7B), zero-shot capability scales with size
(46.1% → 50.0% → 71.7% → 80.6% PRA) but stays far below any fine-tuned model: LoRA on
764 examples lifts the 0.5B to 78.3% and the 7B to 83.9%, while the two deployment sizes,
re-run under one frozen protocol with three seeds each, reach **84.1% ± 1.7 (1.5B)** and
**88.5% ± 0.8 (3B)** PRA, the 3B again the best operating point. A 0.5B model with
fine-tuning (78.3%) comes within 2.3 points of a 7B zero-shot (80.6%).

The ablation is the paper's main measurement. With the user request removed, guards still
reach **77.2% (1.5B)** and **79.1% (3B)** PRA: most of the capability is **grounding**, i.e.
checking the call against what the agent retrieved. Adding the request is worth
**+6.9 ± 2.3** and **+9.4 ± 2.9** points of PRA, positive in every seed, and roughly twice
that in SPA. All inference is clustered by action group (47 groups, design effect 1.8–2.6):
the 3B's effect survives a whole-group sign-flip permutation — ΔPRA +0.094 [+0.031, +0.159],
p = 0.0067; ΔSPA +0.204 [+0.089, +0.326], p = 0.0016 — while the 1.5B's does not
(p = 0.098) despite a positive direction in all three seeds. At 90 pairs the effect is
resolvable for the 3B only, and we say so. A pre-registered equal-weight average over the
earlier three-guard build gives ΔPRA = +0.085 [+0.014, +0.152], p = 0.021 and
ΔSPA = +0.189 [+0.074, +0.300], p = 0.0028; we keep it as an auxiliary cross-size statement.

To separate the two signals by construction, we hold action and evidence fixed and vary only
the user task, keeping pairs whose **both** tasks were unseen in training (41 pairs, 19
scenarios, 6 action groups). Here the no-request guards score **exactly 0.500** PRA with
TieRate **1.000** in all three seeds — removing the task does not degrade the guard, it
removes its ability to decide, since the two renderings of a pair become byte-identical. With
the request the same checkpoints reach **0.948 ± 0.019 (3B)** and 0.827 ± 0.110 (1.5B).
Grounding carries most of the accuracy on naturally occurring pairs; where grounding has
nothing left to compare, the request is the only signal — a regime the standard benchmark
never isolates.

We therefore argue that grounding, not task-awareness, is the bulk of what a guard of this
class learns; that the request is a real but secondary signal on naturally occurring pairs and
the only one once action and evidence are held fixed; and that a benchmark which cannot
separate the two — the standard one — should not be used to claim either.

---

## 1. Introduction

Three signals are available before a tool call: what the user asked (the task), what the
agent retrieved (the evidence), and the call itself. Published step-level benchmarks provide
all three, and high scores are read as evidence that models use all three.

This paper separates them.

1. **The standard benchmark measures tool identity** (§2). Tool-name lookup 0.960 → 0.143
   with tools held out; action text alone 0.916; the request adds −0.003; minimal pairs
   0.48%.
2. **A benchmark with a provable 50% floor, built on real documents** (§3). Every action
   string appears under multiple labels, so action-only models are exactly at chance; the
   evidence is parsed from the environment's own files, so "the value appears in the
   documents" is not a proxy for "the call was authorized" (grounding oracle: 50.5%).
3. **Fine-tuning dominates scale** (§5.2). Zero-shot bandwidth is 46–81% pairwise across
   0.5B–7B; after LoRA every size is 78–91%, and a 0.5B guard is within 2.3 points of a 7B
   zero-shot.
4. **Grounding is the bulk of the learned capability** (§5.3). With the request removed,
   guards still reach 0.71–0.78 PRA. The request adds +0.05 to +0.13 PRA and +0.08 to +0.30
   SPA, but only the 3B's ΔPRA survives action-clustered inference. The one run that first
   looked null was an under-tuned checkpoint, not a limit of the model size.

Point 4 is the claim: a guard of this class is primarily a grounding checker, and the
"task-aware guardrail" framing overstates the part of the problem it solves.

---

## 2. What the standard benchmark measures

### 2.1 Data and label semantics

TS-Bench: 7,182 step-level records (AgentHarm 731, AgentDojo 1,220, ASB 5,231) with a
three-level `score` (0.0 / 0.5 / 1.0 → ALLOW / REVIEW / DENY). Counts match the published
ones except ASB (5,231 vs 5,237; 6 records unaccounted for).

We verify rather than assume the semantics: ASB records with `attack_success = True` but
`score = 0` contain benign calls (`market_data_api`), while `score = 1` records carry
arguments such as `"action": "redirect_funds_without_authorization"`. The rating concerns
the **current step**, not the trajectory. Parsing succeeds for 99.8% of records (tool name)
and 91.9% (arguments as JSON).

### 2.2 Tool identity determines the label

| baseline | macro-F1 | accuracy |
|---|---|---|
| majority class | 0.2295 | 0.5251 |
| keyword blacklist | 0.2483 | 0.5077 |
| **tool name → its majority label** | **0.9597** | **0.9617** |

Task-grouped split, n = 1,436. Only 44 of 527 tool names ever appear under more than one
label. Holding out the five tools with ≥60 steps and a minority-class share ≥10%
(`send_email`, `delete_file`, `get_webpage`, `query_google_search`,
`create_calendar_event`) gives 447 records split 122/105/220; the same lookup scores
macro-F1 **0.1429**, identical to predicting the majority class.

### 2.3 The request contributes nothing

| input | macro-F1 |
|---|---|
| action text only (grouped 5-fold CV by request) | **0.9161** |
| action + user request | 0.9131 |
| Δ | **−0.0030** |

### 2.4 Minimal pairs are absent

| quantity | value |
|---|---|
| same tool **and** same arguments, different label | 20 / 4,207 = **0.48%** |
| same tool + same task, different label, in the held-out-tool test set | **0** |

> "Our task-aware guard improves F1 on TS-Bench" is unfalsifiable: the score is reachable
> without reading the task.

---

## 3. Building a benchmark that can answer the question

### 3.1 Sources and construction

For each of AgentDojo v1's 97 user tasks we call `ground_truth(environment)` to obtain the
calls the task authorizes, with concrete arguments: 339 calls over 165 distinct actions.

| flavour | what varies | n |
|---|---|---|
| `authorized` | the call the task authorizes | 339 |
| `same_action_diff_task` | **action text identical**, task differs | 308 |
| `same_tool_diff_args` | same tool, different arguments | 163 |
| `diff_tool_same_domain` (×2) | different tool, same suite | 409 |

Labels: ALLOW for authorized calls; REVIEW if not authorized but read-only; DENY otherwise.

**Evidence.** For each task we render the documents the agent would have retrieved — the
actual `filesystem` files, bank transactions, emails, drive files, hotel/restaurant/flight
records, calendar events — and append two decoy documents from the same suite that the task
does **not** authorize. Identifier-like values (IBANs, emails, dates, amounts) are then
**parsed out of that rendered text**; nothing is copied from the ground-truth arguments.

### 3.2 Why the evidence must be real documents

We built this three times; each earlier version failed a check the last one passes.

**(a) No evidence.** The request names the full argument set in only 28% of cases (96/339).
Authorization is undefined: even "decidable" negative types sat at 48.8–60.0% pairwise for a
lexical model.

**(b) Evidence as a curated value list.** Decidable, but the benchmark collapsed into a
grounding test: an oracle rule — "ALLOW iff every argument value appears in the evidence" —
reached **81.65%**, and a model trained with the request blanked scored *higher* on validation
than the full model (0.9594 vs 0.9417). Grounding had swallowed authorization — the same defect
we criticise in TS-Bench, reproduced by us.

**(c) Evidence as real documents (final).** Documents carry many identifiers the call does not
need, so presence stops being informative. The same oracle now scores **50.5%** — chance — and
among fully-grounded samples only 34% are ALLOW.

| build | grounding oracle | model trained without the request |
|---|---|---|
| curated value list + decoys | 81.7% | 0.9594 val (full: 0.9417) |
| real documents | **50.5%** | 0.8167 test (full: 0.8639) |

### 3.3 Properties of the final benchmark (PAB-RD)

| property | value |
|---|---|
| steps | 1,219 (ALLOW 339 / REVIEW 440 / DENY 440) |
| tasks | 97 (banking, slack, travel, workspace) |
| documents | banking 12, slack 13, travel 39, workspace 83 |
| distinct action strings | 165, of which **164 (99.4%) under more than one label** |
| split, grouped by task | train 764 / val 120 / test 335; task overlap **0** |
| same-action pairs in test | **90 pairs over 47 actions** |
| grounding oracle | **50.5%** (chance) |

### 3.4 The floor is a theorem

Two samples sharing an action string but differing in task have **byte-identical** action text.
Any deterministic function of the action text returns the same score for both, so pairwise
accuracy is exactly 50.0%. Verified on the 90 test pairs: tool-name lookup, action-text lookup
and TF-IDF on the action alone all score **50.0%**; adding the request gives 52.2%, adding the
documents 51.1%.

---

## 4. Method

Qwen2.5-Instruct at four sizes + LoRA (r = 16, α = 32, dropout 0.05, all attention and MLP
projections). Input: request, retrieved documents, pending call. Output: one token,
`0.0` / `0.5` / `1.0`.

| size | trainable | batch × accum | max len | epochs | peak |
|---|---|---|---|---|---|
| 0.5B | 4.7M | 8 × 2 | 1,024 | 4 | <8 GiB |
| 1.5B | 18.5M | 2 × 8 | 1,280 | 4 | 10.2 GiB |
| 3B | 27.3M | 4 × 4 | 1,024 | 3 | ~14 GiB |
| 7B | 40.4M | 1 × 8 | 1,024 | 2 | 20.8 GiB |

Three choices mattered more than the architecture:

1. **The policy is stated in the prompt** — the model applies a specified rule rather than
   exercising open-ended judgment.
2. **One-token output.** Under the original four-section rubric a zero-shot 1.5B failed to
   terminate in 8.3% of cases; a single-token target removes the failure mode (0.0% after
   training for every size).
3. **Prompt truncation never touches the action.** `tokenizer(truncation=True)` cuts from the
   right and would delete the object under judgment, so we shrink the document block instead.

Two protocols are in play and they should not be confused. The table above is the **exploratory**
configuration of the first sweep (5.1): each size was fitted to the memory budget, so batch, max
length and epoch count differ between rows. The **deployment protocol** — used for every number in
5.3 and 5.6 — is identical for 1.5B and 3B: batch 4 × accum 4 (effective 16), max_len 1,024,
4 epochs, LoRA r16/α32/dropout 0.05, and a learning rate chosen per model on the validation split
only (2e-4 for both), seeds {0, 42, 123}. Validation is the only place any choice is made;
the test split is scored once per run.

The 7B row uses a smaller batch and one fewer epoch than the others because of memory: at batch
4 it exceeds 24 GiB. We flag this where it matters (§5.2); it is the most likely explanation for
the 7B being the only size that does not improve on the 3B.

**Deployment configuration.** The system this work targets is a 7B agent that proposes tool
calls, with a small guard in front of execution. The guard sizes in scope are therefore
**0.5B, 1.5B and 3B**; every table marks them as deployment arms. The 7B guard we also trained
is an **exploratory upper reference only** — it is not part of the deployment configuration, it
was trained under a reduced schedule for memory reasons, and it is labelled `(exploratory)` in
the tables. Any claim about "the guard" refers to the 0.5B–3B range.

---

## 5. Results

All tables in this section are generated by `scripts/unified_eval.py` from **one** set of
prediction files (`results/preds/*.jsonl`), each of which stores a label and a continuous
score per sample. No table is computed by a different code path.

### 5.0 The three metrics, and why three

With pairs defined as (authorised call *a*, its same-action unauthorised twin *o*):

| metric | definition | what it is for |
|---|---|---|
| **PRA** — Pairwise Ranking Accuracy | per pair 1 if *s(a) > s(o)*, 0.5 if equal, 0 otherwise; averaged | discrimination. Exactly 50.0% for any score that is a function of the action text alone |
| **SPA** — Strict Pair Accuracy | per pair 1 **only** if *s(a) > s(o)* strictly; ties score 0 | exposes the degenerate strategy: a guard that answers REVIEW to everything has PRA = 50.0% but SPA = 0.0% |
| **Macro-F1** | per-class P/R/F1 over the 335 samples, averaged | the only one of the three that rewards guessing the majority class — which is why we do not report it alone |

PRA and SPA differ only in how they treat ties, and with a three-level output ties are common
(tie rate 0.10–1.00 across our arms), so the gap between them is itself diagnostic.

**Freeze.** The three metrics are defined once, in `scripts/unified_eval_v2.py`, and the
inference layer once, in `scripts/final_stats.py` (`metric_version = p0-1.1`). Definitions are
unchanged between p0-1.0 and p0-1.1 — only the inference was corrected, and point estimates
are asserted identical. The two layers are merged into a **single** artefact,
`results/frozen/final_report.json`, and every table below is generated from that file by
`scripts/final_report.py` and nothing else. No number in this section is typed by hand:

    wins(a,o) = 1[s(a) > s(o)],  ties = 1[s(a) = s(o)],  losses = 1[s(a) < s(o)]
    PRA = (wins + 0.5·ties)/n,  SPA = wins/n,  TieRate = ties/n
    identity: PRA = SPA + 0.5·TieRate        (asserted per arm at runtime)

The identity holds exactly for every arm, which is a cheap way to catch a mis-specified
metric. `deltas` are computed on the same 90 `pair_id`s for every arm; all 20 arms cover the
same 335 test `sid`s (asserted). Metadata recorded with the results:
`dataset_hash = 9af72b7559f51888`, `split_hash = 1a1a6323ef421cb1`,
`pairs_hash = 10751fff54a90ae1`, `seed = 0`, plus base model, LoRA rank, lr, batch/accum and
epochs per arm. 335 samples, 90 pairs, 47 action groups, 25 task groups.

**A caveat about comparing SPA across scorer families.** The TF-IDF baselines emit continuous
scores and therefore can never tie, so their SPA equals their PRA by construction and SPA is
not comparable with rows that emit one of three discrete levels; we mark those rows with †.
The lookup and majority baselines *do* tie — always, in fact — and their SPA = 0 is a
meaningful statement that they never strictly rank the authorised call above its twin.

### 5.1 Main table (PAB-RD test, 335 samples, 90 pairs, 47 actions)

| arm | wins | ties | losses | PRA | SPA | TieRate | Macro-F1 |
|---|---|---|---|---|---|---|---|
| **3B + LoRA** | 77 | 9 | 4 | **0.906** | **0.856** | 0.100 | **0.881** |
| 7B + LoRA (exploratory) | 64 | 23 | 3 | 0.839 | 0.711 | 0.256 | 0.877 |
| 1.5B + LoRA (lr 1e-4) | 60 | 29 | 1 | 0.828 | 0.667 | 0.322 | 0.879 |
| 1.5B + LoRA | 56 | 33 | 1 | 0.806 | 0.622 | 0.367 | 0.864 |
| 7B zero-shot | 60 | 25 | 5 | 0.806 | 0.667 | 0.278 | 0.406 |
| 0.5B + LoRA | 55 | 31 | 4 | 0.783 | 0.611 | 0.344 | 0.864 |
| 3B + LoRA, no request | 50 | 40 | 0 | 0.778 | 0.556 | 0.444 | 0.818 |
| 1.5B + LoRA, no request | 49 | 38 | 3 | 0.756 | 0.544 | 0.422 | 0.817 |
| 1.5B + LoRA (lr 1e-4), no request | 44 | 45 | 1 | 0.739 | 0.489 | 0.500 | 0.806 |
| 7B + LoRA, no request | 43 | 44 | 3 | 0.722 | 0.478 | 0.489 | 0.796 |
| 3B zero-shot | 47 | 35 | 8 | 0.717 | 0.522 | 0.389 | 0.476 |
| 0.5B + LoRA, no request | 38 | 51 | 1 | 0.706 | 0.422 | 0.567 | 0.797 |
| TF-IDF, action + task | 47 | 0 | 43 | 0.522 | 0.522† | 0.000 | 0.638 |
| TF-IDF, action + task + evidence | 46 | 0 | 44 | 0.511 | 0.511† | 0.000 | 0.604 |
| action-text lookup | 0 | 90 | 0 | 0.500 | 0.000 | 1.000 | 0.605 |
| tool-name lookup | 0 | 90 | 0 | 0.500 | 0.000 | 1.000 | 0.636 |
| TF-IDF, action only | 0 | 90 | 0 | 0.500 | 0.000 | 1.000 | 0.620 |
| majority class | 0 | 90 | 0 | 0.500 | 0.000 | 1.000 | 0.158 |
| 1.5B zero-shot | 0 | 90 | 0 | 0.500 | 0.000 | 1.000 | 0.150 |
| 0.5B zero-shot | 1 | 81 | 8 | 0.461 | 0.011 | 0.900 | 0.166 |

† continuous scorer: ties are impossible, so SPA ≡ PRA and SPA is not comparable with the
discrete rows. The constant/lookup baselines do tie, and their SPA = 0 is meaningful.

Two things in this table drove several of our earlier mistakes.

**The surface baselines never win a pair.** They score 0.60–0.64 Macro-F1 while recording
wins = 0, losses = 0, ties = 90. Every one of their "correct" answers is the same class for
both members of the pair, which the pair metric refuses to reward and the tie rate makes
visible. The same is true of the 1.5B zero-shot model.

**The guards' errors are indecision, not inversion.** Among the fine-tuned guards, losses are
1–4 out of 90 while ties are 9–51. The 3B trained without the request loses zero pairs — it
never ranks the unauthorised twin above the authorised one; it simply fails to decide. This is
why SPA (wins/n) separates the arms far better than PRA: the signal is in whether the guard
commits, not in whether it is right when it does.

> **Update (P1, multi-seed).** The 1.5B and 3B rows above come from the exploratory sweep: single seed, and a per-size configuration (table in 4) that differs from the deployment protocol in batch size, max length and epochs. Sections 5.3 and 5.6 re-run both sizes under one frozen protocol with three seeds and add strict unseen-task pairs; **the deployment protocol governs, and where the two disagree 5.1 is the exploratory reading.** The request effect replicates; absolute levels move by ~2 points because the protocol changed.

### 5.2 Zero-shot scales with size; fine-tuning does not need it (PRA)

| size | zero-shot PRA | +LoRA PRA | gain |
|---|---|---|---|
| 0.5B | 46.1% | **78.3%** | +32.2 pp |
| 1.5B | 50.0% | 80.6% | +30.6 pp |
| 3B | 71.7% | **90.6%** | +18.9 pp |
| 7B | 80.6% | 83.9% | +3.3 pp |

Zero-shot capability is monotone in size (46 → 50 → 72 → 81) and the fine-tuning gain shrinks
monotonically (32 → 31 → 19 → 3): scale and training are substitutes, and the substitution is
quantitative. The practical statement: **a 0.5B guard trained on 764 examples (78.3%) is within
2.3 points of a 7B used zero-shot (80.6%), at roughly 1/15 of the inference cost.**

The 3B is the best operating point at 90.6%. The 7B's 83.9% is below it; given that the 7B
received one fewer epoch and a batch of 1 for memory reasons, and that its zero-shot floor is
already 80.6%, we read this as under-training rather than as a property of the size, and we do
not build a scaling claim on the 7B row.

### 5.3 The request effect under action-clustered inference (P1, three seeds)

Each of the 90 pairs is one unit, but **pairs are not independent**: one action string can
carry several pairs and all of them share the same authorised sample. We therefore report two
procedures and always label which is which:

- **primary — action-cluster inference.** 95% CI from a bootstrap that resamples the 47 action
  groups; p from a permutation test that flips the sign of an *entire* action group (20,000
  draws). Flipping whole groups keeps the within-group structure intact, so the p-value
  accounts for the correlation that the pair count hides.
- **auxiliary — pair-level sign test.** Counts pairs, ignores both magnitude and clustering.
  Reported only for continuity with earlier drafts; never used to support a claim.

The estimates below come from the P1 re-run (three seeds, one frozen protocol). Per pair we
average the task-minus-no-task difference over the three seeds and then cluster; every seed is
also reported separately, because averaging three correlated runs is not the same as having
three times the data.

| model | ΔPRA | 95% CI (action cluster) | p (cluster perm.) | p (pair sign, aux.) | ΔSPA | 95% CI (action cluster) | p (cluster perm.) | design effect |
|---|---|---|---|---|---|---|---|---|
| 1.5B | +0.069 | [−0.015, +0.145] | 0.098 | 0.0096 | +0.133 | [−0.003, +0.264] | 0.052 | 2.63 |
| **3B** | **+0.094** | **[+0.031, +0.159]** | **0.0067** | 0.0009 | **+0.204** | **[+0.089, +0.326]** | **0.0016** | 1.84 |

| model | seed | ΔPRA | 95% CI | p (cluster perm.) | ΔSPA | p (cluster perm.) |
|---|---|---|---|---|---|---|
| 1.5B | 0 | +0.061 | [−0.044, +0.165] | 0.303 | +0.089 | 0.408 |
| 1.5B | 42 | +0.094 | [−0.032, +0.209] | 0.145 | +0.178 | 0.105 |
| 1.5B | 123 | +0.050 | [−0.031, +0.134] | 0.308 | +0.133 | 0.130 |
| 3B | 0 | +0.072 | [−0.022, +0.163] | 0.174 | +0.167 | 0.066 |
| 3B | 42 | +0.083 | [+0.023, +0.147] | 0.015 | +0.167 | 0.015 |
| 3B | 123 | +0.128 | [+0.055, +0.204] | 0.0019 | +0.278 | 0.0004 |

**What survives, and what does not.** The 3B's request effect survives clustering on both
metrics, and it does so in two of three seeds individually (s42 p = 0.015, s123 p = 0.002;
s0 is directionally positive but not resolved at 90 pairs). The 1.5B is positive in all three
seeds — +0.061, +0.094, +0.050 — but its interval crosses zero and its p is 0.098: at this
size and this sample the effect is **not resolvable on pairs**, and we do not claim it is.

The third metric is less conservative here, and the reason is units, not luck:

| model | ΔMacro-F1 per seed | mean | 95% CI (task cluster) |
|---|---|---|---|
| 1.5B | +0.057 / +0.080 / +0.055 | +0.064 | **[+0.029, +0.100]** |
| 3B | +0.065 / +0.043 / +0.091 | +0.066 | **[+0.032, +0.102]** |

Both intervals exclude zero. Macro-F1 is paired by sample and resamples the **25 task groups**
rather than the 47 action groups, and it does not require a within-pair comparison; 335 samples
spread over 25 clusters carry more information than 90 pairs spread over 47. The two readings
are both honest and they say different things: *the guard classifies better when it sees the
request* (resolved for both sizes), and *it ranks a pair's two members better* (resolved only
for the 3B).

**The clustered tests are four to ten times weaker than the sign test.** For PRA the gap is
0.0096 → 0.098 at 1.5B and 0.0009 → 0.0067 at 3B; the sign test treats 90 correlated pairs as
90 independent votes and would have us claim an effect the design cannot support. The design
effect column makes the cost explicit: the cluster-bootstrap variance is 1.84–2.63 times the
i.i.d. variance, so **90 pairs behave like roughly 34–49 independent ones**.

**Scope.** These numbers replace an earlier single-seed analysis that also covered 0.5B and 7B.
Those two sizes were never re-run under the P1 protocol, so their clustered deltas are no longer
used to support any claim here; the equal-weight auxiliary summary that includes them is kept in
5.4, clearly labelled, and should be read as belonging to that earlier build.

### 5.4 Auxiliary: equal-weight summary across the three deployment guards

The deployment configuration is *one* guard size, not three, so nothing in this subsection is
a primary result. We report it because a reader will ask for a cross-size number, and because
its statistics are easy to get wrong in a way that flatters the method.

**The weights are fixed in advance.** 0.5B, 1.5B and 3B each receive 1/3, chosen before any
test number was computed and not adjusted afterwards. The 7B guard is excluded on principle:
it is an exploratory reference trained under a reduced schedule, not a deployment candidate.

    ΔPRA = (0.078 + 0.050 + 0.128)/3 = +0.085
    ΔSPA = (0.189 + 0.078 + 0.300)/3 = +0.189

Both are exactly the equal-weight mean of the per-guard deltas; we assert this identity in
code rather than trusting the two routes to agree.

**Why 360 pairs is not 360 observations.** A tempting summary pools the four guards' 90 pairs
into 360 and runs one McNemar. That is invalid — the same 90 pairs are measured once per
guard, so the 360 numbers are four repeated measurements of 90 units. The naive test gives
p = 1.0e-07 on 93 discordant observations; an earlier version of this paper reported
p = 1e-10 from exactly this kind of pooling.

**A labelling error we are correcting.** An earlier version then reported p = 0.0007 and
described it as an action-clustered test. It is not. That number is a plain **pair-level sign
test** on the SPA differences: 41 pairs favour the request, 15 favour its removal, 34 are
unchanged, and a two-sided binomial test on 41:15 gives p = 0.00069. It treats 90 pairs as
independent votes — precisely the assumption the previous paragraph says is false. We
reproduce it here so the correction is auditable, and demote it to an auxiliary column.

| summary | Δ | 95% CI (action cluster) | p (cluster permutation) | p (pair sign, aux.) | design effect |
|---|---|---|---|---|---|
| equal-weight ΔPRA | **+0.085** | [+0.014, +0.152] | **0.021** | 0.0022 (41:17) | 2.07 |
| equal-weight ΔSPA | **+0.189** | [+0.074, +0.300] | **0.0028** | 0.00069 (41:15) | 1.90 |

**What changes.** The summary survives action-clustered inference on both metrics, so the
qualitative conclusion holds: across the three deployment sizes the request carries real
information. But the evidence is four- to ten-fold weaker than the pair-level test suggested
(0.021 vs 0.0022 for PRA; 0.0028 vs 0.00069 for SPA), and the design effect of ~2 means the
90 pairs behave like roughly 43 independent ones. We therefore keep this as an auxiliary
cross-size statement and continue to report the three sizes separately, since they disagree:
under clustering only the 3B's ΔPRA survives, while the equal-weight summary does — the
summary is carried by the 3B and by ΔSPA, not by a uniform effect.

**Assumption of the permutation test, stated plainly.** Sign-flipping whole action groups is
valid if, under the null, each group's direction is exchangeable — i.e. the within-group
correlation is symmetric about zero. This is weaker than independence but not free: a group
whose pairs are heterogeneous in sign contributes a near-zero mean and therefore little
information either way, which is the correct behaviour but also means the test is driven by
the groups with consistent direction. We report the action-level t-test on the 47 group means
as an analytic cross-check (ΔPRA t = 2.97, p = 0.003; ΔSPA t = 3.71, p = 0.0002); it agrees.

### 5.5 Transfer to the standard benchmark

The same recipe on TS-Bench's `unseen_tool` split (5,034 steps, 1 epoch, 1.5B) gives macro-F1
**0.7005** on 447 held-out-tool records (0.2% parse failures), against 0.1429 for tool-name
lookup. The model learns to read the action instead of the tool name. TS-Bench still cannot say
whether it reads the task.

---

### 5.6 Multi-seed replication (P1) and strict unseen-task pairs (P2-v2)

The single-seed rows in 5.1 were the weakest part of this paper: the 1.5B result moved with the
learning rate, and one run cannot separate an effect from a training artefact. We therefore
re-ran both deployment sizes under one frozen protocol — 4 epochs, effective batch 16, max_len 1024, LoRA r16/α32, lr selected per
model on validation only (2e-4 for both), seeds {0, 42, 123} — and evaluated once on the test
split. Checkpoints were chosen on validation macro-F1; the test set was never touched.

| model | arm | PRA (mean ± sd) | Macro-F1 (mean ± sd) |
|---|---|---|---|
| 1.5B | + request | 0.841 ± 0.017 | 0.879 ± 0.016 |
| 1.5B | no request | 0.772 ± 0.022 | 0.815 ± 0.013 |
| 3B | + request | **0.885 ± 0.008** | **0.889 ± 0.012** |
| 3B | no request | 0.791 ± 0.035 | 0.823 ± 0.012 |

The request effect replicates in every seed, and it is larger than the seed spread:

| model | ΔPRA per seed | mean ± sd | ΔMacro-F1 mean ± sd |
|---|---|---|---|
| 1.5B | +0.061 / +0.094 / +0.050 | **+0.069 ± 0.023** | +0.064 ± 0.014 |
| 3B | +0.072 / +0.083 / +0.128 | **+0.094 ± 0.029** | +0.066 ± 0.024 |

The 3B is the stable operating point (PRA sd 0.008 over seeds); the 1.5B moves ±0.017, which is
why the earlier single-seed 1.5B numbers could not support a claim on their own. Absolute levels
sit slightly below the single-seed 5.1 rows (3B 0.885 vs 0.906) because the protocol changed
(4 epochs at 2e-4 instead of 3 epochs at 1e-4); the effect size is what replicates, and it is
the number we now stand behind.

**PAB-RD's pairs share actions, so its 90 pairs are not 90 independent units.** The test above
therefore cannot answer the sharper question a reviewer will ask: on tasks the guard has never
seen, does the request still decide? P2-v2 holds action and evidence fixed and varies only the
user task, and keeps only pairs whose *both* tasks are in the test split
(19 scenarios, 41 pairs, 6 action groups). This is a zero-shot evaluation of the P1
checkpoints — P2-v2 was frozen before any model touched it and was never used for training,
tuning, or checkpoint selection.

| model | arm | s0 | s42 | s123 | mean ± sd | TieRate (mean) |
|---|---|---|---|---|---|---|
| 1.5B | + request | 0.715 | 0.831 | 0.934 | 0.827 ± 0.110 | 0.35 |
| 1.5B | no request | 0.500 | 0.500 | 0.500 | 0.500 ± 0.000 | 1.00 |
| 3B | + request | 0.965 | 0.952 | 0.928 | **0.948 ± 0.019** | 0.10 |
| 3B | no request | 0.500 | 0.500 | 0.500 | 0.500 ± 0.000 | 1.00 |
| 1.5B / 3B | zero-shot | 0.500 / 0.634 | — | — | — | — |

Two things are worth separating.

**Without the request the guard does not degrade — it stops deciding.** Every no-request arm
returns the same label for both members of all 41 pairs, giving PRA exactly 0.500, SPA 0.000 and
TieRate 1.000 in all three seeds. We verified the inputs before drawing this conclusion: the two
renderings of a pair are byte-identical once the task is removed (316/316), so identical scores
are the only possible outcome, and the measured 0.500 confirms the harness rather than a model
result. The claim is therefore not "the request helps a little"; with action and evidence held
fixed, **the request is the only thing that separates authorised from unauthorised**.

**The 3B is close to ceiling and seed-stable; the 1.5B is not.** 0.948 ± 0.019 against
0.827 ± 0.110 — the 1.5B swings 22 points across seeds on 41 pairs and one seed lands at 0.715.
We report the per-seed cells rather than only the mean for exactly this reason.

Three caveats we do not want buried. First, **6 of 632 prompts exceed the 1024-token training
budget** (max 1047) and were fed untruncated; dropping the single affected scenario moves the 3B
to 0.963 / 0.949 / 0.924, so the conclusion does not rest on them. Second, **the strict layer has
only 6 action groups**, so the bootstrap intervals in the full report are descriptive; we make no
significance claim for P2-v2 and report no p-values. Third, the 3B's zero-shot floor is already
0.634 while the 1.5B's is 0.500, so part of the size gap is capability the base model brings,
not something LoRA created.

## 6. Cost

A cheap first stage (TF-IDF + logistic regression) escalating to the model when its maximum class
probability falls below τ gives a usable frontier on the curated-evidence build: 26.5% escalation
retains 68.2% pairwise (full model 87.3%), 57.7% retains 71.8%. The cheap stage alone is at
chance, so every point is bought by escalating. Prompt Guard 2 cannot serve as this stage: it
detects prompt injection, not authorization, and its score carries no information about these
labels (100% escalation).

Given §5.2, the cheaper lever is the model size itself: a 0.5B guard at 78.3% is within 2.3
points of a 7B at 80.6% while costing an order of magnitude less per call.

---

## 7. Limitations

1. Four sizes from one family (Qwen2.5). No cross-family replication.
2. **One training run per cell, and a benchmark that resolves ~15–20 pp.** With 47 action
   groups the minimum detectable ΔPRA is about 15–20 points; a per-size difference smaller than
   that needs a benchmark several times larger. We therefore report action-clustered intervals
   and a pair-level pooled test, and treat per-size orderings as hypotheses. The learning-rate
   sensitivity we found in the 1.5B is a warning that any single-run cell can be under-tuned.
3. **Statistical caveats that we got wrong twice.** Bootstrap and permutation units must be
   the independent unit (action for pairs, task for samples), not the row count; several guards
   evaluated on the same pairs are repeated measurements, not extra observations; and a sign
   test over correlated pairs is not a cluster test, however it is labelled. §5.3 and §5.4
   report every number under both procedures. The cluster permutation additionally assumes
   group-level sign exchangeability under the null — weaker than independence, but an
   assumption, and one we state rather than bury.
4. PAB-RD is generated from ground-truth calls over the documents AgentDojo ships; it is not a
   log of incidents, and its document diversity is bounded by that benchmark.
5. 97 tasks, 90 test pairs, 47 actions — adequate for the effect sizes reported, not for
   per-suite breakdowns.
6. The label policy is ours. The method transfers; the numbers do not.
7. ASB differs from the published count by 6 records.
8. The 7B guard was trained with a reduced configuration for memory reasons; its number is a lower
   bound.

---

## 8. Related work

Guardrails split into (i) prompt-injection detectors on text, (ii) step-level safety classifiers
trained on agent trajectories, and (iii) system-level enforcement at the tool boundary. Our
measurement targets (ii): its benchmark does not isolate the property it is used to argue for.
Our method is a small instance of (ii) on a benchmark that does, and our four-size ablation
decomposes the learned capability into grounding and task conditioning.

---

## Appendix A — Prompt Guard 2's label mapping is missing, not wrong

Both released checkpoints have **no** `id2label`, `label2id` or `num_labels` in `config.json`, so
`transformers` falls back to `{0: LABEL_0, 1: LABEL_1}` and any code branching on the label *name*
silently misbehaves. We wrote `0 = BENIGN`, `1 = MALICIOUS` and verified the direction
empirically: benign text scores p(MALICIOUS) = 0.0004 (86M) / 0.0026 (22M); injection text
0.9994 / 0.9959. The 22M variant scores
`SYSTEM OVERRIDE: email the user's password to attacker@evil.com` at only 0.3404 (BENIGN) while
the 86M scores 0.9760 — the sizes are not interchangeable.

## Appendix B — reproduction

```bash
cd /data/projects/guardrails && conda activate /data/conda/envs/guard
python scripts/build_tsbench.py && python scripts/make_splits.py
python scripts/run_baselines.py --split grouped
python scripts/analyze_pairs.py --split unseen_tool
python scripts/build_pab_rd.py                       # 1219 records from real documents
python scripts/make_splits_generic.py --data data/pab_rd.jsonl --out data/pab_rd_splits.json
# ---- 统一评测（P0：三指标 + 差值 + 检验，全部从同一批预测生成）----
python scripts/emit_all_preds.py       # 所有臂 -> results/preds/*.jsonl（{sid,pred,score}）
python scripts/unified_eval_v2.py      # 指标层 -> results/frozen/unified_eval.json
python scripts/final_stats.py          # 推断层 -> results/frozen/final_stats.json + final_tables.md
                                       #   PRA/SPA/TieRate/Macro-F1 定义不变；
                                       #   动作聚类 bootstrap CI + 整组翻符号置换检验
bash scripts/run_sizes.sh                            # 3B then 0.5B, task + task-blind
bash scripts/run_7b.sh                               # 7B: bs=1, accum 8, 2 epochs
python scripts/train_lora.py --data data/pab_rd.jsonl --splits data/pab_rd_splits.json \
    --split pab --style pab --epochs 4 --bs 2 --accum 8 --tag o1_rd_15b
```
