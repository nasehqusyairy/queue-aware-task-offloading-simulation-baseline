# Implementation notes

- Upstream revision is recorded in each run manifest; source repository has its own GPL-3.0 LICENSE.
- Upstream Maven package was checked on the current Java 25 / Maven 3.9.12 environment.
- Baseline configuration is a working copy distinct from the upstream default files.
- Data extraction intentionally returns null/N/A for fields not confidently identified. Validate log format before adding a parser.
- Future Queue-Aware approach should be a new class extending upstream `Orchestrator` or `DefaultOrchestrator`, set through `Simulation.setCustomEdgeOrchestrator`, without changing upstream files.
