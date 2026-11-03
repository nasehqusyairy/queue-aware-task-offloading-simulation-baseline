# Workload Imbalance Experiment — Design and Feasibility

## Design decision

The user selected **Option A: virtual ingress/home-EDC demand attribution**. The home EDC is a workload accounting label, not an execution destination. Tasks remain attached to their original UE, and Trade-Off or Queue-Aware chooses the actual destination using the same existing candidate eligibility and scoring code. The intervention does not alter UE positions, EDC coverage/capacity, baseline rates, global application totals, total tasks, or total MI.

The 4×3 matrix assigns the unchanged application-profile user totals to four virtual ingress groups. Each generated task's home EDC receives its application task length in the offered-work audit. This is a documented model extension: it represents offered demand per virtual ingress but does not physically preload execution queues at the home EDC.

## Source and configuration basis

- `PaperAlignedTaskGenerator.generate()` previously generated tasks per UE and application profile; no home EDC was represented. The new optional home matrix adds task-keyed accounting while keeping task source UE, release, task length, and destination decision separate.
- `SeededMobilityModel.configureSeed()` samples UE positions over the unchanged 200×200 m map. `PaperAlignedOrchestrator.isReachableEdgeDataCenter()` retains the existing 71 m radial EDC eligibility check. Therefore four EDCs are valid candidates globally, but each task may have fewer than four candidates.
- Four configured EDCs remain symmetric at 10 cores × 40,000 MIPS, 16,000 MB RAM, with the configured 100/250 W idle/maximum power values. No network or coverage parameter changed.
- Existing λ-sensitivity evidence had 43/77 decisions with one candidate and 34/77 with two. This is why UE clustering or destination pinning was excluded: it would change or constrain the studied candidate choice.
- `ComputingNode` exposes direct average/current CPU utilization and energy model values. These are now exported per EDC; task counts are not used as a utilization proxy.

## Workload conditions

Total generated demand is held at 2,175 tasks and 13.8M MI. Task rates, global app-user totals, UE count, app mix totals, EDC config, destination rule, estimator, and formula stay fixed.

| Condition | Home EDC 1 | Home EDC 2 | Home EDC 3 | Home EDC 4 | Task counts EDC1–4 |
|---|---:|---:|---:|---:|---|
| Balanced | 25.0% | 25.0% | 25.0% | 25.0% | 240, 240, 615, 1,080 |
| Moderate | 39.9% | 30.1% | 19.9% | 10.1% | 755, 710, 565, 145 |
| Severe | 69.9% | 15.2% | 9.8% | 5.1% | 1,420, 195, 45, 515 |

Shares are based on generated MI per virtual home EDC. Balanced refers to MI rather than equal task count; application profiles have different task lengths. Home labels are not mapped from UE nearest-EDC geography. Actual execution assignments remain a separate measured outcome. UE clustering, task pinning, and coverage/capacity alterations are excluded.

## Pilot gate and outcome

The seed-1 pilot contained 9 runs (three conditions × three methods). The gate required equal task/work totals and application counts, paired configuration and task source/application/home inputs, unchanged source positions/eligibility code between methods, all four EDC IDs observed as candidates across Queue-Aware decisions, and per-EDC state output.

**Pilot passed.** All 9 runs exited 0; all 2,175 tasks and 13.8M MI reconciled; the actual home shares matched the intended profiles; task keyed inputs and source positions matched between methods; four EDCs were observed as candidates across each Queue-Aware run; and all four EDCs had horizon state rows. Candidate eligibility remains source-specific under the shared 71 m rule. The run logs and pilot validation are in [`run_status.json`](run_status.json) and [`analysis_validation.json`](analysis_validation.json).

The full paired 45-run matrix then completed with 0 run failures. See [`REPORT.md`](REPORT.md) for measurements and the interpretation boundary.

## Remaining limitation

Virtual home demand is not a physical ingress queue. The experiment measures an imbalanced workload-demand attribution, then observes where the unchanged scheduler executes tasks and what queues/utilization result there. A claim about preloaded physical home-EDC overload requires a further ingress/forwarding model that preserves destination selection. Per-task candidate sets are not all four EDCs under the unchanged coverage rule; source-specific eligibility is held identical between methods within each pair, and its remaining effect is disclosed in the report.
