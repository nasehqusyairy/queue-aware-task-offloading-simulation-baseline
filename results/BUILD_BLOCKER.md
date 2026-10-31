# Historical build note — review status before using old runs

This file records an earlier build-layout blocker: PureEdgeSim sources are under `PureEdgeSim/`, not Maven's default `src/main/java`. The source-root fix is now present in `simulator/PureEdgeSim/pom.xml` and is checked by `run.sh`.

The archived run directories are historical artifacts. Their validity must be determined from each `manifest.json`, especially `status` and `validation_errors`; the existence of metrics alone does not make a run valid. This audit environment did not have Maven installed, so the Java build and 200-second end-to-end acceptance test were not rerun here.
