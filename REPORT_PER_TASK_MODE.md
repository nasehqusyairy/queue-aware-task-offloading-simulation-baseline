# Per-Task Offloading Decision Mode — Validation Report

**Repository commit at start:** `4dff71514fdc01adf08eb902faa3cedb2941e8f2`  
**Simulator:** vendored PureEdgeSim, revision `bcdd239fa301bd7164526dc47685058288c305ef`  
**Scope:** isolated per-task dispatch mode plus deterministic validation policy. No neural network, DQN learning, reward tuning, GNN, or baseline algorithm change.

## 1. Implementation Summary

Added a new opt-in method, `per-task-test`, whose manager bypasses the per-UE placement cache at every task dispatch and asks a policy for a fresh destination. The current policy is `DeterministicTestPolicy`; it rotates through eligible EDC actions by task ID solely to verify mapping and application. It is not DQN or machine learning.

The validation run used a deterministic synthetic workload: 64 tasks from one UE, 30,000 MI each, 0.03-second release spacing, 10 configured UEs, four EDCs, `EDGE_DC_ONLY`, seed 1, and a 5-second horizon. This workload is a plumbing/queue-state validation and is not a performance comparison. A 1-second cutoff run separately validates pending accounting.

## 2. Architecture Changes

| File | Change |
|---|---|
| `experiment/src/com/mechalikh/pureedgesim/simulationmanager/PaperAlignedSimulationManager.java` | Removed `final` so an isolated manager can extend the existing event/destination audit implementation. Existing logic is unchanged. |
| `experiment/src/com/mechalikh/pureedgesim/simulationmanager/DqnReadySimulationManager.java` | Overrides dispatch to clear the UE placement gate before delegating to PureEdgeSim; records task decisions, cache bypass, applied destination, and a task-ID event ledger; validates selected versus applied destination; closes logs at horizon. |
| `experiment/src/com/mechalikh/pureedgesim/experiment/DqnReadyOrchestrator.java` | Builds a stable EDC ID order, eligibility mask, observation, invokes the configured policy, rejects invalid/masked actions, and returns the selected node to PureEdgeSim. |
| `experiment/src/com/mechalikh/pureedgesim/experiment/OffloadingObservation.java`, `DqnStateEncoder.java` | Adds named task and per-EDC observation fields; raw units and normalized values are both preserved. Missing queue/active/estimate values remain null. |
| `experiment/src/com/mechalikh/pureedgesim/experiment/OffloadingPolicy.java`, `OffloadingTransition.java`, `DeterministicTestPolicy.java`, `DqnActionSpace.java` | Adds policy contract, future transition payload, deterministic non-learning validation policy, stable action mapping and fail-closed mask validation. |
| `experiment/src/com/mechalikh/pureedgesim/experiment/DqnReadyComputingNode.java` | Uses the queue-visible node and emits task submission, queue, execution and node-state observations. |
| `experiment/src/com/mechalikh/pureedgesim/experiment/PerTaskValidationTaskGenerator.java`, `PerTaskTestMain.java` | Creates the deterministic single-UE test workload and registers only the new policy mode. |
| `scripts/run.sh`, `scripts/execute_run.py` | Adds opt-in `--method per-task-test`, raw decision/ledger output, and validations for unique decisions, action masks, destination matching, and lifecycle partition. Baseline method branches remain as before. |
| `tests/java/DqnActionSpaceSelfTest.java`, `scripts/test_dqn_foundation.sh` | Adds executable checks for stable ID ordering, valid/masked/out-of-range actions, no-eligible handling, and deterministic action choice. |

No files under `configs/` or historical experiment result directories were modified or overwritten. The only upstream-adjacent change is making the local `PaperAlignedSimulationManager` subclassable; PureEdgeSim upstream source was not edited.

## 3. Per-Task Decision Lifecycle

1. PureEdgeSim emits `SEND_TASK_FROM_ORCH_TO_DESTINATION` to `DqnReadySimulationManager.processEvent`.
2. `DqnReadySimulationManager.sendFromOrchToDestination` snapshots the prior placement, marks the UE unplaced for this dispatch, then delegates to the existing manager method.
3. The existing path calls `edgeOrchestrator.orchestrate(task)`. `DqnReadyOrchestrator.findComputingNode` sorts configured EDCs by stable node ID, computes eligibility and current features, and invokes `OffloadingPolicy.selectAction` once.
4. `Orchestrator.assignTaskToComputingNode` applies the selected `ComputingNode` to `task.setOffloadingDestination` and updates the UE placement field. The manager compares the selected EDC ID with the actual task destination immediately after dispatch returns.
5. The existing PureEdgeSim network, container download, execution, result transfer, failure, deadline and horizon handling continue unchanged.

Relevant references: `DqnReadySimulationManager.sendFromOrchToDestination` and `processEvent`; `DqnReadyOrchestrator.findComputingNode`; PureEdgeSim `Orchestrator.orchestrate/assignTaskToComputingNode`; `DefaultSimulationManager.sendFromOrchToDestination` and `DefaultNetworkModel` transfer methods.

## 4. State Feature Schema

Raw values and initial normalization reference scales:

| Feature | Raw unit | Normalization | Missing-value rule |
|---|---|---|---|
| `task_mi` | MI | `/ 30,000` | Task API value required. |
| `input_size_bits` | bits | `/ 160,000` | Task API value required. |
| `deadline_seconds` | simulated seconds | `/ 300` | Task max latency required. |
| EDC ID | integer node ID | categorical/stable key; no numeric normalization | Never missing for configured node. |
| `queue_length_per_edc` | task count | `/ 100` | null if no queue view. |
| `active_tasks_per_edc` | task count | `/ 100` | null if active-task tracking is unavailable. |
| `estimated_queue_wait_seconds_per_edc` | simulated seconds | `/ 300` | null for unavailable estimator; never replaced with zero. This is an estimate, not actual waiting time. |
| `mips_per_core_per_edc` | MIPS/core | `/ 110,000` | Node API value. |
| `cpu_cores_per_edc` | cores | `/ 10` | Node API value. |
| `cpu_utilization_percent_per_edc` | percent | `/ 100` | Node API value; current utilization, not cumulative average. |
| `eligible` | boolean | no scaling | Captured in action mask. |
| `resource_available` | boolean | no scaling | Observed from available RAM/storage against task container; retained as a feature. |

Scales are explicit baseline reference constants, not clipped and not claimed as universally calibrated. CSV preserves raw and normalized values. Missing numeric features serialize as JSON `null`; they are not silently zero-filled.

## 5. Action Mapping and Masking

The action list is the configured EDC set sorted by stable `ComputingNode.getId()`; its size is dynamic. The decision audit stores the full `candidate_edc_ids` list and a same-length `action_mask`. Ineligible actions are false when the existing `PaperAlignedOrchestrator.offloadingIsPossible` rejects a candidate because it is invalid, dead, disallowed by architecture, or unreachable. Eligible actions are true. The selected action is an index into this stable list, and the selected EDC ID is also logged.

If the policy returns an out-of-range or masked action, the orchestrator throws before dispatch. If there are no eligible actions, the test policy returns `-1`; the existing manager path observes `ComputingNode.NULL` and records `NO_OFFLOADING_DESTINATIONS`. The runtime pilot had eligible destinations for all decisions, so the no-eligible *simulator failure branch* was not exercised end-to-end; its action sentinel and helper behavior were unit checked.

Resource shortage is recorded as `resource_available_per_edc`, but is not masked in this validation mode so PureEdgeSim can retain its existing `INSUFFICIENT_RESOURCES` failure reason. The current pilot did not encounter that condition.

## 6. Deterministic Policy Validation

The deterministic policy selects the `(task_id - 1) mod eligible_count`-th eligible action. It is intentionally destination-varying so cache bypass is observable; it does not read or optimize queue values. `OffloadingPolicy` exposes `selectAction`, `observe`, and `endEpisode`; `endEpisode` is called at the simulation horizon. No reward is fabricated and `observe` is not used until a reward/next-state contract exists.

Executable action checks:

```text
./scripts/test_dqn_foundation.sh
DqnActionSpaceSelfTest: 9 checks passed
```

Checks cover stable ID ordering, eligible action acceptance, masked action rejection, out-of-range rejection, no eligible candidate detection, deterministic masked choice, and `-1` for no candidates.

## 7. Decision Audit Results

Final full-horizon validation run:

`results/runs/20261104T003439520707266_paper-aligned-baseline_per-task-test_10ue_EDGE_DC_ONLY_seed1/`

Raw evidence: `raw/per_task_decisions.csv`, `raw/per_task_ledger.csv`, `raw/destinations.csv`, `raw/task_event_trace.csv`, `raw/edc_node_state.csv`, simulator CSVs, and `manifest.json`.

| Check | Observed |
|---|---:|
| Generated deterministic test tasks | 64 |
| Unique per-task policy decisions | 64 |
| Source UEs | 1 (UE ID 7) |
| Candidate ID mapping and mask | `[1,2,3,4]`; `[false,false,true,true]` for all 64 decisions |
| Selected destination allocation | EDC 3: 32; EDC 4: 32 |
| Cache bypass flags | 64/64 true |
| Cached placement existed before dispatch | 63/64 |
| Selected destination differs from prior cached EDC | 63/64 |
| Selected destination matches actual applied destination and destination audit | 64/64 |
| Duplicate task decisions | 0 |

Queue/workload observations across the four candidate rows per decision:

| Observed field | Candidate values > 0 | Maximum | Decision snapshots containing a nonzero value |
|---|---:|---:|---:|
| Waiting queue length | 85 | 5 tasks | 43/64 |
| Active task count | 125 | 10 tasks | 63/64 |
| Estimated queue wait | 89 | 0.49 simulated seconds | 45/64 |

The estimate is an estimator output; it is not substituted for actual waiting time. The lifecycle ledger reports average actual completed-task waiting time of `0.16875` simulated seconds and maximum `0.45` seconds for this diagnostic workload.

## 8. Task Lifecycle Accounting

Final 5-second run ledger partition:

| Generated | Completed | Failed | Pending at horizon | Reconciles |
|---:|---:|---:|---:|---|
| 64 | 64 | 0 | 0 | PASS |

The runner validates that task IDs are unique in the generated set; terminal categories are unique and mutually exclusive; every terminal ID belongs to the generated set and has a decision; and `generated = completed + failed + pending`. At the 5-second horizon all 64 terminal outcomes are keyed to the corresponding task IDs in the decision ledger.

Separate 1-second cutoff validation:

`results/runs/20261104T003132581500781_paper-aligned-baseline_per-task-test_10ue_EDGE_DC_ONLY_seed1/`

It generated 64 tasks, recorded 32 task destination decisions before the cutoff, completed 3, failed 0, and left 61 pending. The 61 pending IDs are recorded as `TASK_PENDING_AT_HORIZON`; no pending task is counted as failed. Two tasks had reached the orchestration request stage but had not reached destination-decision dispatch by the cutoff, and the remaining generated tasks had future release times. Ledger partition passed: `64 = 3 + 0 + 61`.

## 9. Regression Test Results

```text
./scripts/test_dqn_foundation.sh
  DqnActionSpaceSelfTest: 9 checks passed

python3 -m pytest --import-mode=importlib -q
  25 passed, 3 skipped, 6 subtests passed

python3 -m py_compile scripts/execute_run.py
  passed
```

`--import-mode=importlib` is needed because archived evidence directories contain Python tests with duplicate module basenames. Plain `python3 -m pytest -q` was also tried and failed during collection with “import file mismatch” for those archived duplicates; no files were removed or altered to bypass this repository condition. Three acceptance/smoke tests are gated and skipped by default.

Current-source baseline smoke command:

```text
./run.sh --profile paper-aligned-baseline --method trade-off --devices 10 --duration-seconds 1 --destination-config EDGE_DC_ONLY --seed 1
```

Run `results/runs/20261104T003151834114462_paper-aligned-baseline_trade-off_10ue_EDGE_DC_ONLY_seed1/` completed with `validation_errors=0`: generated 145, completed 9, failed 120, pending 16. It used the ordinary baseline entry point. This short run verifies the baseline still executes; it is not a performance comparison with the synthetic 64-task workload.

Two earlier validation attempts are preserved but excluded from successful-run counts: a runner syntax error before simulator launch (`20261104T001820032542088_...`) and a 5-second run whose simulator exited 0 but was marked invalid by a runner check incorrectly expecting all 10 UEs to appear as task sources for the deliberately single-UE test generator (`20261104T002057899284041_...`). The source-count check was corrected to expect one UE only for `per-task-test`; later final runs passed all validations. An initial default-workload per-task smoke run (`20261104T001857018640475_...`) did not create changing decision-time queue observations and is not used as evidence for the deterministic load test.

## 10. Remaining DQN Implementation Requirements

- No neural network or training loop is implemented. Replay buffer, target network, optimizer, exploration schedule, model checkpoint and train/evaluation split remain future work.
- `OffloadingPolicy.observe` is not called yet: the reward, delayed asynchronous outcome semantics, next-state definition and treatment of pending tasks must be designed first. A terminal task-ID ledger exists and the runner checks terminal-to-decision correlation.
- The current test policy deliberately rotates actions and therefore does not demonstrate queue-aware destination ranking or performance benefit.
- The 64-task generator selects one UE with at least two reachable EDCs and uses one application profile. Results validate dispatch mechanics and queue observability only; no generalization or performance claim follows.
- Runtime no-eligible-destination and resource-shortage cases were not produced by the pilot; no-eligible policy sentinel and invalid-mask behavior were tested at helper level.
- Three default-gated acceptance tests were skipped. Trade-Off and Queue-Aware source/scoring/configuration remain unchanged; only `PaperAlignedSimulationManager` was made non-final for subclassing, and the new mode uses distinct manager/orchestrator/node/generator classes.

## Reproduction

Run the isolated full-horizon validation workload:

```bash
./run.sh --profile paper-aligned-baseline --method per-task-test --devices 10 --duration-seconds 5 --destination-config EDGE_DC_ONLY --seed 1
```

Run the hard-horizon pending check:

```bash
./run.sh --profile paper-aligned-baseline --method per-task-test --devices 10 --duration-seconds 1 --destination-config EDGE_DC_ONLY --seed 1
```

Both commands create unique timestamped directories under `results/runs/`; they do not overwrite prior results. The deterministic policy is selected by the per-task mode and writes raw CSV audits alongside the authentic PureEdgeSim output.
