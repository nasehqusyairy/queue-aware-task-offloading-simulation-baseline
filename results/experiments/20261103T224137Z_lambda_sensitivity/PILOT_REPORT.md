# Pilot Report — λ=0 Equivalence Gate

**Status: PASS.** Pilot seed 1; 30 UE, 4 EDC, `EDGE_DC_ONLY`, 5 seconds; Trade-Off and Queue-Aware λ=0. Both runs completed with exit 0 and no validation errors. Per-run configurations, console logs, raw output, task traces and destination audit are in `runs/`; exact commands are in `pilot_commands.txt`.

## Implementation check

`QueueAwareScoring.combinedScore()` returns the baseline score directly when `queuePenaltyWeight == 0` (`QueueAwareScoring.java:53–66`). Candidate iteration follows `nodeList` order, as does `DefaultOrchestrator.tradeOff()` (`QueueAwareTradeOffOrchestrator.java:53–70`; `DefaultOrchestrator.java:58–80`). Both selectors retain the first minimum on ties: the baseline updates only for a strict lower score, while `firstMinimum()` does the same (`QueueAwareScoring.java:69–80`). Queue observation occurs before this zero-weight branch, so the audit still records estimates at λ=0.

## Pilot evidence

- Configuration hashes, simulator properties and seed match; 75 policy-selection task IDs match between methods.
- All 2,175 task destination assignments match exactly between Trade-Off and Queue-Aware λ=0.
- Queue-Aware wrote 109 candidate audit rows; all estimates were available, 56 were nonzero, and selected candidates had mean estimate 0.8292 s. Thus λ=0 disables the penalty but does not disable queue observation.
- All 109 baseline and combined scores and ranks match exactly; every logged penalty is zero; all 75 selected candidates match the baseline winner.
- Generated/completed/failed/pending, completion rate, energy, average delay, and actual waiting time match exactly.

The gate is valid. Proceeding to the planned 25-run matrix, with the pilot's Trade-Off and Queue-Aware λ=0 runs counted as two of the 25 cells.
