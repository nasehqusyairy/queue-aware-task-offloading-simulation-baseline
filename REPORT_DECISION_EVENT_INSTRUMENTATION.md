# Decision-Event MDP Instrumentation Report

**Revision before changes:** `bfe313518573cbbee8a246d09c89cf5148e8ea92`  
**Working tree:** implementation and pilot artifacts are uncommitted.  
**Scope:** isolated decision-event observation/transition instrumentation and validation only. No DQN training was run; the legacy `DelayedTransitionLedger` remains in use by the existing DQN path and was not replaced. Default Trade-Off/Queue-Aware behavior is unchanged unless the new instrumentation/drain properties are explicitly supplied to the per-task experimental manager.

## 1. Implemented architecture

- `DecisionStateSnapshot` and nested immutable task/EDC records freeze the state before policy selection. Collections are defensive, unmodifiable copies; unsupported measurements are `null` in CSV JSON rather than zero.
- `DqnReadyOrchestrator.findComputingNode()` calls `DqnReadySimulationManager.preparePolicyDecision()` before `policy.selectAction()`. The manager gives each call a monotonically increasing decision ID, reads simulator time and the current `Event` serial, freezes candidate IDs/eligibility and lifecycle counts, and writes `decision_event_snapshots.csv`.
- After the policy returns, the manager records the action. After the base dispatch path returns, it writes selected and actual applied EDC IDs and cache status to `decision_event_decisions.csv` and fails closed if selected and applied IDs differ.
- `DecisionEventTransitionBuilder` is a separate system-reward interval builder. A later actionable decision closes the previous interval; all terminal callbacks observed during that interval are accumulated independent of task ID. Duplicate terminal task IDs are ignored. Empty-mask calls are logged as decisions but do not close/open an actionable interval. At the terminal horizon the open interval closes without a fabricated next state.
- `DecisionEventDrainController` is enabled only by `paper.decision-event-drain-seconds`; it tracks arrival cutoff, drained outcome, and right-censored outcome. Existing hard-horizon behavior remains the default. `scripts/execute_run.py` passes these properties only under explicit `PAPER_DECISION_EVENT_TRACE=1` and accepts end time between arrival cutoff and configured drain cap after validating both markers.

The transition CSV contains source task ID for audit only, decision ID, state/next-state timestamps and IDs, action/EDC, interval reward, elapsed seconds, continuous-time discount, terminal flag, and next-state mask. `next_state` itself is the next immutable snapshot in the snapshot CSV, joined by decision ID.

## 2. State feature sources and limitations

| Feature | Source | Availability / interpretation |
|---|---|---|
| Task MI, input, container, output, deadline, release time, UE ID/location, application | PureEdgeSim `Task` and UE mobility model at the policy hook | Direct pre-action values; remaining deadline is `max(0, deadline - (decision time - release time))` |
| EDC ID, eligibility, waiting count, MIPS/core, total cores, current CPU utilization, available RAM/storage | Stable candidate list/action mask; `ComputingNode`/`DefaultComputingNode` getters | Direct pre-action measurements |
| Active task count, available cores, active remaining service estimate and queue wait estimate | `QueueAwareComputingNode` | Direct active/queue accounting from its observed task map; service estimate sums remaining service seconds across active jobs and is not a wall-clock makespan under parallel cores |
| Request/dispatch/queue/active/result lifecycle bucket | `TaskLifecycleTracker`, updated from existing event callbacks in the DQN-ready manager and computing-node hooks | One mutually exclusive stage per observed task; prevents double counting across those buckets |
| Active network transfers and per-link remaining transfer state | PureEdgeSim `NetworkLink` internals | **Unavailable as a coherent decision-time aggregate.** `transferFinished` exposes a completed transfer's type, but active transfer progress is protected and not included in the policy snapshot. Snapshot records a blank (`null`) active-transfer count. |
| Exact request-vs-task-vs-container transfer counts in flight | Not exposed at the policy boundary | `REQUEST_IN_FLIGHT` (source request pending) and `ASSIGNED_NOT_ADMITTED` (destination assigned but not admitted) are observable lifecycle buckets. The latter can include destination request/task/container network work; these subtypes cannot be counted reliably at a snapshot. No synthetic zeros are emitted. |

The lifecycle map is exclusive by task ID; task state moves between buckets instead of incrementing independent counters. Terminal tasks are removed from the outstanding map. The current decision task is marked `AT_ORCHESTRATOR_DECISION` before freezing the snapshot, not left counted as a source request in flight. This state is an observed aggregate, **not proven Markov-sufficient**: active network transfers, transfer queues, and other hidden event-queue state are missing.

## 3. Exact decision boundary and event order

The boundary is an actual invocation of `DqnReadyOrchestrator.findComputingNode()` from the orchestrator event path `SEND_TASK_FROM_ORCH_TO_DESTINATION`. The snapshot is taken after the request reaches the orchestrator and before `policy.selectAction()`. The selected action is written later after policy return; actual destination is verified after dispatch returns.

`Event.getSerial()` is captured from the currently processed event. `FutureQueue.addFirst()` assigns negative serials to `scheduleNow()` events; `Event.compareTo()` sorts by timestamp and then serial, and PureEdgeSim drains same-time events in that order. Adjacent actionable decisions therefore define interval boundaries by callback/processed order; timestamp ties produce a zero elapsed interval when appropriate and remain distinct events in the audit.

Code path: `DqnReadyOrchestrator.findComputingNode()`, `DqnReadySimulationManager.processEvent()/preparePolicyDecision()/finalizeDecision()`, `DefaultSimulationManager.sendFromOrchToDestination()`, `Event.compareTo()`, and `FutureQueue.addFirst()`.

## 4. Interval reward accounting

For each unique terminal task callback during the current open interval, diagnostic reward contribution is:

- completed: (+w_C - w_D \cdot d_j)
- failed: (-w_F - w_D \cdot d_j)

where (d_j) is the simulator-reported total delay. The interval builder sums every contribution between the two actionable decision hooks, including multiple and out-of-order task outcomes. Task ID is used only for duplicate protection/audit, not to connect one task reward to another task's state. A completion/failure outside an open interval is not credited to an action.

The pilot explicitly supplied (w_C=1), (w_F=1), (w_D=0.01), and (\rho=0.01\;s^{-1}) as **instrumentation smoke-test values only**, not recommended research coefficients. No congestion integral was added. For elapsed simulated time Δτ, the builder stores (e^{-\rho\Delta\tau}). The current DQN learner is not connected to these new transitions.

## 5. In-flight workload accounting

Each task appears in at most one lifecycle stage at a time: `REQUEST_IN_FLIGHT`, `AT_ORCHESTRATOR_DECISION`, `ASSIGNED_NOT_ADMITTED`, `WAITING_QUEUE`, `ACTIVE_EXECUTION`, or terminal (removed from outstanding counts). A source request pending for orchestration is separated from a destination-assigned task that has not yet reached admission. Once admitted it is observed as waiting or active through `DqnReadyComputingNode` callbacks; after execution it moves to result transfer until terminal.

The per-link active transfer list is not surfaced. The audit therefore does not claim exact counts for in-flight request/task/container/results transfers. `TaskTracingNetworkModel.transferFinished()` observes completed transfer types only. This is the specific remaining instrumentation gap for a richer Markov state.

## 6. Experimental drain

`paper.decision-event-drain-seconds` is opt-in on `DqnReadySimulationManager`. At the existing `PRINT_LOG` event (arrival cutoff), it starts a drain controller and schedules checks. It terminates when all generated tasks are completed/failed or at the cap. Remaining work at the cap flows through existing pending-at-horizon accounting; no failure callback/reward is synthesized for it. The default manager path and baseline experiment behavior are unchanged.

## 7. Tests and integration pilot

Command for deterministic Java checks:

```bash
./scripts/test_dqn_foundation.sh
```

Result: `DqnActionSpaceSelfTest: 9 checks passed`, `DqnImplementationSelfTest: 18 checks passed`, and `DecisionEventInstrumentationSelfTest: 17 checks passed`. New deterministic checks cover immutable snapshots, same-time `FutureQueue` ordering, empty action set, multiple/out-of-order terminal outcomes, duplicate protection, reward arithmetic, elapsed-time discount, exclusive lifecycle counts, drained vs censored drain outcomes, and no fabricated reward for censored tasks.

Final accepted integration pilot used a deterministic test policy, not DQN:

```bash
RUNS_ROOT="$PWD/results/experiments/20261104T_decision_event_instrumentation_pilot/runs" \
PAPER_DECISION_EVENT_TRACE=1 \
PAPER_DECISION_EVENT_COMPLETION_WEIGHT=1 \
PAPER_DECISION_EVENT_FAILURE_WEIGHT=1 \
PAPER_DECISION_EVENT_DELAY_WEIGHT=0.01 \
PAPER_DECISION_EVENT_RHO=0.01 \
PAPER_DECISION_EVENT_DRAIN_SECONDS=10 \
./run.sh --profile paper-aligned-baseline --method per-task-test --devices 10 \
  --duration-seconds 5 --destination-config EDGE_DC_ONLY --seed 1
```

Accepted run: `20261104T021903707358630_paper-aligned-baseline_per-task-test_10ue_EDGE_DC_ONLY_seed1`.

- 64 generated, 64 completed, 0 failed, 0 pending; run validator returned `status=completed`, `validation_errors=[]`.
- 64 snapshots, 64 decision rows, and 64 interval rows; IDs are sequential; selected EDC equals actual applied EDC for every row; rewards are nonzero where terminal outcomes fall in the interval; last row is terminal.
- Log: `DECISION_EVENT_ARRIVAL_CUTOFF time_seconds=5.000000000 drain_cap_seconds=10.000000000 generated=64`; `DECISION_EVENT_DRAIN_END time_seconds=5.050000000 elapsed_seconds=0.050000000 unresolved_censored=0 drained=true`; `PAPER_HORIZON ... pending_at_cutoff=0 ... accounting_valid=true`.
- Simulator summary: success rate 1.0, average completed-task total delay 5.766165 s, actual average waiting 0.168750 s, energy 0.986 Wh. These are smoke-run outputs only, not a method comparison or performance claim.
- Raw snapshot, decision, and transition CSVs, task event trace, node state, simulator console, metrics and manifest are retained under `results/experiments/20261104T_decision_event_instrumentation_pilot/runs/<run_id>/`.

Run status history: the first instrumented invocation was rejected because the old runner expected end time exactly equal to the 5 s cutoff despite the configured drain (simulation data itself had 64/64 completions). The runner was updated to validate cutoff and drain separately. Two subsequent intermediate runs passed generic run validation, but a follow-up CSV audit found that terminal outcomes were only being forwarded to the new builder for DQN policies; that callback was corrected and the final accepted pilot above has nonzero interval rewards. Two short-cap probes also drained 64/64 tasks before the cap; they did not produce censored tasks. The censor-at-cap branch is covered by the deterministic controller test, not claimed as observed in the simulator pilot.

## 8. Unimplemented components

- No exact global snapshot of active network transfer queues or per-link remaining bytes at decision time.
- No separate active counts for destination request, task, and container transfers; only the exclusive assigned-not-admitted stage plus transfer-completion type callback is available.
- No time-integrated congestion penalty or energy attribution to decision intervals.
- No connection of this builder to replay/training, no training, and no claim of Markov sufficiency.
- No new experimental comparison against Trade-Off/Queue-Aware was run.

## 9. Known methodological limitations

The pilot uses a deterministic validation policy and one seed, and its 64 tasks are a small instrumentation workload. The reward weights are intentionally smoke-test coefficients. Active network state and some transfer subtypes are hidden, so the snapshot does not establish a fully observed MDP. The zero-pending drain result proves only that this pilot completed before its configured cap; censoring behavior was tested at the controller level but was not observed in a simulator run.

The new interval CSV is not consumed by DQN and does not alter the legacy task-keyed transition ledger. Before training, add/validate active-transfer observability or explicitly use a partial-observation formulation, audit same-timestamp completion boundaries end to end, and run a cap-censored integration case with pending accounting.
