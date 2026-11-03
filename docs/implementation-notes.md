# Implementation notes

- Upstream revision is recorded in each run manifest; source repository has its own GPL-3.0 LICENSE.
- Upstream Maven package was checked on the current Java 25 / Maven 3.9.12 environment.
- Baseline configuration is a working copy distinct from the upstream default files.
- Data extraction intentionally returns null/N/A for fields not confidently identified. Validate log format before adding a parser.
- The paper-aligned simulation manager records exactly one terminal outcome per task ID, leaves cutoff-pending tasks nonterminal, reports terminal failures rejected before the pipeline as a subset, and emits a runtime accounting invariant. Its CSV adds explicit sent/completed/terminal-failed/pending/rejected columns after all legacy columns. Generic technical-baseline runs have no hard-cutoff pending classification and leave appended pending/rejected fields empty.
- PureEdgeSim's `Total tasks executed (layer)` is a destination dispatch counter. At the paper-aligned horizon, successful-completion columns subtract both layer failures and unresolved tasks assigned to that layer.
- `Task.getTotalDelay()` is network transfer time + queue waiting time + CPU time. The phase-3 deadline test runs after the result returns to the UE, so result-return network time is included. A delay equal to the configured deadline is a latency failure.
- Deadline classification uses `DeadlinePolicy.isExceeded`: equality fails, zero deadline expires at zero delay, and negative/non-finite delays or deadlines raise an explicit configuration/runtime error. The executable Java test covers these boundaries.
- The mobility model now clamps a movement step to the configured map rectangle after the existing orientation check, which could otherwise allow a timestep to cross the boundary.
- Acceptance run evidence and root causes are recorded in `docs/audit-findings.md`.
- Future Queue-Aware approach should be a new class extending upstream `Orchestrator` or `DefaultOrchestrator`, set through `Simulation.setCustomEdgeOrchestrator`, without changing upstream files.
