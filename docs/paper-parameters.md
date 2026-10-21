# Paper parameters and current mapping

Paper reference: Garmendia-Orbegozo, Núñez-González & Antón (2024), DOI 10.32604/cmes.2024.045912. This repo has not verified the paper's complete six-target definitions against the article's full methods text.

| Paper target | Current technical baseline |
|---|---|
| 10, 20, 30 user devices | run.sh supports arbitrary positive integer; use 10/20/30 |
| 4 Edge Data Centers | not yet enforced; upstream default settings have one DC entry |
| 200-second duration | not yet mapped; PureEdgeSim property uses minutes; wrapper defaults 10 minutes |
| Trade-Off and Round Robin | implemented in upstream DefaultOrchestrator and selectable |
| GNN and DQN | not included or claimed |
| Six destination configurations | not configured yet; one architecture selected per run |
| Three repetitions | multiple separate invocations; automated repetition/seed control not available |
| success, energy, workload | success parser remains conservative; energy/workload may remain N/A |
