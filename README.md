# Queue-Aware Task Offloading — PureEdgeSim technical baselines

This repository runs the built-in PureEdgeSim Trade-Off and Round Robin orchestrators. It is a **technical baseline**, not a reproduction of the cited paper; GNN, DQN, and Queue-Aware are not implemented here.

## Requirements

- Git 2.x (including submodule support)
- Java JDK (17+ recommended; tested here with OpenJDK 25.0.4.1)
- Maven 3.8+ (tested here with Maven 3.9.12)
- Python 3 (tested here with Python 3.11)
- Network access on first submodule/dependency setup; Maven artifacts are cached for subsequent builds.

## Clone and run

Recommended clean clone (the submodule is pinned by the parent repository's gitlink):

```bash
git clone --recurse-submodules https://github.com/nasehqusyairy/queue-aware-task-offloading-simulation-baseline.git
cd queue-aware-task-offloading-simulation-baseline
./run.sh --method trade-off --devices 10
./run.sh --method round-robin --devices 10
```

If you cloned without `--recurse-submodules`, `run.sh` initializes the pinned submodule automatically. The script checks Java, Maven, Python, and Git; applies the tracked upstream Maven source-layout patch if needed; builds PureEdgeSim from source; and fails with a diagnostic if setup or simulation fails. No simulation output is deleted: each attempt gets a unique `results/runs/<UTC-run-id>/` directory.

Use `./run.sh --help` for options. The default simulated duration is 1 minute; `--duration-minutes N` controls it. Upstream `ParametersParser` converts this property from minutes to seconds. Per-run manifest/config, simulator log, and raw simulator CSVs are retained.

## Outputs and dashboard

The successful run's raw data are in `results/runs/<run-id>/raw/`. Each run contains `manifest.json`, copied configuration, and raw CSV/log output. The analyzer only includes runs marked completed with a simulator CSV; unavailable values remain N/A.

Recreate aggregate CSV/JSON and dashboard from successful runs:

```bash
./analyze.sh --latest
python3 -m http.server 8000 --directory results
```

Open <http://localhost:8000/dashboard.html>. The static dashboard fetches `processed/summary.json` from that same results directory; serving over HTTP avoids browser restrictions on `fetch()` from `file://`.

## PureEdgeSim provenance and build patch

PureEdgeSim is the official Git submodule at `https://github.com/CharafeddineMechalikh/PureEdgeSim.git`; the selected upstream revision is pinned in the gitlink (also printed in the run header and recorded in each manifest). The upstream source tree places Java files under `PureEdgeSim/`, but its Maven project did not declare this as source root. As observed, default Maven `package` can succeed while compiling zero classes. `patches/pureedgesim-maven-source-root.patch` adds that source root and is applied explicitly by `run.sh`; it does not silently rewrite Java source. The upstream checkout retains its GPL-3.0 `LICENSE`; the patch is available for review in this repository.

## Scope and limitations

This is not paper reproduction. The paper's four Edge Data Centers, 200-second duration, six destination configurations, three repetitions, and GNN/DQN implementations are not yet reproduced or validated. The baseline currently runs the locally configured `EDGE_AND_CLOUD` scenario with built-in Trade-Off or Round Robin and default task/network/device profile except explicit CLI settings. No random seed is asserted where the selected API/configuration does not expose one. Results across runs may vary.

Next research step: parameterize paper-aligned topology and destination configurations and validate those against the paper before adding a Queue-Aware orchestrator. Do not label baseline values as GNN/DQN or Queue-Aware results.

## License

PureEdgeSim is GPL-3.0; see the submodule's `LICENSE`. This repository references it as a Git submodule rather than copying or relicensing its source. The source-root modification is distributed as a transparent patch with its reason documented. Review license obligations before redistributing combined/modified binaries.
