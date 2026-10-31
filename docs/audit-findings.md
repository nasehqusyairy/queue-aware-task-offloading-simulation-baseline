# Repository audit findings and changes

Audit performed on the uploaded ZIP snapshot. The Python unit tests can run in this environment; Maven is not installed here, so Java compilation and the full simulator acceptance run were not performed.

## Confirmed issues and changes made

1. **Analyzer overwrote manifest validation errors.** `scripts/analyze.py::_row_for_run()` expanded parser metrics after run metadata, so the parser's empty `validation_errors` replaced the manifest's real run-level failures. It now preserves run-level errors as `validation_errors` and records parser-specific checks separately as `metric_validation_errors`. A regression test covers the previous failure mode.
2. **Orchestrator audit timing.** `PaperAlignedSimulationManager` previously inferred the orchestrator type from the UE before the base simulation manager assigned the orchestrator to the task. It now records the task's orchestrator after the base event handler has assigned it.
3. **Orchestrator validation was permissive for missing observations.** `execute_run.py` previously only rejected a non-CLOUD type if the observed set was non-empty. It now compares observed types with the configured `deploy_orchestrator` value (CLOUD/EDGE/MIST) and flags missing or mismatched observations.
4. **Offloading eligibility discarded connectivity checks.** `PaperAlignedOrchestrator` previously accepted every node of a permitted layer, regardless of reachability. It now restricts EDC candidates to the UE's current uplink EDC or an EDC within `edge_datacenters_coverage`, and Mist candidates to the configured UE-to-UE range.
5. **Task orchestrator initialized explicitly.** `PaperAlignedTaskGenerator` now binds tasks to the configured Cloud orchestrator when `deploy_orchestrator=CLOUD`, avoiding the task API's lazy fallback to the source UE when the task orchestrator is unset.
6. **Acceptance test had an unsupported nearest-EDC assertion.** The test asserted `nearest_edc_mismatch_count`, a field not produced by the runner, and assumed Trade-Off always selects the nearest EDC. The assertion was removed; the test retains checks for permitted destinations, no `NONE` destinations, and orchestrator consistency.
7. **Documentation had stale status statements.** The historical build-blocker note and experiment protocol now distinguish historical notes from current configuration and clarify that the task-rate interpretation is not verified as paper-equivalent.

## Verification performed

- `python3 -m unittest discover -s tests -p 'test_*.py' -v`: 10 tests passed; the simulator acceptance test was skipped because `RUN_PAPER_SMOKE=1` was not set.
- `python3 -m py_compile scripts/*.py tests/*.py`: passed.
- `bash -n run.sh analyze.sh`: passed.
- Full Java build and 200-second simulation: **not run** because Maven is not installed in the audit environment.

## Remaining research-validity questions

- The custom generator treats each application `rate` as tasks per simulated second per UE. PureEdgeSim's default generator uses a per-minute loop; the intended semantics in the paper must be verified before calling the run paper-equivalent.
- Randomness is not controlled, so repeated runs are not guaranteed to be reproducible.
- EDC coordinates and several resource/network values are implementation choices until checked against the paper's full methods/configuration.
- A `completed` run means software validation passed; it does not establish that all experimental parameters or metrics reproduce the paper.
- The current implementation remains a Trade-Off/Round-Robin technical baseline. It does not implement Queue-Aware, GNN, or DQN.
