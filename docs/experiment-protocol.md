# Experiment protocol

1. Select the built-in PureEdgeSim algorithm (`TRADE_OFF` or `ROUND_ROBIN`), UE count, duration, and destination target. The paper-aligned profile supports the six target labels in `scripts/paper_experiment.py`, 10/20/30 UEs, four configured Edge Data Centers, and a 200-second default horizon.
2. `run.sh` creates a unique run directory, copies the chosen configuration, builds PureEdgeSim, compiles the experiment adapters, and invokes the simulator. The `paper-aligned-baseline` profile is a technical implementation, not a validated reproduction of the paper.
3. `manifest.json` records parameters, config hashes, simulator revision, command, status, and validation errors. At a paper-profile hard horizon, generated tasks are partitioned into completed, terminally failed, and pending. The required invariant is `generated = completed + terminally_failed + pending`. Pending work is not reclassified as failure.
   `sent` counts tasks accepted into the orchestration pipeline. Pre-send source failures are also reported as `rejected_before_pipeline_tasks`, a subset of terminal failures.
4. PureEdgeSim layer totals count tasks dispatched to a layer. Layer successful-completion counts exclude terminal failures and pending work, and must sum to global completed tasks. A task is complete only after its result returns to its source UE.
5. `analyze.py` extracts explicit lifecycle metrics from authentic PureEdgeSim CSVs. Success, failure, and pending rates use generated tasks as the denominator. Run-level validation failures are preserved separately from metric/parser validation failures. Missing source values remain `null`/N/A, not zero.
6. Run repeated experiments only after the smoke acceptance test is valid. The wrapper currently does not control a deterministic RNG seed; the simulator uses `SecureRandom`, so repeatability is not guaranteed.

## Methodological caveats

- The six target labels are mapped to PureEdgeSim's built-in layer names. Their equivalence to the paper's exact experimental definitions still needs verification against the full methods section.
- The current task generator interprets each application `rate` as tasks per simulated second per UE assigned to that application profile. This is an explicit implementation interpretation, not a verified claim about the paper's rate semantics. PureEdgeSim's default task generator uses a different generation loop, so this mapping must be checked before reporting paper-equivalent results.
- UE positions, EDC placement, resource values, energy values, network settings, metric definitions, and cutoff handling must be checked against the paper before calling the setup a reproduction.
- Deadline checks use PureEdgeSim's accumulated network time + queue waiting time + CPU time, evaluated after results return to the UE. Result-return transfer time is included, and delay equal to the maximum latency fails. Tasks still pending at cutoff are not latency failures unless they reached the deadline failure event first.
- GNN, DQN, and Queue-Aware algorithms are not implemented in this baseline.
