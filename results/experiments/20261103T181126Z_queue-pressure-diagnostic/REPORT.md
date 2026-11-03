# Queue Pressure Diagnostic Report

## 1. Diagnosis of zero estimates in the previous quick experiment

**Diagnosis:** both event timing and placement caching mattered. The prior high-load quick run (30 UE, 1 s) logged all 30 Queue-Aware selections at simulation time 0.06 s with active tasks=0, waiting queue=0, and estimated wait=0. The first task payloads had not reached EDC execution yet. Its horizon ended at 1 s, before the next decision window observed in this diagnostic (1.06 s).

The estimator itself reads the current `activeTasks` map and `getTasksQueue()`; it did not hide a populated queue at its observed decision points. PureEdgeSim `DefaultComputingNode.submitTask()` starts work if a core and RAM are available, otherwise adds to `tasksQueue` (lines 222–236); `executionFinished()` removes the FIFO head and starts it (lines 275–304). QueueAware tracks start/finish in `startExecution()`/`executionFinished()` and computes active remaining service plus the current waiting list in `estimateQueueWaitSeconds()` (`QueueAwareComputingNode.java`, lines 37–72).

`DefaultSimulationManager.sendFromOrchToDestination()` calls the orchestrator only if `isApplicationPlaced()` is false; otherwise it reuses the saved destination (lines 294–320). `setFailed()` clears that placement for a later task (lines 419–435); mobility can also clear it in `LocationAwareNode.connectWith()` (lines 53–60). The trace confirms deadline failures before later re-placement: for source UE 26, tasks 401–420 fail at 0.2225/0.235 s; task 421 is policy-selected at 1.06 s. Thus the previous zero is best explained by **early initial selection + a short horizon before a later failure-triggered re-placement**, not by a broken queue accessor. The longer run's lifecycle trace records 2,131 queue-entry events for each method.

## 2. Changes Made

- `QueueAwareTradeOffOrchestrator.findComputingNode()` now additionally calculates and logs, without changing selection behavior: λ×wait penalty, baseline/combined candidate ranks, whether rank order changes, baseline vs selected candidate ID, whether the selected candidate changes, and `placement_cache_used=false` for calls that enter the selector.
- `PaperAlignedSimulationManager.recordQueueCandidate()` writes those fields plus estimate timestamp, active-task count, and waiting-queue length to `raw/queue_decisions.csv`.
- No estimator formula, task scheduling, queue, baseline properties, or workload profile changed. Trace and audit are observational. The existing lifecycle trace marks each task's `POLICY_SELECTED` or `CACHED_PLACEMENT_REUSED` stage.

## 3. Configuration and Commands

- Experiment ID: `20261103T181126Z_queue-pressure-diagnostic`
- HEAD: `7cd0acabe3255552a79f33dd55dc31612833914b`; working tree dirty. Both runs have identical configuration hashes and simulator properties; method and queue audit settings are the intended differences.
- Profile `paper-aligned-baseline`; 30 UE (high), 4 configured EDC, target `EDGE_DC_ONLY`; seed 1; duration 5 s; Queue-Aware λ=1.0 (Trade-Off has no λ).
- This is a staged increase from the prior same-seed 30 UE/1 s quick result to 30 UE/5 s. The baseline application/device properties were not changed; `simulation_time` was set by the documented duration CLI option.
- Exact commands (the local environment prefixed a Maven-offline wrapper because its Maven cache is read-only):

```bash
PAPER_TASK_EVENT_TRACE=1 RUNS_ROOT=results/experiments/20261103T181126Z_queue-pressure-diagnostic/runs ./run.sh --profile paper-aligned-baseline --method trade-off --devices 30 --duration-seconds 5 --destination-config EDGE_DC_ONLY --seed 1 --queue-weight 1.0
PAPER_TASK_EVENT_TRACE=1 RUNS_ROOT=results/experiments/20261103T181126Z_queue-pressure-diagnostic/runs ./run.sh --profile paper-aligned-baseline --method queue-aware --devices 30 --duration-seconds 5 --destination-config EDGE_DC_ONLY --seed 1 --queue-weight 1.0
```

The actual prefixed commands are preserved in `commands_run.txt`; full console output is in `trade-off_console.log` and `queue-aware_console.log`.

## 4. Queue Signal, Ranking, and Destination Evidence

Queue-Aware made 77 policy-selection calls and emitted 111 candidate observations at times 0.06, 1.06, 2.06, 3.06, and 4.06 s. The initial 42 candidate rows at 0.06 all had queue length 0 and wait 0. At later decision windows the queue was visible: candidate queue wait ranged **0.00–4.18 s**, with **58/111** nonzero candidate observations; selected candidates had **0.00–4.18 s**, with **36/77** nonzero selected estimates. Observed waiting queue ranged 0–256 tasks and active task count 0–10. Lifecycle trace additionally records 2,131 queue entries and 1,333 exits in Queue-Aware; these are cumulative events, not instantaneous queue length.

The queue penalty affected scores in 58 candidate rows (λ=1.0). It changed candidate rank order in **14/77** decisions and changed the selected candidate relative to the same decision's baseline scores in **14/77** decisions. These are counterfactual comparisons within Queue-Aware's candidate set; they do not imply every score change alters the winner.

Concrete decision evidence, task 421 at 1.06 s (`raw/queue_decisions.csv`): EDC 2 had baseline score 0.150, queue estimate/penalty 0.555, combined score 0.705, rank 1→2; EDC 4 had baseline score 0.150, estimate/penalty 0, combined score 0.150, rank 2→1. The selector chose EDC 4 instead of baseline-score winner EDC 2. `raw/destinations.csv` confirms task 421 went to EDC 4 under Queue-Aware and EDC 2 under Trade-Off. The task-event trace marks this selection `POLICY_SELECTED`; subsequent tasks commonly show `CACHED_PLACEMENT_REUSED` (2,098 such events in Queue-Aware). This is evidence of queue-aware **application re-placement** at failure-triggered selection points, not an independent policy call for every task.

## 5. Results

Completion rate = completed/generated. Failed are terminal failures; pending are unresolved at the 5-second horizon. Energy is simulator computing-node energy (Wh; network energy is separate). Delay is simulator average completed-task total delay (s): accumulated network + queue waiting + CPU. Destination counts are task rows in `raw/destinations.csv`. Queue estimate min/max/count covers candidate rows; Trade-Off does not expose this estimator, so those fields are N/A.

| Method / workload | Generated | Completed | Failed | Pending | Completion | EDC1 / EDC2 / EDC3 / EDC4 | Queue estimate min–max; nonzero candidate rows | Rank changed / selected changed | Energy Wh | Avg total delay s | Avg completed wait s |
|---|---:|---:|---:|---:|---:|---|---|---:|---:|---:|---:|
| Trade-Off / high | 2,175 | 122 | 1,159 | 894 | 5.61% | 715 / 765 / 405 / 290 | N/A | N/A | 3.0565 | 6.7463 | 1.1736 |
| Queue-Aware / high | 2,175 | 117 | 1,193 | 865 | 5.38% | 625 / 705 / 495 / 350 | 0–4.18 s; 58/111 | 14/77 / 14/77 | 3.0750 | 6.7867 | 1.2142 |

Queue-Aware selected-estimate summary: 0–4.18 s, 36/77 selected estimates nonzero; mean selected estimate 0.7420 s; mean selected waiting-queue length 47.82. Per-node CPU utilization is not in these run outputs.

## 6. Quick Comparison

Queue-Aware minus Trade-Off: completion **−0.23 percentage point** (−5 completed), terminal failures **+34**, pending **−29**, energy **+0.0185 Wh**, total delay **+0.0405 s**, completed-task wait **+0.0406 s**. Allocation shifted among EDCs, and task 421 is one verified changed destination. One seed only: these measurements are descriptive, not evidence of general superiority or inferiority. The diagnostic does show nonzero pressure can enter the ranking and can change the selected EDC at re-placement.

## 7. Limitations and Next Step

One seed and one high-workload duration do not estimate variance. Queue estimates are model-based (active remaining service plus FIFO queued task lengths); PureEdgeSim also queues when RAM is unavailable, while the estimator's wait formula models service assignment across CPU cores. Re-placement is triggered by application placement invalidation, especially failures, so it is not a per-task dynamic selector. The aggregate delay has the simulator's known event-clock/per-hop interpretation limitation.

**Next experiment:** run the same paired high-load diagnostic over at least five seeds with the now-verified 5-second configuration, then compare paired completion, failure, pending, energy, and the fraction of re-placement decisions whose winner changes. Keep the trace and per-candidate score audit enabled.

## 8. Audit Checklist

- [PASS] Queue estimator observes actual queue state — at 1.06 s, task 421 candidate EDC 2 logs active=10, waiting=49, estimate=0.555 s; current queue list is read by the estimator.
- [PASS] Nonzero queue signal observed — 58/111 candidate estimates and 36/77 selected estimates are >0.
- [PASS] Queue penalty affects candidate scores — 58 candidate rows have positive λ×estimate.
- [PASS] Candidate ranking changes — 14/77 selection decisions have changed rank order.
- [PASS] Selected destination changes — 14/77 counterfactual winners differ; task 421 example verified against Trade-Off's actual destination.
- [PASS] Multiple EDCs receive tasks — all four receive tasks under both methods.
- [PASS] Paired configuration is valid — same seed, UE count, duration, target, simulator properties, and config SHA-256 per pair; both manifests completed with no validation errors.
- [PASS] Outputs and reproduction command exist — manifests, raw CSV/logs, task traces, candidate audit, `diagnostic_summary.csv`, `queue_decision_effects.csv`, and `commands_run.txt` are present.
