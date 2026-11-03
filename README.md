# Queue-Aware Task Offloading — PureEdgeSim technical baselines

This repository runs the built-in PureEdgeSim Trade-Off and Round Robin orchestrators. It is a **technical baseline**, not a reproduction of the cited paper; GNN, DQN, and Queue-Aware are not implemented here.

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
```

`run.sh` checks for Java, Maven, and Python; verifies the PureEdgeSim source-root configuration; builds PureEdgeSim from source; and stops if setup or simulation validation fails. It does not automatically initialize missing submodules. No simulation output is deleted: each attempt gets a unique `results/runs/<UTC-run-id>/` directory.

Use `./run.sh --help` for options. The default simulated duration is 1 minute; `--duration-minutes N` controls it. Upstream `ParametersParser` converts this property from minutes to seconds. Per-run manifest/config, simulator log, and raw simulator CSVs are retained.

## Outputs and dashboard

Each run's raw data are in `results/runs/<run-id>/raw/`. Each run contains `manifest.json`, copied configuration, and raw CSV/log output. Lifecycle accounting distinguishes generated, sent, completed, terminally failed, and pending tasks; pending work at the hard cutoff is not counted as a terminal failure. Successful, failure, and pending rates use generated tasks as the denominator. Layer workload is dispatch count; layer completion counts include only tasks whose results returned to their source UE. The analyzer preserves failed runs and validation messages in aggregates; unavailable values remain N/A.

Recreate aggregate CSV/JSON and dashboard from successful runs:

```bash
./analyze.sh --latest
python3 -m http.server 8000 --directory results
```

Open <http://localhost:8000/dashboard.html>. The static dashboard fetches `processed/summary.json` from that same results directory; serving over HTTP avoids browser restrictions on `fetch()` from `file://`.

## PureEdgeSim provenance and build patch

PureEdgeSim is the official Git submodule at `https://github.com/CharafeddineMechalikh/PureEdgeSim.git`; the selected upstream revision is pinned in the gitlink (also printed in the run header and recorded in each manifest). The upstream source tree places Java files under `PureEdgeSim/`, but its Maven project did not declare this as source root. As observed, default Maven `package` can succeed while compiling zero classes. `patches/pureedgesim-maven-source-root.patch` adds that source root and is applied explicitly by `run.sh`; it does not silently rewrite Java source. The upstream checkout retains its GPL-3.0 `LICENSE`; the patch is available for review in this repository.

## Scope and limitations

This is a technical baseline, not a paper reproduction. The `paper-aligned-baseline` profile configures four Edge Data Centers, a 200-second horizon, and six destination labels, but these settings and the task-rate interpretation still need verification against the full paper methodology. The current task generator interprets application rates as tasks per simulated second per assigned UE; this is an implementation choice, not a verified paper fact. Random seeds are not controlled, so results may vary. GNN, DQN, and Queue-Aware are not implemented.

Before reporting results, run the 200-second acceptance test and inspect each run's `manifest.json` validation errors. Do not label baseline values as GNN/DQN or Queue-Aware results.

## License

PureEdgeSim is GPL-3.0; see the submodule's `LICENSE`. This repository references it as a Git submodule rather than copying or relicensing its source. The source-root modification is distributed as a transparent patch with its reason documented. Review license obligations before redistributing combined/modified binaries.
