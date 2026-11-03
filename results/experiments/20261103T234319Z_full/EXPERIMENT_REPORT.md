# Experiment workflow and preliminary results

- Workflow tested: yes; `./run_experiment.sh --quick` completed and `./view_results.sh` regenerated the outputs without rerunning simulations.
- Simulations completed: 18 valid of 18 planned quick cells; raw simulator CSVs, manifests, logs, and configs are retained under `runs/`.
- Quick protocol: seed 1, 8128, 4401; 200 simulated second(s); paired Trade-Off and Queue-Aware at low, medium, and high workload; destination `EDGE_DC_ONLY`.
- Result status: preliminary diagnostic only. One seed and a one-second horizon are not statistically conclusive; no confidence intervals, hypothesis tests, or generalized performance claims are supported.

## Measured paired success-rate differences

- low, seed 1: Queue-Aware − Trade-Off = +0.00% success rate.
- low, seed 4401: Queue-Aware − Trade-Off = +0.00% success rate.
- low, seed 8128: Queue-Aware − Trade-Off = +0.00% success rate.
- medium, seed 1: Queue-Aware − Trade-Off = +0.07% success rate.
- medium, seed 4401: Queue-Aware − Trade-Off = +0.36% success rate.
- medium, seed 8128: Queue-Aware − Trade-Off = +0.00% success rate.
- high, seed 1: Queue-Aware − Trade-Off = -0.09% success rate.
- high, seed 4401: Queue-Aware − Trade-Off = -0.21% success rate.
- high, seed 8128: Queue-Aware − Trade-Off = -0.12% success rate.

These values do not establish Queue-Aware improvement. See `aggregate.csv` for per-run counts, success rates, validation status, energy, delay, and destination-layer task counts. The generated charts include seed points and available-seed means.

## Metric and data limitations

- Completion rate is simulator completed tasks divided by generated tasks. Failed and pending remain separate in `aggregate.csv` and `charts/task_outcomes.png`.
- Delay is PureEdgeSim's average completed-task total delay: accumulated network + queue waiting + CPU. Event-clock elapsed can differ because per-hop latency accumulation and event scheduling do not have identical semantics. It is not wall-clock or pure network latency.
- Computing energy is the simulator's existing metric for computing nodes; network energy is separate.
- Workload distribution is measured by destination layer. Per-device queue length/utilization is not exposed by the available summary output, so no per-node imbalance claim is made.
- Full matrix (three seeds and 200 seconds per cell) was not executed as part of this workflow validation.
