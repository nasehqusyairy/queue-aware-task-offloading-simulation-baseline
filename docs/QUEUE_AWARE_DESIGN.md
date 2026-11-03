# Queue-Aware Trade-Off: Source Audit and Design

Status: source audit, algorithm specification, and implementation record. Queue-Aware is implemented as an experiment-only extension and passed the paired 200-second acceptance smoke. The smoke is a correctness check, not evidence of performance benefit.

## 1. Repository and execution path audited

The working tree was clean on `main` before work began. Work is on `feature/queue-aware-offloading`; the existing Trade-Off implementation remains untouched and Round Robin remains available. The baseline's `run.sh` copies one profile into a unique `results/runs/<id>` directory, builds the PureEdgeSim Maven source tree using the checked-in source-root patch, and calls `scripts/execute_run.py`. That script compiles the experiment Java adapters, runs the simulator, copies raw CSV/log output, validates observations, writes the manifest, then invokes `scripts/analyze.py` to create per-run metrics. The paper-aligned adapter path is `PaperAlignedMain` → `PaperAlignedTaskGenerator`, `PaperAlignedComputingNodesGenerator`, `PaperAlignedOrchestrator`, and `PaperAlignedSimulationManager`.

## 2. Trade-Off decision flow

Source: `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/taskorchestrator/DefaultOrchestrator.java`.

1. `Orchestrator` reads the scenario architecture and creates `nodeList` from the selected Cloud, Edge Data Center, and/or Mist sets.
2. `DefaultSimulationManager.sendTaskToOrchestrator()` associates the task with its configured orchestrator and sends it through `NetworkModel`.
3. When the request reaches the orchestrator, `DefaultSimulationManager.sendFromOrchToDestination()` calls `edgeOrchestrator.orchestrate(task)` unless the UE application was already placed.
4. `DefaultOrchestrator.findComputingNode()` chooses the Trade-Off or Round Robin path from the scenario algorithm. Trade-Off walks `nodeList`, rejects candidates through `offloadingIsPossible`, scores eligible nodes, and increments assignment history for the selected node.
5. The exact built-in Trade-Off score is:

   `S_tradeoff(j) = (H_j + 1) * w_type(j) * L_task / MIPS_per_core(j)`

   where lower is preferred; `H_j` is a cumulative assignment count kept in `historyMap`, `w_type` is 1.8 for Cloud, 1.3 for Mist/UE, and 1.2 for Edge Data Center, `L_task` is task length, and `MIPS_per_core` is the candidate's per-core rate. This history is not the node's current queue and is never decremented on completion. In the default method, the first eligible node wins exact ties.

The paper adapter currently subclasses `DefaultOrchestrator` only to apply its existing destination-layer and reachability checks while retaining the built-in Trade-Off/Round Robin selection. Queue-aware behavior must be a distinct orchestrator class so the `TRADE_OFF` code path and results remain available unchanged.

## 3. Task lifecycle and processing model

Relevant source: `DefaultSimulationManager`, `DefaultNetworkModel`, `NetworkLink`, `DefaultComputingNode`, `TaskAbstract`, `DefaultTaskGenerator`, and their paper-aligned experiment extensions.

`generated → scheduled to SEND_TO_ORCH → sent through request network → orchestrated → destination assigned → request/container transfer → EXECUTE_TASK → submitTask → running or waiting queue → execution finished → result transfers → RESULT_RETURN_FINISHED → completed or failed`.

`DefaultComputingNode` implements a FIFO `ArrayList<Task>` returned by `getTasksQueue()`. `submitTask()` starts work immediately when a core and enough RAM are available; otherwise it appends to that list. On completion, `executionFinished()` frees core/RAM/storage, records finish time, then starts the first queued task. Each task runs for `task.length / mipsPerCore` simulated seconds. The core count controls how many tasks run concurrently; per-task service rate is `mipsPerCore`.

The existing node exposes its waiting queue through `ComputingNode.getTasksQueue()`, core count through `getNumberOfCPUCores()`, per-core service rate through `getMipsPerCore()`, aggregate capacity through `getTotalMipsCapacity()`, and a CPU utilization estimate. The waiting queue does **not** contain active tasks. `DefaultComputingNode` has a protected aggregate `tasks` field for active task lengths, but there is no public active-task list or remaining-work accessor. Its `getCurrentCpuUtilization()` is capped and derived from that aggregate; it does not express a reliable queue length or active-task completion schedule. Consequently, queue length alone would miss busy cores, and the conceptual `sum(backlog)/capacity` estimate is not an exact wait estimate for this multi-core FIFO scheduler.

`TaskAbstract.getWatingTime()` is destination arrival to execution start; CPU time is execution finish minus start. `getTotalDelay()` sums accumulated network transfer/latency, waiting, and CPU time. Network links add transfer time and per-hop latency. This is separate from the proposed *decision-time estimate*; do not add task network delay or task's eventual wait to the queue penalty.

## 4. Queue/workload signal and proposed extension

### Runtime workload view

Use a separate experiment-only subclass of `DefaultComputingNode` implementing a small workload-view interface. Override the existing protected `startExecution(Task)` and `executionFinished(Event)` hooks to track each active task's start time and length, while always calling the superclass implementation unchanged. At decision time, derive each active task's estimated remaining work:

`R_i = max(0, L_i - (t_now - t_start,i) * MIPS_per_core)`

The waiting queue is read from the existing FIFO `getTasksQueue()` and contributes each queued task's `L_q`. Predict core availability under the current state only: initialize one free-time slot per core with the tracked active task's remaining service time (empty cores get 0); then assign already queued tasks in FIFO order to the currently earliest-free slot, adding `L_q / MIPS_per_core`. The estimated queue wait for a new task is the minimum resulting core-free time:

`W_queue(j) = min_k(free_time_k after scheduling current queued tasks)` seconds.

This mirrors the framework's one-task-per-core service time and FIFO dequeue behavior more closely than dividing task count by capacity. It uses only current active tasks and current queued tasks. It assumes no new arrivals, assumes current per-core rate remains constant, and does not model future network transit, RAM-constrained queue eligibility, or failures. A zero-core/sensor node is already not a legal computing candidate in the paper orchestrator; the estimator will return unavailable for non-finite/non-positive MIPS or invalid core state, never divide by zero.

### Decision equation

For each eligible candidate, preserve the built-in Trade-Off base score exactly, then add a dimensionally consistent waiting-time penalty:

`S_queue-aware(j) = S_tradeoff(j) + λ * W_queue(j)`

Both terms are simulated seconds and `λ` is a dimensionless, explicit experiment parameter. Initial engineering default: `λ = 1.0`; sensitivity checks should include `λ = 0` and predeclared positive alternatives. `λ = 0` must select exactly the same candidate as the isolated Trade-Off scoring component, including candidate order on ties. Do not tune λ against acceptance output. The selected candidate's `historyMap` count is incremented once, as in the base algorithm.

Overloaded nodes receive higher estimated waits but are not removed solely for being busy. Existing architecture, resource, and reachability eligibility remains authoritative. If workload data are unavailable, use the unchanged Trade-Off base score for that candidate and record the estimate as unavailable; do not substitute an invented zero in reported metrics. Invalid service capacity makes queue estimation unavailable and an ineligible sensor remains excluded by the existing candidate filter.

## 5. Integration

- `QueueAwareTradeOffOrchestrator` extends the paper-aligned eligibility adapter; `DefaultOrchestrator` and its Trade-Off implementation are unchanged.
- `QueueAwareComputingNode` tracks active tasks only in Queue-Aware runs through PureEdgeSim's `SimulationAbstract.setCustomComputingNode(Class)` hook. Its superclass retains execution, queue, and lifecycle transitions.
- `QueueAwareScoring` isolates the estimator and score for unit testing. The estimator creates no task events and mutates no task lifecycle state.
- `QueueAwareMain` installs the adapter. `raw/queue_decisions.csv` records each candidate's base score, wait estimate (blank when unavailable), combined score, active/queued counts, and selection.
- Runner, manifest, analyzer, and matrix support `queue-aware` and its configured λ. The manifest's algorithm label is `QUEUE_AWARE_TRADE_OFF`.

## 6. Workload levels and comparison matrix

The current paper-aligned generator interprets application rates as tasks per simulated second per UE. At 10 UEs, largest-remainder assignment gives 2/3/5 UEs for the three app profiles. With rates 20/30/3 tasks/s and lengths 500/5,000/30,000 MI, that is 145 tasks/s or **920,000 MI/s** of offered work. The 20- and 30-UE conditions scale linearly to 1,840,000 and 2,760,000 MI/s. These are generated offered loads, not measured executed throughput.

For the initial load-sensitivity experiment, hold the destination architecture at `EDGE_DC_ONLY`. The four configured EDCs provide `4 * 10 * 40,000 = 1,600,000 MIPS` aggregate capacity. Thus the estimated offered-load ratios are:

| Label | UEs | Offered work | EDC aggregate capacity | Offered-load ratio |
|---|---:|---:|---:|---:|
| Low | 10 | 0.92M MI/s | 1.60M MIPS | 0.575 |
| Medium | 20 | 1.84M MI/s | 1.60M MIPS | 1.15 |
| High | 30 | 2.76M MI/s | 1.60M MIPS | 1.725 |

These labels are theoretical offered-load ratios for this fixed architecture; they are not observed utilization and must not be generalized to other architecture targets. Comparisons within each load condition use the same UE count, profiles, apps, EDC/Cloud resources, duration, network parameters, seed, and workload; only the orchestrator differs. The initial matrix is 3 algorithms × 3 load levels × `EDGE_DC_ONLY`. Additional target architectures can be a separate matrix with their own declared capacity denominator.

## 7. Reproducibility and metrics

The simulator does not expose a shared seed option. Audit found `SecureRandom.getInstanceStrong()` in `DefaultTaskGenerator`, `DefaultComputingNodesGenerator` (including random UE positions), and `DefaultMobilityModel`. The experiment adapters now seed task-source assignment, UE initial positions, and per-UE mobility using the supplied `paper.seed`; the technical baseline's default randomness is untouched. The acceptance run verified identical source task/UE/position traces across Trade-Off, Round Robin, and Queue-Aware at seed 8128. A separate repeated-run identity check remains necessary before formal claims.

Required reported fields retain the existing lifecycle definitions: generated, sent, completed, terminal failures, pending, per-layer dispatch, and per-layer successful completions. Primary outcome: `completed / generated`. Failure and pending rates also use generated as denominator. Report latency and waiting means only for completed tasks and preserve N/A when the source value is absent. Keep energy scope/units as recorded by the current analyzer. Add queue diagnostics: candidate estimates observed, mean/median selected-candidate wait estimate, and per-layer decision-time workload summaries. These are estimates at decision time, not actual queue wait; actual task waiting remains sourced from `TaskAbstract.getWatingTime()` after execution.

## 8. Risks and test plan

- Active-task progress is estimated from scheduled start and nominal service rate. This assumes the current PureEdgeSim service model (`length / mipsPerCore`) and no preemption.
- The queue prediction excludes future arrivals and RAM availability interactions; report this limitation and compare its estimate with observed waiting time before interpreting it.
- A scoring weight that is too large can overwhelm the original Trade-Off preference. Prespecify λ and report sensitivity rather than selecting the best result after the fact.
- Random layout/mobility and the current application-to-UE assignment prevent paired comparison until the seed-controlled adapter is implemented and verified.
- Existing lifecycle regression checks and destination validations remain mandatory.

Required pure tests cover empty queue, one queued task, multiple queue lengths, heterogeneous MIPS/core counts, equal waits/tie order, zero/invalid capacity, overload, unavailable estimate fallback, λ=0 equivalence, and a baseline Trade-Off regression. These Java helper tests passed. The Python suite passed (19 tests, 2 opt-in acceptance tests skipped by default), and the paired 200-second acceptance passed for Trade-Off, Round Robin, and Queue-Aware with seed 8128 and zero manifest validation errors. It verified lifecycle accounting, matching source traces, queue audit output, and analyzer metrics. In this low-load smoke, selected estimated queue wait was 0 seconds; this is consistent with the chosen load and available cores, and does not validate behavior under the medium/high offered loads. The nine-run matrix is prepared but has not been run. Repeat-run identity and medium/high load acceptance remain before formal experiments.
