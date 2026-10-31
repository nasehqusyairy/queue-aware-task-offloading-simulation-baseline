# Experiment protocol

1. Select the built-in PureEdgeSim algorithm (`TRADE_OFF` or `ROUND_ROBIN`), UE count, duration, and destination target. The paper-aligned profile supports the six target labels in `scripts/paper_experiment.py`, 10/20/30 UEs, four configured Edge Data Centers, and a 200-second default horizon.
2. `run.sh` creates a unique run directory, copies the chosen configuration, builds PureEdgeSim, compiles the experiment adapters, and invokes the simulator. The `paper-aligned-baseline` profile is a technical implementation, not a validated reproduction of the paper.
3. `manifest.json` records parameters, config hashes, simulator revision, command, status, and validation errors. Treat `status != completed` as an invalid run; preserve its artifacts for diagnosis.
4. `analyze.py` extracts metrics from authentic PureEdgeSim CSVs. Run-level validation failures are preserved separately from metric/parser validation failures. Missing source values remain `null`/N/A, not zero.
5. Run repeated experiments only after the smoke acceptance test is valid. The wrapper currently does not control a deterministic RNG seed; the simulator uses `SecureRandom`, so repeatability is not guaranteed.

## Methodological caveats

- The six target labels are mapped to PureEdgeSim's built-in layer names. Their equivalence to the paper's exact experimental definitions still needs verification against the full methods section.
- The current task generator interprets each application `rate` as tasks per simulated second per UE assigned to that application profile. This is an explicit implementation interpretation, not a verified claim about the paper's rate semantics. PureEdgeSim's default task generator uses a different generation loop, so this mapping must be checked before reporting paper-equivalent results.
- UE positions, EDC placement, resource values, energy values, network settings, metric definitions, and cutoff handling must be checked against the paper before calling the setup a reproduction.
- GNN, DQN, and Queue-Aware algorithms are not implemented in this baseline.
