# Queue-Aware Task Offloading — PureEdgeSim technical baselines

This repository runs the built-in PureEdgeSim Trade-Off and Round Robin orchestrators, plus an experimental Queue-Aware extension to Trade-Off. It is a **technical baseline**, not a reproduction of the cited paper; GNN and DQN are not implemented here.

## Requirements

- Git 2.x (including submodule support)
- Java JDK (17+ recommended; tested here with OpenJDK 25.0.4.1)
- Maven 3.8+ (tested here with Maven 3.9.12)
- Python 3 (tested here with Python 3.11)
- Network access on first submodule/dependency setup; Maven artifacts are cached for subsequent builds.

## Clone and run

Clone the repository and its configured source dependencies, then run:

```bash
git clone --recurse-submodules https://github.com/nasehqusyairy/queue-aware-task-offloading-simulation-baseline.git
cd queue-aware-task-offloading-simulation-baseline
./run.sh --method trade-off --devices 10
./run.sh --method round-robin --devices 10
./run.sh --profile paper-aligned-baseline --method queue-aware --devices 10 \
  --destination-config EDGE_DC_ONLY --seed 8128 --queue-weight 1.0
```

`run.sh` checks for Java, Maven, and Python; verifies the PureEdgeSim source-root configuration; builds PureEdgeSim from source; and stops if setup or simulation validation fails. It does not automatically initialize missing submodules. No simulation output is deleted: each attempt gets a unique `results/runs/<UTC-run-id>/` directory.

Use `./run.sh --help` for options. The default simulated duration is 1 minute; `--duration-minutes N` controls it. Upstream `ParametersParser` converts this property from minutes to seconds. Queue-Aware requires the `paper-aligned-baseline` profile and records candidate scores and queue estimates in `raw/queue_decisions.csv`. The default `--queue-weight` is 1.0; zero removes the estimated-wait term. Per-run manifest/config, simulator log, and raw simulator CSVs are retained.

For paired runs at three workload levels, use `scripts/run_queue_aware_matrix.py --dry-run` to inspect the nine-run plan, then run it without `--dry-run`. Levels use 10, 20, and 30 UEs, with the destination target fixed to `EDGE_DC_ONLY`. `--method all` runs Trade-Off, Round Robin, and Queue-Aware with the same seed and conditions. The queue wait is an estimate from currently active and queued work; it does not predict future arrivals or RAM-constrained scheduling. See [the design and source audit](docs/QUEUE_AWARE_DESIGN.md) and [the experiment protocol](docs/experiment-protocol.md) for definitions and limitations.

## Outputs and dashboard

Each run's raw data are in `results/runs/<run-id>/raw/`. Each run contains `manifest.json`, copied configuration, and raw CSV/log output. Lifecycle accounting distinguishes generated, sent, completed, terminally failed, and pending tasks; pending work at the hard cutoff is not counted as a terminal failure. Successful, failure, and pending rates use generated tasks as the denominator. Layer workload is dispatch count; layer completion counts include only tasks whose results returned to their source UE. The analyzer preserves failed runs and validation messages in aggregates; unavailable values remain N/A.

Recreate aggregate CSV/JSON and dashboard from successful runs:

```bash
./analyze.sh --latest
python3 -m http.server 8000 --directory results
```

Open <http://localhost:8000/dashboard.html>. The static dashboard fetches `processed/summary.json` from that same results directory; serving over HTTP avoids browser restrictions on `fetch()` from `file://`.

## One-command paired experiment and PNG results

Run the quick paired comparison across low, medium, and high offered workloads (Trade-Off and Queue-Aware share each workload, seed, duration, and destination configuration):

```bash
./run_experiment.sh --quick
```

Quick mode uses seed 1 and a one-second simulation horizon per cell. It validates the end-to-end workflow and provides preliminary observations; it is **not statistically conclusive**. The full matrix is selected by default with `./run_experiment.sh`: three seeds (1, 8128, 4401), three workload levels, both methods, and 200 simulated seconds per run. Review compute cost before starting the full matrix.

Every invocation creates `results/experiments/<UTC timestamp>_<mode>/`, retains each run's raw simulator CSVs/logs/configuration under `runs/`, and updates `aggregate.csv`, `aggregate_summary.csv`, PNG charts, and a static `index.html` after each run. Completion also writes `EXPERIMENT_REPORT.md` with workflow status, run counts, preliminary/statistical status, observed pair differences, and limitations. A failed or interrupted experiment preserves finished runs. Continue the most recent incomplete matrix with `./run_experiment.sh --resume` (or `./run_experiment.sh --quick --resume`); completed cells are skipped and never overwritten. An incomplete cell is retried into a new uniquely named run directory.

Open or regenerate the latest completed experiment without running simulations:

```bash
./view_results.sh
```

Pass a specific experiment directory to view an in-progress or older result set: `./view_results.sh results/experiments/<directory>`. Open its `index.html` locally or serve that directory with `python3 -m http.server --directory <directory>`. The workflow needs Java, Maven, Python 3, and Pillow for PNG rendering. Matrix defaults live in `configs/experiment/matrix.json`.

Charts show seed-level task completion rates and available-seed means, completed/failed/pending accounting, computing-node energy, the simulator's average completed-task total delay, and dispatch counts by destination layer. Delay uses the simulator's existing accumulated network + queue + CPU metric; event-clock and accumulated network timing have a known interpretation limitation described in each chart and the trace audit. Workload distribution is available only by destination layer, not per device or node queue; no per-node imbalance is inferred. `aggregate.csv` contains the run-level source data, including validation status. Results should be treated as preliminary until the protocol, configuration, sample size, and statistical analysis have been reviewed.

## PureEdgeSim provenance and build patch

PureEdgeSim is the official Git submodule at `https://github.com/CharafeddineMechalikh/PureEdgeSim.git`; the selected upstream revision is pinned in the gitlink (also printed in the run header and recorded in each manifest). The upstream source tree places Java files under `PureEdgeSim/`, but its Maven project did not declare this as source root. As observed, default Maven `package` can succeed while compiling zero classes. `patches/pureedgesim-maven-source-root.patch` adds that source root and is applied explicitly by `run.sh`; it does not silently rewrite Java source. The upstream checkout retains its GPL-3.0 `LICENSE`; the patch is available for review in this repository.

## Scope and limitations

This is a technical baseline, not a paper reproduction. The `paper-aligned-baseline` profile configures four Edge Data Centers, a 200-second horizon, and six destination labels, but these settings and the task-rate interpretation still need verification against the full paper methodology. The current task generator interprets application rates as tasks per simulated second per assigned UE; this is an implementation choice, not a verified paper fact. Queue-Aware is an experimental heuristic extension, not a paper-validated algorithm. It adds a weighted queue-wait estimate to the built-in Trade-Off score; do not report performance claims until repeated paired experiments and methodological validation are complete.

Before reporting results, run the 200-second acceptance test and inspect each run's `manifest.json` validation errors. Do not label baseline values as GNN/DQN or Queue-Aware results.

## License

PureEdgeSim is GPL-3.0; see the submodule's `LICENSE`. This repository references it as a Git submodule rather than copying or relicensing its source. The source-root modification is distributed as a transparent patch with its reason documented. Review license obligations before redistributing combined/modified binaries.
