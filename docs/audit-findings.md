# Repository audit findings

## Confirmed bugs and repairs

1. **Cutoff tasks were misreported as failures.** `PaperAlignedSimulationManager` added `sentTasks - tasksCount` to `SimLog.tasksFailed` at the hard horizon. In-flight work therefore became terminal failure, while PureEdgeSim had already incremented the destination layer's task count at dispatch. The 58-task discrepancy was consistent with this timing mismatch. The adapter now reports pending separately and does not mutate the terminal failure counter at cutoff.
2. **Layer “successful” counts included in-flight tasks.** Upstream `SimLog.taskSentFromOrchToDest()` increments `tasksExecutedOn*` when it dispatches work; the CSV's success fields subtract only terminal failures. The paper adapter tracks assigned destinations through terminal outcomes, and `SimLog` subtracts pending by destination when reporting successful completions. Layer totals remain dispatch counts.
3. **CSV lifecycle fields were absent and initially misaligned.** The CSV did not expose sent, completed, terminal failure, or pending counts. Explicit columns are now appended after the complete legacy row. A missing comma found during the first smoke test shifted the fields; this was fixed and covered by the final acceptance run.
4. **Cutoff accounting did not guard against duplicate terminal events.** The paper adapter now records task IDs after their first terminal outcome and ignores stale or duplicate lifecycle events. Cutoff validation checks nonnegative counts, the closed accounting equation, and that layer-pending counts do not exceed global pending.
5. **Mobility could move a UE just outside the map.** The upstream mobility model checked bounds before movement, allowing a timestep to cross a map edge. The position update now clamps to the configured rectangle. This preserves the configured map and prevents invalid positions in coverage/connectivity audits.
6. **The analyzer conflated failures with generated minus successful.** It now reads explicit lifecycle columns, keeps pending separate, computes rates using generated tasks as denominator, reconciles layer success with global completion, and preserves manifest versus metric validation errors independently. Missing values remain null.

The earlier issues in the repository history remain addressed: orchestrator observation after assignment, strict missing/mismatched orchestrator validation, destination eligibility by reachability, and analyzer preservation of manifest errors.

## Implemented definitions

- **Generated:** all tasks created by the task generator.
- **Sent:** tasks accepted into PureEdgeSim's orchestration pipeline (`incrementTasksSent`); generated tasks that fail before that point remain part of generated and terminal failure accounting.
- **Completed:** tasks whose result reaches the source UE within the simulation horizon.
- **Terminally failed:** tasks receiving one terminal failure reason before cutoff. Pending tasks do not enter this count.
- **Pending:** `generated - completed - terminally_failed` at cutoff, including generated work not yet sent and work still in flight.
- **Closed accounting:** `generated = completed + terminally_failed + pending`.
- **Rejected before pipeline:** a subset of terminal failures that failed at the pre-send source check; reported separately and included in `terminally_failed` (never added twice).
- **Layer dispatched:** tasks assigned and submitted toward a Cloud, Edge Data Center, or Mist/UE destination. This is an attempt/dispatch count, not a completion count.
- **Layer successful completion:** dispatched tasks that completed their full return path, excluding terminal failures and tasks pending at cutoff. Local execution is attributed to the source UE (Mist/UE layer).
- **Success, failure, and pending rates:** each respective count divided by generated tasks; zero generated gives an unavailable rate.

`Task.getTotalDelay()` is `actualNetworkTime + waitingTime + actualCpuTime`. The framework checks `totalDelay >= maxLatency` at `RESULT_RETURN_FINISHED`, after the result has been transferred back to the UE. Therefore it includes accumulated request/orchestration and result network transfers, queue wait, and CPU execution. Equality to the deadline is a failure. Other phase failures return before latency classification, so one task is assigned one failure reason in the normal lifecycle. Cutoff by itself does not cause latency failure.

## Verification

- Python unit suite: 15 tests passed; the opt-in acceptance test is skipped in ordinary discovery (it passed when run explicitly).
- Python compilation and shell syntax: passed.
- Maven `package -DskipTests`: passed and produced 86 compiled PureEdgeSim class files.
- Java deadline policy check: passed (below/equal/above boundaries, zero deadline, and invalid values).
- 200-second `EDGE_DC_ONLY` acceptance test: passed on 2026-11-03.
- Final acceptance run accounting: generated 29,000; sent 29,000; completed 2,456; terminal failures 23,710; pending 2,834; rejected before pipeline 0. `29,000 = 2,456 + 23,710 + 2,834`. Cloud completed 0, Edge completed 2,456, Mist completed 0; layer completed sum equals global completed. All 2,834 pending tasks were assigned to Edge. The run ended at 200 seconds, status completed, with no manifest or metric validation errors. Repeated smoke runs varied materially, consistent with uncontrolled randomness; do not treat the workload outcome as a performance claim.

## Remaining limitations

- The baseline still uses only built-in Trade-Off and Round Robin; Queue-Aware, GNN, and DQN are not implemented.
- Application rate semantics, UE allocation, EDC coordinates, and some configuration values are implementation interpretations pending full methods-section verification. This is not a paper reproduction.
- PureEdgeSim's deadline metric excludes final result transmission time, as described above.
- Random seeds are not controlled; repeated runs are not guaranteed to be reproducible.
- The acceptance output is one technical smoke run and is not evidence of paper-methodology fidelity or general performance.
