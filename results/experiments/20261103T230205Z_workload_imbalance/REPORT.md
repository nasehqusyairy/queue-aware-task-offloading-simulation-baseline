# Experiment Report — Workload Imbalance and Queue-Aware Offloading

## 1. Objective and hypothesis

Test whether Queue-Aware λ=0.5 or λ=1.0 changes destination decisions and performance under balanced, moderate, and severe **virtual ingress workload demand** across four EDCs, compared with Trade-Off.

Hypothesis: as virtual ingress demand becomes more skewed, Queue-Aware may respond to actual destination queues and redistribute execution. A destination shift does not itself imply a performance improvement.

## 2. Design and validity boundary

### Selected workload model

The user selected Option A: **virtual ingress/home-EDC demand attribution**. Each generated task is assigned a `home_edc_id` in `raw/home_workload.csv` for workload accounting. This ID is not passed to the orchestrator as a selected destination and does not pin the task. Tasks remain attached to their source UE; the existing Trade-Off or Queue-Aware scheduler selects the actual EDC from the existing eligible candidate set.

Application user totals and generated workload were held constant in every condition: 6 Hard real-time, 9 Soft real-time, and 15 Non-real-time UE groups; 2,175 tasks and 13,800,000 MI per run. The per-condition 4×3 matrix assigns those application groups to virtual home EDCs; the exact matrix is in [`workload_profiles.json`](workload_profiles.json). The home assignment is deterministic from the paired seed and condition.

### Measured workload strata

The workload label is based on task length × generated task count (offered MI), not task count alone:

| Condition | EDC 1 | EDC 2 | EDC 3 | EDC 4 | Offered tasks EDC1–4 | CV of four EDC work shares |
|---|---:|---:|---:|---:|---|---:|
| Balanced | 25.0% | 25.0% | 25.0% | 25.0% | 240, 240, 615, 1,080 | 0.000 |
| Moderate | 39.9% | 30.1% | 19.9% | 10.1% | 755, 710, 565, 145 | 0.444 |
| Severe | 69.9% | 15.2% | 9.8% | 5.1% | 1,420, 195, 45, 515 | 1.047 |

Each condition still has 13.8M MI total. The balanced task counts are unequal because application profiles have different task lengths; the balanced criterion is equal offered MI, not equal task count. Home labels are deterministic virtual groups and do not encode the UE's nearest-EDC geography. EDC capacities and network parameters are unchanged. **Interpretation boundary:** virtual ingress shares are demand attribution labels. They do not preload physical EDC execution queues. Physical queue pressure occurs at the EDC selected by the simulator. Therefore this study tests performance under an imbalanced virtual ingress-demand profile while leaving execution free; it does not claim that ingress loads themselves were physically queued at home EDCs.

## 3. Code and configuration changes

- [`PaperAlignedTaskGenerator.java`](../../../experiment/src/com/mechalikh/pureedgesim/experiment/PaperAlignedTaskGenerator.java): accepts the optional 4×application home matrix; validates matrix column totals against unchanged global app user counts; records task ID, home EDC, source UE, application, release time, and task length to `home_workload.csv`. With no matrix property, it keeps the existing application allocation path.
- [`execute_run.py`](../../../scripts/execute_run.py): validates condition/matrix input, records its semantics in the manifest, passes the experiment properties to Java, and checks that the home audit is produced.
- [`PaperAlignedSimulationManager.java`](../../../experiment/src/com/mechalikh/pureedgesim/simulationmanager/PaperAlignedSimulationManager.java), [`TaskTracingComputingNode.java`](../../../experiment/src/com/mechalikh/pureedgesim/experiment/TaskTracingComputingNode.java), and [`TaskTracingQueueAwareComputingNode.java`](../../../experiment/src/com/mechalikh/pureedgesim/experiment/TaskTracingQueueAwareComputingNode.java): add event-time EDC state observations for active tasks, waiting queue length, direct CPU utilization values, and computing/network energy; write a final state row for each EDC at the simulation horizon.
- [`execute_workload_imbalance.py`](execute_workload_imbalance.py), [`analyze_workload_imbalance.py`](analyze_workload_imbalance.py), and [`workload_profiles.json`](workload_profiles.json): experiment execution, gated pilot, pairing checks, per-EDC aggregation, statistics, and chart generation.
- No EDC configuration, coverage, baseline task rates, Queue-Aware estimator/formula, eligibility rule, or Trade-Off selection code was changed. The TaskTracing classes add observations only.

Repository commit at experiment start: `d26dc67dd6712c7fc4cb825f4a7f34f1ac0eeeda`. PureEdgeSim revision: `bcdd239fa301bd7164526dc47685058288c305ef`.

## 4. Experiment configuration and execution

| Parameter | Value |
|---|---|
| Experiment ID | `20261103T230205Z_workload_imbalance` |
| UE / EDC | 30 / 4 |
| Duration | 5 simulated seconds |
| Destination | `EDGE_DC_ONLY` |
| Methods | Trade-Off; Queue-Aware λ=0.5; Queue-Aware λ=1.0 |
| Conditions | balanced; moderate; severe virtual ingress work |
| Seeds | 1, 8128, 4401, 2026, 2027 |
| Planned / completed / failed | 45 / **45 / 0** |

Exact execution command:

```bash
python3 results/experiments/20261103T230205Z_workload_imbalance/execute_workload_imbalance.py --full
```

The runner executes the nine seed-1 pilot cells first and gates the remaining 36 on the pilot checks. All nine pilot runs exited 0, passed manifest/metric validation, preserved 2,175 tasks and 13.8M MI, produced nonzero queue estimates, and observed candidate IDs for all four EDCs across each Queue-Aware run. The pilot and full matrix status are in [`run_status.json`](run_status.json) and [`analysis_validation.json`](analysis_validation.json).

## 5. Pairing and destination verification

There are 30 paired comparisons: two Queue-Aware weights × three conditions × five seeds. For every pair, the validator confirmed:

- simulator configuration hashes/properties, profile, device count, duration, destination config, simulator revision, and seed match;
- the task-keyed home labels, task lengths, source UE IDs, application IDs, and source positions match between methods;
- 2,175 destination records and home workload records reconcile per run;
- all four EDC IDs appeared as Queue-Aware candidate destinations across each run; source eligibility remains governed by the unchanged 71 m coverage rule, so not every task has all four candidates;
- each run has final active/queue/utilization/energy state for four EDCs.

Destination assignments remain scheduler outcomes, independent from the home labels. Mean actual assignment counts (EDC1–EDC4; all sum to 2,175) were:

| Condition | Trade-Off | Queue-Aware λ=0.5 | Queue-Aware λ=1.0 |
|---|---|---|---|
| Balanced | 581, 585, 475, 534 | 525, 607, 509, 534 | 513, 625, 507, 530 |
| Moderate | 613, 569, 448, 545 | 577, 537, 466, 595 | 577, 519, 472, 607 |
| Severe | 544, 603, 503, 525 | 518, 541, 483, 633 | 518, 517, 483, 657 |

These actual assignments do not reproduce the virtual ingress proportions. This is expected under the accounting-only home label and is a limit on interpreting the study as physical home-EDC queue overload.

## 6. Aggregate performance results

Mean ± sample SD over five seeds. Completion rate = completed/generated. Failed is simulator terminally failed; pending is unresolved at the 5-second horizon. Energy is the existing simulator total in Wh (computing nodes across UE + EDC + Cloud; network energy is separate). Delay and actual waiting are simulator averages among completed tasks only.

| Condition | Method | Completed | Failed | Pending | Completion rate | Energy (Wh) | Total delay (s) | Actual wait (s) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Balanced | Trade-Off | 114.6 ± 7.0 | 1075.8 ± 45.9 | 984.6 ± 43.2 | 5.269 ± 0.323% | 3.0628 ± 0.0105 | 6.477 ± 0.042 | 0.906 ± 0.042 |
| Balanced | QA λ=0.5 | 116.0 ± 6.2 | 1065.6 ± 23.8 | 993.4 ± 22.8 | 5.333 ± 0.283% | 3.0626 ± 0.0157 | 6.512 ± 0.054 | 0.941 ± 0.053 |
| Balanced | QA λ=1.0 | 115.4 ± 6.5 | 1066.2 ± 23.6 | 993.4 ± 22.8 | 5.306 ± 0.301% | 3.0625 ± 0.0157 | 6.509 ± 0.051 | 0.939 ± 0.050 |
| Moderate | Trade-Off | 113.8 ± 4.3 | 1139.4 ± 71.6 | 921.8 ± 68.1 | 5.232 ± 0.199% | 3.0768 ± 0.0109 | 6.653 ± 0.079 | 1.082 ± 0.080 |
| Moderate | QA λ=0.5 | 114.4 ± 4.2 | 1135.4 ± 43.7 | 925.2 ± 41.4 | 5.260 ± 0.194% | 3.0792 ± 0.0107 | 6.651 ± 0.051 | 1.079 ± 0.052 |
| Moderate | QA λ=1.0 | 115.4 ± 5.4 | 1122.2 ± 37.9 | 937.4 ± 33.8 | 5.306 ± 0.249% | 3.0745 ± 0.0113 | 6.667 ± 0.028 | 1.096 ± 0.028 |
| Severe | Trade-Off | 110.8 ± 9.0 | 1143.4 ± 59.5 | 920.8 ± 56.8 | 5.094 ± 0.413% | 3.0725 ± 0.0102 | 6.904 ± 0.085 | 1.334 ± 0.086 |
| Severe | QA λ=0.5 | 104.6 ± 6.7 | 1179.0 ± 46.3 | 891.4 ± 43.5 | 4.809 ± 0.306% | 3.0826 ± 0.0194 | 6.911 ± 0.085 | 1.341 ± 0.085 |
| Severe | QA λ=1.0 | 105.4 ± 5.5 | 1168.4 ± 39.2 | 901.2 ± 37.4 | 4.846 ± 0.253% | 3.0800 ± 0.0109 | 6.928 ± 0.042 | 1.357 ± 0.042 |

## 7. Queue decisions and per-EDC measurements

Queue-Aware observed nonzero estimates in every condition and weight. Across the five runs per setting:

| Condition | λ | Nonzero / available candidate estimates | Maximum observed estimate (s) | Rank changes total | Selected destination changes total |
|---|---:|---:|---:|---:|---:|
| Balanced | 0.5 | 278 / 480 | 4.573 | 32 | 32 |
| Balanced | 1.0 | 280 / 482 | 4.573 | 39 | 39 |
| Moderate | 0.5 | 263 / 477 | 5.310 | 18 | 18 |
| Moderate | 1.0 | 261 / 475 | 5.310 | 21 | 21 |
| Severe | 0.5 | 276 / 500 | 4.630 | 42 | 42 |
| Severe | 1.0 | 281 / 505 | 3.935 | 46 | 46 |

The estimator records decision-time candidate queue state. Trade-Off has no estimator output, so estimate fields are not applicable to that method. `edc_node_state.csv` adds direct event-time active/waiting counts, current and average CPU utilization from `ComputingNode`, and computing/network energy values from the simulator's energy model. At horizon, utilization values were near the API's 100% cap in most EDCs; this saturation limits between-node discrimination. Per-EDC task outcomes and queue, utilization, and energy summaries for all 45 runs are available in [`edc_metrics_by_run.csv`](edc_metrics_by_run.csv) and [`edc_summary_across_seeds.csv`](edc_summary_across_seeds.csv). Actual completed-task waiting time is joined from task trace completion events; missing samples remain blank, not zero.

Per-EDC computing energy is CPU energy from each EDC energy model, not total run energy and not network energy. The simulator's run-level energy includes UE, EDC, and Cloud computing nodes. The per-EDC direct state sample at horizon is a cumulative average; event state rows are available in each run's `raw/edc_node_state.csv`.

Contoh agregat per EDC pada **severe** condition (mean across five seeds):

| EDC | Virtual offered MI | Assignments TO / QA .5 / QA 1 | QA λ=1 completed / failed / pending | QA λ=1 queue estimate range (s) | QA λ=1 avg CPU utilization | QA λ=1 computing CPU energy (Wh) |
|---|---:|---:|---:|---:|---:|---:|
| EDC 1 | 9,650,000 | 544 / 518 / 518 | 25.4 / 272.2 / 220.4 | 0–2.82 | 100.0% | 0.3522 |
| EDC 2 | 2,100,000 | 603 / 541 / 517 | 32.0 / 222.0 / 263.0 | 0–3.40 | 100.0% | 0.3601 |
| EDC 3 | 1,350,000 | 503 / 483 / 483 | 24.0 / 300.2 / 158.8 | 0–1.72 | 100.0% | 0.3544 |
| EDC 4 | 700,000 | 525 / 633 / 657 | 24.0 / 374.0 / 259.0 | 0–2.53 | 99.7% | 0.3523 |

“Virtual offered MI” is an accounting demand label; assignments and outcome counts are actual simulator destination records joined to task terminal events. Queue estimate range is candidate-decision-time Queue-Aware output. Per-run snapshots and per-method/per-lambda aggregates for all three conditions are in the linked per-EDC CSV files.

![Verified virtual ingress MI shares](/home/nasyikhqusyairy/Projects/repositories/queue-aware-task-offloading-simulation-baseline/results/experiments/20261103T230205Z_workload_imbalance/charts/virtual_ingress_workload_shares.png)

![Completion rate by condition](/home/nasyikhqusyairy/Projects/repositories/queue-aware-task-offloading-simulation-baseline/results/experiments/20261103T230205Z_workload_imbalance/charts/completion_by_workload_condition.png)

## 8. Paired inference

Each Queue-Aware setting is paired against Trade-Off at the same condition and seed (n=5 pairs). Differences are Queue-Aware minus Trade-Off. Confidence intervals are paired t intervals (df=4); p-values are exact two-sided sign-flip tests over all 32 sign assignments. The full table, including completed/failed/pending, is in [`paired_statistics.csv`](paired_statistics.csv); per-seed deltas are in [`paired_by_seed_condition.csv`](paired_by_seed_condition.csv).

| Condition | λ | Δ completion (pp), 95% CI, p | Δ energy (Wh), 95% CI, p | Δ total delay (s), 95% CI, p | Δ actual wait (s), 95% CI, p |
|---|---:|---|---|---|---|
| Balanced | 0.5 | +0.064 [−0.085, +0.213], .500 | −0.0002 [−0.0180, +0.0176], 1.000 | +0.0347 [−0.0190, +0.0884], .125 | +0.0349 [−0.0195, +0.0893], .125 |
| Balanced | 1.0 | +0.037 [−0.038, +0.111], .500 | −0.0003 [−0.0182, +0.0176], 1.000 | +0.0323 [−0.0151, +0.0798], .125 | +0.0326 [−0.0156, +0.0808], .125 |
| Moderate | 0.5 | +0.028 [−0.024, +0.079], .500 | +0.0024 [−0.0088, +0.0136], .750 | −0.0028 [−0.0486, +0.0431], 1.000 | −0.0028 [−0.0486, +0.0431], 1.000 |
| Moderate | 1.0 | +0.074 [−0.101, +0.248], .500 | −0.0023 [−0.0176, +0.0130], .625 | +0.0141 [−0.0719, +0.1001], 1.000 | +0.0141 [−0.0719, +0.1000], 1.000 |
| Severe | 0.5 | −0.285 [−0.744, +0.174], .250 | +0.0101 [−0.0081, +0.0283], .500 | +0.0064 [−0.0269, +0.0397], 1.000 | +0.0066 [−0.0268, +0.0401], 1.000 |
| Severe | 1.0 | −0.248 [−0.530, +0.033], .250 | +0.0076 [−0.0103, +0.0254], .500 | +0.0233 [−0.0543, +0.1009], .500 | +0.0236 [−0.0541, +0.1013], .500 |

All listed confidence intervals include zero. With five seed pairs, exact p-values are coarse and the study has low power; this is exploratory evidence, not proof of equivalence.

## 9. Interpretation and limitations

- Queue-Aware changed more decisions in the severe virtual ingress profile than in the moderate profile, but it did **not** improve the measured outcomes consistently. In the severe profile, mean completion decreased by 0.25–0.29 pp and run-level energy increased by 0.0076–0.0101 Wh; delay and waiting also increased slightly. The paired intervals are inconclusive.
- Moderate showed small mixed changes: λ=1.0 had slightly higher completion and lower mean energy, while total delay and actual waiting increased slightly. None is distinguishable from seed variation here.
- Destination allocation shifted toward EDC4 as λ rose in moderate/severe profiles, but the ingress work label is not the physical execution destination. Queue-Aware responds to the actual queue estimates at destinations, not to the home label itself.
- Queue estimates and CPU utilization are different measures. Queue estimates are direct candidate-time observations of active/waiting state fed to the existing estimator; CPU utilization and energy are direct simulator API/model outputs. Destination allocation is not used as an utilization proxy.
- The 100% utilization cap means a large portion of EDC horizon averages are saturated. Workload profiles have identical global application totals but move application-profile UE assignments among virtual home groups; this is part of the workload intervention and can interact with the existing spatial eligibility geometry.
- Every UE does not have all four EDCs as candidates under the unchanged 71 m rule. All four were observed as candidates during each Queue-Aware run, but the eligible set varies by source location. Pairing preserves source IDs/positions between methods within each condition.
- Home workload is an experiment-only accounting label, not a modeled physical EDC ingress queue. For a claim specifically about preloaded physical EDC overload, the next design must add a real ingress/forwarding model while retaining the unchanged selection freedom, or explicitly revise the research question.

## 10. Recommended next experiment

Do not claim Queue-Aware improved performance from this result. Before another performance matrix, run a small instrumentation pilot for a **physical ingress** model: tasks enter an EDC-specific ingress queue, then the unchanged orchestrator chooses execution from the current eligible candidates. Validate ingress latency/state separately from execution placement, with identical offered workload across methods. If the research scope excludes adding that stage, treat the current results as a virtual-demand sensitivity study and increase seed count only after specifying how virtual demand is expected to affect task timing or source behavior.

## 11. Reproduction and artifacts

- Configuration: [`workload_profiles.json`](workload_profiles.json)
- Exact 45 commands: [`commands_run.txt`](commands_run.txt)
- Run manifest status: [`run_status.json`](run_status.json)
- Per-run manifests and raw simulator output: `runs/<condition>/<run_id>/`
- Per-task virtual ingress mapping: `runs/<condition>/<run_id>/raw/home_workload.csv`
- Per-EDC state snapshots: `runs/<condition>/<run_id>/raw/edc_node_state.csv`
- Task trace, destination audit, Queue-Aware decision audit: corresponding `raw/*.csv` files under each run
- Per-run aggregates: [`run_level.csv`](run_level.csv)
- Per-EDC per-run and across-seed values: [`edc_metrics_by_run.csv`](edc_metrics_by_run.csv), [`edc_summary_across_seeds.csv`](edc_summary_across_seeds.csv)
- Paired inputs/outcomes and inference: [`paired_by_seed_condition.csv`](paired_by_seed_condition.csv), [`paired_statistics.csv`](paired_statistics.csv)
- Charts: `charts/*.png`

## 12. Audit checklist

- [PASS] Design report completed before implementation; Option A then selected by user.
- [PASS] 45/45 runs completed; 0 run failures or manifest validation errors.
- [PASS] Same paired task sources, application labels, virtual ingress labels, lengths, source positions, seed, and simulator configuration between methods.
- [PASS] Total 2,175 generated tasks and 13.8M offered MI in every run.
- [PASS] Measured virtual ingress work shares match balanced/moderate/severe targets.
- [PASS] All four EDCs appeared as Queue-Aware candidates in each run; actual destination logged for every task.
- [PASS] Per-EDC task outcome, queue state, direct utilization, and computing energy exported.
- [INCONCLUSIVE] Queue-Aware performance superiority; paired CIs cross zero and outcomes are mixed.
- [LIMITATION] Virtual ingress demand does not preload a physical home-EDC queue; do not interpret this as a direct physical ingress-overload experiment.
