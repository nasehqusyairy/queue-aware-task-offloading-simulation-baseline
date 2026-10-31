# Paper parameters and current implementation mapping

Paper reference: Garmendia-Orbegozo, Núñez-González & Antón (2024), DOI 10.32604/cmes.2024.045912. The table below describes the current repository implementation; it does not certify equivalence with the paper.

| Paper-related item | Current implementation | Validation status |
|---|---|---|
| 10, 20, 30 user devices | Supported by `run.sh`; largest-remainder allocation assigns integer device counts to five profiles | Code-level tests pass; paper allocation semantics still need confirmation |
| Four Edge Data Centers | Four EDCs configured at fixed coordinates in `configs/paper-aligned/edge_datacenters.xml` | Configured; coordinates are implementation choices unless verified from the paper |
| 200-second duration | `paper-aligned-baseline` defaults to 200 seconds and converts to PureEdgeSim's minute property | Code-level test passes |
| Trade-Off and Round Robin | Built-in algorithms selected through PureEdgeSim's `DefaultOrchestrator` | Implemented; end-to-end runtime must be tested |
| Six destination configurations | Mapped to PureEdgeSim layer names in `scripts/paper_experiment.py` | Mapping tests pass; exact paper definitions still require review |
| GNN and DQN | Not implemented | Out of scope for this baseline |
| Queue-Aware algorithm | Not implemented | Future contribution; do not report as current result |
| Three repetitions | Separate runs can be launched, but automated repetition and controlled seeds are not implemented | Not yet reproducible by design |
| Task rates | Custom generator applies each application rate per simulated second per assigned UE | Explicit implementation interpretation; verify against paper before claiming fidelity |
| Success, energy, workload | Extracted conservatively from PureEdgeSim CSV output | Metric definitions and full runtime behavior still require validation |

## Important distinction

A run marked `completed` means the current program's validation checks passed; it does not, by itself, prove that the configuration, task-generation semantics, or metrics reproduce the paper. The baseline is technical infrastructure for later experiments, not a paper reproduction or a Queue-Aware/GNN/DQN result.
