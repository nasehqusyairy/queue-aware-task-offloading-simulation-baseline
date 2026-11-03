# Experiment protocol

1. Select Trade-Off, Round Robin, or the experimental Queue-Aware extension, UE count, duration, and destination target. Queue-Aware extends Trade-Off and is available only in the paper-aligned profile. The paired load matrix uses 10/20/30 UEs and `EDGE_DC_ONLY` for all methods.
2. `run.sh` creates a unique run directory, copies the chosen configuration, builds PureEdgeSim, compiles the experiment adapters, and invokes the simulator. The `paper-aligned-baseline` profile is a technical implementation, not a validated reproduction of the paper.
3. `manifest.json` records parameters, config hashes, simulator revision, command, status, and validation errors. At a paper-profile hard horizon, generated tasks are partitioned into completed, terminally failed, and pending. The required invariant is `generated = completed + terminally_failed + pending`. Pending work is not reclassified as failure.
   `sent` counts tasks accepted into the orchestration pipeline. Pre-send source failures are also reported as `rejected_before_pipeline_tasks`, a subset of terminal failures.
4. PureEdgeSim layer totals count tasks dispatched to a layer. Layer successful-completion counts exclude terminal failures and pending work, and must sum to global completed tasks. A task is complete only after its result returns to its source UE.
5. `analyze.py` extracts explicit lifecycle metrics from authentic PureEdgeSim CSVs. Success, failure, and pending rates use generated tasks as the denominator. Run-level validation failures are preserved separately from metric/parser validation failures. Missing source values remain `null`/N/A, not zero.
6. Supply the same `--seed` to paired runs. The experiment adapters seed task-source assignment, UE initial placement, and mobility; the checked-in baseline path remains unchanged. This supports paired comparisons, but repeat-run verification is still required before formal claims.

## Queue-Aware extension

Queue-Aware selects among the same eligible destinations as Trade-Off using `S_tradeoff + λ × W_queue`. `W_queue` estimates how long the candidate's current active and FIFO queued work would occupy its cores, in simulated seconds. `--queue-weight` sets the dimensionless λ (default 1.0); λ=0 reduces the score to Trade-Off, subject to the same candidate order for ties. Every candidate score and wait estimate is retained in `raw/queue_decisions.csv`; missing estimates remain unavailable and fall back to the base score.

The estimate assumes nominal per-core service continues and no future tasks arrive. It does not model future network transit, RAM interactions, or failures. Queue estimates are diagnostics, not observed task waiting time. Compare them with completed-task waiting values in `metrics.json`, and report both distinctly. The initial matrix has nine conditions (three methods × three loads); inspect it with `scripts/run_queue_aware_matrix.py --dry-run` before execution. Do not infer algorithm benefit from the acceptance smoke run.

## Methodological caveats

- The six target labels are mapped to PureEdgeSim's built-in layer names. Their equivalence to the paper's exact experimental definitions still needs verification against the full methods section.
- The current task generator interprets each application `rate` as tasks per simulated second per UE assigned to that application profile. This is an explicit implementation interpretation, not a verified claim about the paper's rate semantics. PureEdgeSim's default task generator uses a different generation loop, so this mapping must be checked before reporting paper-equivalent results.
- UE positions, EDC placement, resource values, energy values, network settings, metric definitions, and cutoff handling must be checked against the paper before calling the setup a reproduction.
- Deadline checks use PureEdgeSim's accumulated network time + queue waiting time + CPU time, evaluated after results return to the UE. Result-return transfer time is included, and delay equal to the maximum latency fails. Tasks still pending at cutoff are not latency failures unless they reached the deadline failure event first.
- GNN and DQN are not implemented. Queue-Aware is an experimental heuristic and has not been validated as a paper reproduction.
