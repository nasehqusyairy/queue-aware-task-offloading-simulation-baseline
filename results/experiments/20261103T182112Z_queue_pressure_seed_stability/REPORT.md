# Queue-Aware Seed Stability Experiment Report

## Objective and protocol

Test whether the queue-pressure-driven decision changes observed in the prior diagnostic persist over five paired seeds, and whether they yield consistent performance benefit. Configuration: `paper-aligned-baseline`, 30 UE, 4 EDC, `EDGE_DC_ONLY`, 5 simulated seconds, Trade-Off vs Queue-Aware, λ=1.0, seeds 1, 8128, 4401, 2026, 2027. Task-event trace and expanded queue decision audit were enabled for every run. No estimator or score formula was tuned.

Experiment ID: `20261103T182112Z_queue_pressure_seed_stability`. Repository HEAD `7cd0acabe3255552a79f33dd55dc31612833914b`; working tree dirty. Matrix is recorded in `matrix.json`; exact ten commands are in `commands_run.txt`.

## Execution and pairing validation

All **10/10** simulator runs completed with exit code 0 and zero manifest validation errors. All five seed pairs have identical device/application config hashes, simulator properties, destination, duration, UE count, simulator revision, and seed; only method and its method-specific queue audit/weight property differ. The pair audit is in `paired_by_seed.csv`; checks are summarized in `analysis_validation.json` and individual manifests.

## Queue signal and decision stability

Nonzero candidate queue estimates were observed for every seed. Queue-Aware had 93–111 candidate observations and 74–79 policy-selection decisions per seed. Candidate estimates ranged 0–3.210 to 0–4.505 seconds across seeds; selected-estimate means ranged 0.742–0.837 seconds. Nonzero candidate estimate counts were 42–58 per seed; nonzero selected estimate counts were 32–46.

| Seed | Candidate wait range (s) | Nonzero candidate observations | Selected mean wait (s) | Rank changed | Selected destination changed | Policy decisions |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0–4.180 | 58/111 | 0.7420 | 14 | 14 | 77 |
| 8128 | 0–3.755 | 55/101 | 0.7534 | 3 | 3 | 76 |
| 4401 | 0–4.505 | 42/97 | 0.7903 | 4 | 4 | 78 |
| 2026 | 0–3.905 | 55/93 | 0.8368 | 8 | 8 | 74 |
| 2027 | 0–3.210 | 53/95 | 0.7487 | 2 | 2 | 79 |

The observed selector changed rank/winner in **31 of 384 decisions (8.1%)**, with at least one such decision in each seed. Thus Queue-Aware changed some decisions consistently across these seeds, but most decisions retained the same winner. Lifecycle trace shows policy selections vs cached-placement reuse; these are re-placement decisions, not a fresh independent policy choice for every task.

## Paired performance results

All values below are mean ± sample SD across five runs. Difference is Queue-Aware minus Trade-Off, with paired t 95% CI (df=4). Completion is completed/generated; delay and waiting time are the simulator's average over completed tasks. Energy is computing-node Wh (network energy excluded).

| Metric | Trade-Off mean ± SD | Queue-Aware mean ± SD | Paired difference | 95% paired CI | Exact paired sign-flip p |
|---|---:|---:|---:|---:|---:|
| Completion rate | 5.076% ± 0.420 pp | 4.975% ± 0.361 pp | −0.101 pp | [−0.231, +0.029] pp | 0.250 |
| Completed tasks | 110.4 ± 9.13 | 108.2 ± 7.85 | −2.2 | [−5.03, +0.63] | 0.250 |
| Failed tasks | 1,224.4 ± 55.94 | 1,231.0 ± 47.25 | +6.6 | [−25.40, +38.60] | 0.688 |
| Pending tasks | 840.2 ± 47.15 | 835.8 ± 42.74 | −4.4 | [−36.39, +27.59] | 0.750 |
| Computing energy (Wh) | 3.0668 ± 0.0084 | 3.0766 ± 0.0066 | +0.00982 | [−0.00227, +0.02191] | 0.125 |
| Completed-task total delay (s) | 6.8514 ± 0.2051 | 6.8785 ± 0.1262 | +0.02715 | [−0.08953, +0.14383] | 0.688 |
| Actual completed-task waiting time (s) | 1.2811 ± 0.2069 | 1.3084 ± 0.1277 | +0.02727 | [−0.08938, +0.14391] | 0.688 |

Exact two-sided paired sign-flip tests enumerate all 2⁵ sign assignments for seed-pair differences. This assumes pairwise sign exchangeability under the null. All p-values exceed 0.05, and all paired t intervals include zero; with five seeds, these results have low power and are exploratory. No metric provides statistically supported evidence of benefit.

| Seed | Completion Δ (pp) | Completed Δ | Failed Δ | Pending Δ | Energy Δ (Wh) | Delay Δ (s) | Actual wait Δ (s) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | −0.230 | −5 | +34 | −29 | +0.0185 | +0.0405 | +0.0406 |
| 8128 | 0.000 | 0 | +10 | −10 | +0.0107 | +0.0104 | +0.0104 |
| 4401 | −0.092 | −2 | +23 | −21 | −0.0046 | +0.1804 | +0.1804 |
| 2026 | −0.184 | −4 | −33 | +37 | +0.0058 | −0.0387 | −0.0384 |
| 2027 | 0.000 | 0 | −1 | +1 | +0.0187 | −0.0568 | −0.0568 |

## Destination allocation

Per-task EDC assignments (all runs allocate 2,175 tasks; EDC1–4 IDs correspond to the configured four Edge Data Centers):

| Seed | Trade-Off EDC1/2/3/4 | Queue-Aware EDC1/2/3/4 |
|---:|---:|---:|
| 1 | 715 / 765 / 405 / 290 | 625 / 705 / 495 / 350 |
| 8128 | 545 / 575 / 445 / 610 | 545 / 605 / 445 / 580 |
| 4401 | 595 / 795 / 395 / 390 | 595 / 675 / 395 / 510 |
| 2026 | 410 / 610 / 590 / 565 | 410 / 530 / 620 / 615 |
| 2027 | 395 / 490 / 425 / 865 | 395 / 400 / 425 / 955 |

All four EDCs received tasks under both methods for all seeds. Queue-Aware shifted allocation, particularly away from EDC2 on four seeds, but allocation changes do not by themselves establish better utilization or performance.

## Interpretation, limitations, and next step

Queue-Aware produced nonzero queue signals and changed rank/winner in every seed, confirming that the mechanism is active under this workload. The observed performance direction is mixed and small: mean completion was lower by 0.101 percentage point, energy higher by 0.00982 Wh, total delay higher by 0.02715 s, and actual waiting higher by 0.02727 s; failed/pending counts varied in both directions. No paired test supports a performance improvement, and five seeds provide weak precision. Delay remains PureEdgeSim's accumulated network + queue + CPU metric; event-clock/per-hop interpretation limitations from the diagnostic remain applicable. Queue estimates are model estimates, and destination counts do not measure per-node utilization.

**Conclusion:** Queue-Aware consistently made some destination decisions change across these five seeds (31/384 overall), but the changes did not produce a consistent measured performance benefit. It was worse on average for completion, energy, delay, and actual waiting, while failure/pending differences were mixed; all uncertainty intervals include zero. Results are sufficient to justify a narrow exploratory λ-sensitivity experiment because the queue signal and decision mechanism are verified, but not to claim superiority or expand performance claims. Keep paired seeds/configuration and compare λ=0, 0.5, 1.0, and 2.0 as a predeclared sensitivity set.

## Reproduction and artifacts

- Matrix and unchanged protocol: `matrix.json`; execution driver: `execute_matrix.py`; exact commands: `commands_run.txt`.
- Run status/failures: `run_status.json`, `run_status.csv`; all ten raw run directories are under `runs/` with manifest, config, metrics, console log, raw simulator CSV, task event trace, destination audit, and Queue-Aware candidate audit.
- Run-level values: `run_level.csv`; paired deltas: `paired_by_seed.csv`; means, SDs, paired CIs and exact p-values: `paired_statistics.csv`; queue variation: `queue_signal_by_seed.csv`; candidate-decision detail: `queue_decision_effects.csv`.
- Visualizations: `charts/completion_by_seed.png`, `charts/queue_signal_decisions_by_seed.png`, `charts/edc_allocation_by_seed.png`.
- Re-run the same matrix into a fresh experiment directory with `python3 results/experiments/20261103T182112Z_queue_pressure_seed_stability/execute_matrix.py --output results/experiments/<new_experiment_id>`, then run `python3 results/experiments/<new_experiment_id>/analyze_matrix.py`. The driver refuses nonempty output directories and copies the matrix/analysis scripts into the new directory.
