# Formal Decision-Event MDP Design for Queue-Aware Task Offloading

**Repository:** `nasehqusyairy/queue-aware-task-offloading-simulation-baseline`  
**Audited revision:** `df58e6aab9fc215a7f646346f7d0b4812f22298d`  
**Scope:** Methodology/design review only. No Java, DQN transition, configuration, or historical-result files were changed; no training or experiment was run for this report.

## 1. Research objective

**VERIFIED — objective.** The intended policy selects an eligible edge data center (EDC) for each task at an orchestrator decision, seeking better system-level outcomes under shared queues and concurrent work. It is not merely a classifier that predicts the best EDC for an isolated task.

**VERIFIED — current lifecycle.** `DefaultSimulationManager.processEvent()` routes `SEND_TASK_FROM_ORCH_TO_DESTINATION` to `sendFromOrchToDestination()`; the orchestrator assigns `task.offloadingDestination`, then the request/task travel through network events before `EXECUTE_TASK` calls `submitTask()`. Thus the policy decision precedes network delivery, queue admission, execution, and result return. See [`DefaultSimulationManager.java`](simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/simulationmanager/DefaultSimulationManager.java:171), [`Orchestrator.java`](simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/taskorchestrator/Orchestrator.java:49), and [`DefaultNetworkModel.java`](simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/network/DefaultNetworkModel.java:45).

## 2. Decision epoch definition

**RECOMMENDED DEFINITION.** Let (t) index each *actual actionable policy invocation*, not task generation or every simulator event. The epoch occurs in `SEND_TASK_FROM_ORCH_TO_DESTINATION`, after the task/request reaches the orchestrator and immediately before `findComputingNode()` selects a destination. Freeze the observation at that point, before applying action (a_t).

At each epoch, the current task (j_t) is the task passed to `orchestrate()`. Every simulator event processed after this hook and before the next actionable hook belongs to the interval transition. Network transfers, queue admission, execution starts/finishes, completions, failures, mobility, and nondecision events update the environment but do not themselves create an agent action. If no candidate is eligible, the environment has a forced no-action/failure outcome; it should not be represented as a fabricated EDC action.

**VERIFIED — cache caveat.** `DefaultSimulationManager.sendFromOrchToDestination()` calls `orchestrate()` only when application placement is unset; otherwise it reuses `applicationPlacementLocation`. `Orchestrator.orchestrate()` sets that location. Consequently, stock Trade-Off and Queue-Aware may not receive one decision per task. `DqnReadySimulationManager.sendFromOrchToDestination()` clears the application placement before delegating, causing a decision on each task. This difference must be treated as a decision-opportunity difference in comparisons, not hidden as an algorithm effect. See [`DefaultSimulationManager.java`](simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/simulationmanager/DefaultSimulationManager.java:294), [`Orchestrator.java`](simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/taskorchestrator/Orchestrator.java:129), and [`DqnReadySimulationManager.java`](experiment/src/com/mechalikh/pureedgesim/simulationmanager/DqnReadySimulationManager.java:70).

## 3. System state

Use a system snapshot (S_t) at each decision hook. The following is the target state, not a claim that the current observation already contains all fields.

| Component | Include at decision time | Current observability / limitation |
|---|---|---|
| Current task | MI/length, input/container/output sizes, type/application, deadline remaining, source UE and current location/route | Task fields exist before decision; ensure features are read before dispatch and contain no eventual outcome |
| Each EDC | stable EDC ID, eligible flag, cores and free cores, MIPS/core, CPU utilization, RAM/storage capacity and free amount, ordered waiting jobs/workload, active jobs and remaining service | `DefaultComputingNode.submitTask()`, `startExecution()`, and `executionFinished()` manage FIFO waiting and active execution. Queue-aware node exposes an estimate based on active remaining service and queued task lengths. Existing DQN observation includes some of these aggregates but not a complete job schedule |
| Work already committed | task selected for an EDC but not yet arrived/admitted; request waiting for orchestrator; request/task/container transfers; result transfers; per-link active transfer counts, remaining bits, bandwidth/path | These states are material because decision precedes destination delivery. `NetworkLink` maintains transfer progress internally, but current policy observation does not expose a full aggregate in-flight snapshot |
| Exogenous process | mobility/arrival context and, if needed, random-process state or a justified stationary-process assumption | Future arrivals or future mobility outcomes must never be encoded. Full simulator event queue would be Markov but is impractically large and may expose implementation detail |

Code evidence: [`DefaultComputingNode.java`](simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/datacentersmanager/DefaultComputingNode.java:222), [`QueueAwareComputingNode.java`](experiment/src/com/mechalikh/pureedgesim/experiment/QueueAwareComputingNode.java:51), [`DqnStateEncoder.java`](experiment/src/com/mechalikh/pureedgesim/experiment/DqnStateEncoder.java:21), and [`NetworkLink.java`](simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/network/NetworkLink.java:100).

**PARTIALLY VERIFIED — Markov sufficiency.** Current encoded state is an aggregate partial observation: it includes task/candidate queue and resource features, but omits important in-flight network and outstanding-work state. Shared queues and transfers can therefore evolve differently from identical encoded observations. Until state augmentation and a sufficiency check, call the formulation an approximate MDP/POMDP, not a proven Markov-sufficient MDP. Do not add future completion time, actual wait, future queue state, or other post-decision data (leakage).

## 4. Action space and mask

For task (j_t), define the action set as the currently eligible EDCs:

\[
A_t = \{e \in E : m_{t,e}=1\}, \qquad a_t \in A_t.
\]

Use a stable EDC-ID-to-output-index map; record the ordered candidate IDs and mask with each decision. Apply the same mask when selecting an action and when taking the target-network maximum:

\[
\max_{e \in A_{t+1}} Q^-(S_{t+1},e).
\]

The existing `PaperAlignedOrchestrator.offloadingIsPossible()` is the baseline eligibility rule; it checks architecture and reachability/liveness conditions. Do not silently substitute RAM/storage feature availability for eligibility: execution can later fail for resource reasons. Empty (A_t) is an environment no-destination outcome and should not create an invalid `argmax`. Code: [`PaperAlignedOrchestrator.java`](experiment/src/com/mechalikh/pureedgesim/experiment/PaperAlignedOrchestrator.java:21), [`DqnReadyOrchestrator.java`](experiment/src/com/mechalikh/pureedgesim/experiment/DqnReadyOrchestrator.java:28).

## 5. Reward function

Use system-level reward over the interval between policy decisions. For each terminal task outcome (j), define a parameterized outcome value:

\[
g_j = \begin{cases}
+w_C - w_D d_j, & j \text{ completes},\\
-w_F - w_D d_j, & j \text{ fails},
\end{cases}
\]

where (d_j\) is measured end-to-end delay in seconds, and (w_C,w_F,w_D\) are research parameters to be specified and preregistered before training. They are not fitted or recommended numerically here. Queue waiting is part of end-to-end delay; if separately penalized, explain and ablate the potential double counting.

A system congestion term may be added only if a well-defined, normalized queue/workload quantity is available:

\[
R_t = \sum_{j:\,\zeta_t < \zeta_j \le \zeta_{t+1}}
 e^{-\rho(\tau_j-\tau_t)}g_j
 - w_Q \int_{\tau_t}^{\tau_{t+1}} e^{-\rho(s-\tau_t)}\Phi(S(s))\,ds.
\]

Here (\zeta) is processed event/policy-hook order, (\tau) is simulated time, and (\Phi) is an explicitly defined congestion measure. The queue-area term is optional; compare reward variants because delay already reflects queueing. Energy remains an evaluation metric until reliable task-level or decision-interval attribution is established.

This assigns all system outcomes in the interval to the preceding system action and does not attach one task’s delayed reward to an unrelated task’s observation. It is a valid sequential system-reward convention only when the state captures enough outstanding work to predict subsequent outcomes. Completion/failure events are identified in `DefaultSimulationManager.processEvent()` and `taskFailed()/setFailed()`; the existing audit/ledger path is in [`PaperAlignedSimulationManager.java`](experiment/src/com/mechalikh/pureedgesim/simulationmanager/PaperAlignedSimulationManager.java:86) and [`DqnReadySimulationManager.java`](experiment/src/com/mechalikh/pureedgesim/simulationmanager/DqnReadySimulationManager.java:83).

## 6. Transition semantics

A transition is

\[
(S_t,a_t,R_t,S_{t+1},done_t),
\]

where (S_{t+1}) is frozen immediately before the next actionable policy call and (R_t) sums the system-level outcomes and optional time-integrated cost from the event interval. Multiple tasks may complete or fail in one interval; include each exactly once. Tasks can be executing, queued, or in flight across several decisions. Their eventual outcomes enter the interval in which the simulator processes the terminal event, while their outstanding state must remain represented in (S).

Do not assume the chosen task finishes before the next decision. The current `DelayedTransitionLedger.onDecision()` links the next decision state to the prior action, while `onTerminal(taskId, reward)` later joins a task-specific outcome by task ID; this is precisely the asynchronous reward/state pairing that the formal interval design replaces. See [`DelayedTransitionLedger.java`](experiment/src/com/mechalikh/pureedgesim/experiment/DelayedTransitionLedger.java:32).

**Same timestamp ordering — VERIFIED.** `Event.compareTo()` orders by event time and serial. `FutureQueue.addFirst()` gives immediate events negative serials; `scheduleNow()` inserts through this path. The simulator drains events at the same exact timestamp as one batch. Therefore interval boundaries must follow actual processed event and policy-hook order, not timestamp alone. Record event serial/order and close the prior interval immediately before the next policy invocation; events already processed at the same timestamp count in the prior interval, later events do not. Code: [`Event.java`](simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/simulationengine/Event.java:46), [`FutureQueue.java`](simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/simulationengine/FutureQueue.java:35), [`SimEntity.java`](simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/simulationengine/SimEntity.java:80), [`PureEdgeSim.java`](simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/simulationengine/PureEdgeSim.java:158).

## 7. Discount semantics

Decision intervals have variable simulated duration. Use continuous-time discounting:

\[
\Delta\tau_t=\tau_{t+1}-\tau_t,\qquad
\gamma_t=e^{-\rho\Delta\tau_t},\quad \rho\ge0\;[\mathrm{s}^{-1}].
\]

The masked DQN target becomes

\[
y_t=R_t+\gamma_t(1-done_t)\max_{e\in A_{t+1}}Q^-(S_{t+1},e).
\]

This gives ρ a physical-time interpretation. If the intended objective is undiscounted finite-horizon total reward, set ρ=0 explicitly. The existing fixed gamma per decision discounts per decision count, so elapsed-time weighting changes with event frequency; it is not equivalent when intervals vary. Store γ_t (or Δτ and ρ) per replay transition.

## 8. Terminal and horizon handling

Separate task-generation cutoff from episode termination. Stop generating new tasks at (T_{arr}), then drain active/queued work and all in-flight request, task, container, and result transfers until the system is empty. Terminate the episode only once no unresolved work remains, subject to a declared safety drain cap.

If the cap is reached, unresolved tasks are **right-censored/pending**, not failed. Either exclude such episodes from completion-outcome comparisons while reporting censoring, or use a preregistered system backlog terminal cost (-w_B\Psi(S_H)) based on observable remaining workload; do not invent terminal per-task failures. The current paper-aligned manager marks unresolved tasks at the horizon as pending; `DelayedTransitionLedger.finishEpisode()` currently closes the decision sequence at horizon, which must be reconciled with a drain protocol. References: [`PaperAlignedSimulationManager.java`](experiment/src/com/mechalikh/pureedgesim/simulationmanager/PaperAlignedSimulationManager.java:209), [`DelayedTransitionLedger.java`](experiment/src/com/mechalikh/pureedgesim/experiment/DelayedTransitionLedger.java:67).

The pre-first-decision period is an exogenous prelude. Report outcomes in it separately or initialize the process so there are no attributable task outcomes before the first action; do not credit them to an action that has not occurred. A terminal transition has no bootstrap. Distinguish “end of decision sequence” from “task completed”: current `OffloadingTransition.terminal` semantics should not be conflated with a task terminal label.

## 9. DQN compatibility assessment

**CONDITIONAL.** Standard DQN is a reasonable candidate after the transition definition is implemented and state sufficiency is addressed:

- Variable action sets are supported by a shared candidate scorer and masks, provided the same mask is used for exploration/greedy selection and target max.
- Delayed outcomes are compatible with replay when rewards are accumulated by decision interval and the transition is emitted only after (S_{t+1}) is known.
- Target network and replay remain applicable; store interval reward, next-state mask, elapsed-time discount, and terminal flag.
- Concurrent work is represented as system state, rather than attributed using task ID alone.
- Current aggregate state remains partially observable. First augment with outstanding/in-flight state and evaluate whether the approximation is adequate. If relevant hidden state remains, characterize the problem as a POMDP and consider recurrent DQN or a belief/history representation; alternatively compare a suitable event-driven actor-critic or policy-gradient method. Do not presume those alternatives solve missing observability.

The current DQN implementation’s variable candidate scoring/masking does not by itself establish MDP validity. The latest pilot is also not a fair performance comparison: in `results/experiments/20261104T010929Z_dqn_pilot/`, baseline methods used application placement/cache behavior while DQN made per-task decisions. Its two evaluation seeds are preliminary; observed metric differences are not evidence of superiority. See that folder’s `REPORT_DQN_IMPLEMENTATION.md` for recorded pilot details.

## 10. Fair experimental comparison

Maintain two explicitly separate groups and preserve current defaults.

**Group A — original behavior:** original Trade-Off, Queue-Aware, and DQN with their existing placement/cache semantics. This answers how the shipped policies behave in the default simulator integration. Report policy invocation counts and cache hits; do not claim equal decision opportunities.

**Group B — controlled per-task protocol:** new, separately named per-task wrappers for Trade-Off and Queue-Aware plus DQN. Each must be invoked on the same per-task event hook and use identical eligibility rule, stable candidate set, workload/configuration, and seed. Do not silently change the original classes or application-placement behavior. The wrapper names and semantics must be explicit in all outputs.

For Group B validate, per paired run: generated task IDs and offered workload match; decision counts equal (except documented empty-mask forced outcomes); candidate ID list and mask hashes match at each task; all methods use same simulator properties, UE/EDC configuration and seed; every selected action is applied to the same destination ID logged at dispatch; placement cache is bypassed consistently; no method-specific policy invocation changes event ordering. Report destination allocations and invalid/masked actions, and retain raw decision logs. Group A and B answer different questions and must not be pooled.

## 11. Assumptions and limitations

- Treat queue service estimates as estimated state features, not actual waiting outcomes. `QueueAwareComputingNode.estimateQueueWaitSeconds()` uses active remaining service and waiting task lengths; it cannot observe tasks not yet admitted from the network.
- EDC queue/task state evolves through events; snapshots need a coherent, immutable read at the policy hook.
- A compact aggregate may fail Markov sufficiency if job sizes/order, network contention, mobility, or arrivals affect future transitions but are omitted.
- Simulator event serials are implementation-specific. Record them for reproducibility, but the scientific event-boundary rule is processed-order semantics.
- Reward weights, congestion function, episode cutoff/drain cap, and discount rate are research design parameters requiring pre-specification and sensitivity analysis; this report does not tune them.
- No new training, experiment, or code validation was performed for this design report.

## 12. Mathematical notation and compact formulation

Let (E) be all EDCs; (m_{t,e}\in\{0,1\}) the eligibility mask; (S_t) the pre-action system snapshot; ζ the ordered policy-hook/event position; τ simulated seconds; (J_t) the terminal outcomes processed in ((\zeta_t,\zeta_{t+1}]). Then

\[
A_t=\{e\in E:m_{t,e}=1\},\quad a_t\in A_t,
\]

\[
R_t=\sum_{j\in J_t}e^{-\rho(\tau_j-\tau_t)}g_j
-w_Q\int_{\tau_t}^{\tau_{t+1}}e^{-\rho(s-\tau_t)}\Phi(S(s))\,ds,
\]

\[
\gamma_t=e^{-\rho(\tau_{t+1}-\tau_t)},\qquad
Q^*\text{ target: }R_t+\gamma_t(1-done_t)\max_{e:m_{t+1,e}=1}Q^-(S_{t+1},e).
\]

(done_t=1) only at the declared episode end after drain (or an explicitly censored terminal with declared backlog treatment). State must include current task, EDC state, committed/in-flight workload, and relevant exogenous context to claim an MDP. If those are compressed or hidden, explicitly qualify the learned process as approximate/POMDP.

## 13. Implementation roadmap

1. **Freeze protocol:** specify (T_{arr}), drain cap, ρ, reward components/units, queue penalty ablation, no-action handling, candidate ordering, and censoring policy before training.
2. **Instrument the decision boundary:** capture policy-hook ID, processed event order/serial, exact timestamp, task ID, candidate IDs/mask, selected EDC, cache use, and post-selection dispatch destination.
3. **Build state snapshot:** add stable EDC aggregates and outstanding/in-flight request/task/container/result measurements. Document any inaccessible fields and retain an explicit partial-observation designation if not exposed.
4. **Replace only in the new experimental path:** add an interval transition builder that freezes (S_t), accumulates outcomes/costs, freezes (S_{t+1}), stores γ_t/mask/terminal, then emits replay data. Leave current transition implementation and original policies untouched until comparison and review authorize replacement.
5. **Add drain and accounting:** distinguish generation cutoff, drain, completed/failed/pending, and terminal backlog.
6. **Validate on deterministic toy/event cases and paired wrappers before training.** Only after these pass begin a small pilot; then scale seeds/configurations.

## 14. Validation tests and final decision

Required tests before substantive training:

- **Event boundary:** same-time normal and `scheduleNow()` events follow actual queue order; outcome goes to exactly one adjacent interval; order is deterministic under a fixed event schedule.
- **Concurrent outcomes:** multiple completions/failures between two policy calls are each counted once; out-of-order task completions do not corrupt interval reward; an unrelated later decision does not receive a task-specific reward by task-ID coincidence.
- **State timing/leakage:** snapshot equals simulator state immediately before action; selected destination is absent from pre-action observation where appropriate; no future completion, realized wait/delay, or future queue state leaks into features.
- **Queue/network snapshot:** active and waiting jobs and in-flight requests/transfers are distinguishable; conservation/accounting checks reconcile assigned, arrived, queued, active, terminal, and pending tasks.
- **Mask correctness:** selection and target ignore masked candidates; stable mapping survives candidate-list changes; empty mask yields a documented environment outcome without invalid max/NaN.
- **Discount/reward arithmetic:** variable Δτ produces expected (e^{-\rho\Delta\tau}); reward aggregation and units match hand-calculated toy cases; terminal transitions do not bootstrap.
- **Horizon/drain:** generation stops at (T_{arr}); drain includes result return; pending at cap is censored and not silently failed; episode terminal occurs once.
- **Replay/DQN:** stored transition includes correct reward, next mask, elapsed discount, terminal flag; run deterministic toy MDP to confirm target values and compare gradients with finite differences.
- **Group B parity:** paired methods use identical offered task IDs/configuration/seeds, equal eligible decision counts, per-task candidate/mask hashes, and selected-versus-applied destination IDs; Group A defaults remain unchanged.

**Final decision: APPROVED WITH CONDITIONS.** The decision-event system-reward formulation is suitable to implement as a separate experimental path, conditional on explicit interval reward accounting, event-order boundaries, state/in-flight observability (or a clearly labeled POMDP approximation), variable-time discount semantics, drain/censor handling, and Group B parity checks. This is approval of the *design for implementation*, not a finding that the existing transitions or pilot already meet these conditions. Do not begin large-scale training until the validation tests above pass.
