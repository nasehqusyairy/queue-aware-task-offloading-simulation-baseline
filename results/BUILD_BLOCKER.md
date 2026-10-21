# Project status after initial implementation attempt

PureEdgeSim source was cloned successfully, but the upstream Maven build `mvn -DskipTests package` exits 0 without producing compiled classes: its source tree is `PureEdgeSim/` rather than Maven's default `src/main/java`. Therefore the attempted runtime cannot load `Simulation`; no valid simulation or metric output has been produced yet. This is a build-layout mismatch, not an experiment result. `scripts/execute_run.py` and `run.sh` are under active correction; do not interpret prior run folders as valid data.
