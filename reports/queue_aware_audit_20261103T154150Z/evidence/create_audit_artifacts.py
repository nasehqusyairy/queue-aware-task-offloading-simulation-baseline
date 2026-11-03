#!/usr/bin/env python3
"""Collect and summarize only the runs created for this queue-aware audit."""
from __future__ import annotations

import csv
import json
import re
import shutil
import statistics
from pathlib import Path

AUDIT = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = AUDIT / "evidence"
RUNS = ROOT / "results/runs"


def load_run(path: Path) -> dict:
    manifest = json.loads((path / "manifest.json").read_text())
    return manifest


def trace(path: Path) -> list[tuple[str, str, str, str]]:
    with (path / "raw/destinations.csv").open(newline="") as stream:
        return [(row["task_id"], row["source_id"], row["source_x"], row["source_y"])
                for row in csv.DictReader(stream) if row.get("record_type") == "DECISION"]


def destination_counts(path: Path) -> dict[str, int]:
    counts = {str(i): 0 for i in range(1, 5)}
    with (path / "raw/destinations.csv").open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row.get("record_type") == "DECISION":
                key = row.get("destination_id", "UNKNOWN")
                counts[key] = counts.get(key, 0) + 1
    return counts


def choices(path: Path) -> list[tuple[str, str]]:
    with (path / "raw/destinations.csv").open(newline="") as stream:
        return [(row["task_id"], row.get("destination_id", ""))
                for row in csv.DictReader(stream) if row.get("record_type") == "DECISION"]


def main() -> None:
    matrix_log = EVIDENCE / "matrix_console.log"
    matrix_ids = list(dict.fromkeys(re.findall(r"RUN_DIR=(.+)", matrix_log.read_text())))
    smoke_id = "20261103T154111536956981_paper-aligned-baseline_queue-aware_10ue_EDGE_DC_ONLY_seed8128"
    low_ids = [
        "20261103T154124336051485_paper-aligned-baseline_trade-off_10ue_EDGE_DC_ONLY_seed8128",
        "20261103T154131564068538_paper-aligned-baseline_round-robin_10ue_EDGE_DC_ONLY_seed8128",
        "20261103T154138603058420_paper-aligned-baseline_queue-aware_10ue_EDGE_DC_ONLY_seed8128",
    ]
    acceptance_ids = [
        "20261103T154925892848137_paper-aligned-baseline_trade-off_10ue_EDGE_DC_ONLY_seed8128",
        "20261103T154932741244321_paper-aligned-baseline_round-robin_10ue_EDGE_DC_ONLY_seed8128",
        "20261103T154939655428041_paper-aligned-baseline_queue-aware_10ue_EDGE_DC_ONLY_seed8128",
    ]
    paper_smoke_id = "20261103T155354535152828_paper-aligned-baseline_trade-off_10ue_EDGE_DC_ONLY_seed1"
    groups = [("smoke", [smoke_id]), ("low_pair_seed8128", low_ids),
              ("matrix_seed1", matrix_ids), ("opt_in_acceptance_seed8128", acceptance_ids),
              ("paper_smoke_acceptance_seed1", [paper_smoke_id])]
    selected: list[tuple[str, Path]] = []
    for group, ids in groups:
        for run_id in ids:
            path = Path(run_id) if Path(run_id).is_absolute() else ROOT / run_id
            if not path.is_dir():
                path = RUNS / run_id
            if not path.is_dir():
                raise FileNotFoundError(path)
            selected.append((group, path))
    if len(selected) != 17:
        raise AssertionError(f"expected 17 audit runs, got {len(selected)}")
    if len({path.name for _, path in selected}) != len(selected):
        raise AssertionError("duplicate run in audit index")

    evidence_runs = EVIDENCE / "runs"
    evidence_runs.mkdir(exist_ok=True)
    index = []
    for group, path in selected:
        manifest = load_run(path)
        if manifest.get("status") != "completed":
            raise AssertionError(f"run not completed: {path.name}")
        metrics = manifest.get("metrics", {})
        metric_errors = metrics.get("validation_errors", [])
        if manifest.get("validation_errors") or metric_errors:
            raise AssertionError(f"run validation errors: {path.name}: {manifest.get('validation_errors')} {metric_errors}")
        accounting = manifest.get("task_accounting", {})
        if accounting.get("generated_tasks") != (accounting.get("completed_tasks", 0)
                + accounting.get("terminally_failed_tasks", 0) + accounting.get("pending_tasks", 0)):
            raise AssertionError(f"task accounting does not reconcile: {path.name}")
        if sum(accounting.get("layer_successful_completions", {}).values()) != accounting.get("completed_tasks"):
            raise AssertionError(f"layer completions do not reconcile: {path.name}")
        target = evidence_runs / path.name
        target.mkdir(exist_ok=True)
        for name in ("manifest.json", "metrics.json", "config.json", "summary.txt"):
            source = path / name
            if source.exists():
                shutil.copy2(source, target / name)
        shutil.copytree(path / "config", target / "config", dirs_exist_ok=True)
        shutil.copytree(path / "raw", target / "raw", dirs_exist_ok=True)

        counts = destination_counts(path)
        values = list(counts.values())
        cv = statistics.pstdev(values) / statistics.mean(values) if statistics.mean(values) else None
        index.append({
            "audit_group": group,
            "run_id": path.name,
            "method": manifest.get("method"),
            "devices": manifest.get("devices"),
            "duration_seconds": manifest.get("duration_seconds"),
            "seed": manifest.get("random_seed"),
            "queue_weight": manifest.get("queue_penalty_weight"),
            "status": manifest.get("status"),
            "manifest_validation_errors": manifest.get("validation_errors", []),
            "metric_validation_errors": metric_errors,
            "metrics": metrics,
            "queue_decision_count": (metrics.get("queue_aware_metrics") or {}).get("selected_queue_estimate_count"),
            "offloading_decision_count": manifest.get("offloading_decisions"),
            "dispatched_task_count": manifest.get("destination_decision_count"),
            "destination_decision_counts_by_edc_id": counts,
            "edc_destination_count_cv": cv,
        })

    matrix = [row for row in index if row["audit_group"] == "matrix_seed1"]
    if len(matrix) != 9:
        raise AssertionError(f"expected 9 matrix runs, got {len(matrix)}")
    trace_checks = []
    for group in ("low_pair_seed8128", "matrix_seed1", "opt_in_acceptance_seed8128"):
        rows = [row for row in index if row["audit_group"] == group]
        devices_values = sorted({row["devices"] for row in rows})
        for devices in devices_values:
            paired = {row["method"]: row for row in rows if row["devices"] == devices}
            if set(paired) != {"trade-off", "round-robin", "queue-aware"}:
                raise AssertionError(f"incomplete method pair in {group} at {devices} devices")
            run_paths = {method: RUNS / row["run_id"] for method, row in paired.items()}
            traces = {method: trace(path) for method, path in run_paths.items()}
            if len({tuple(value) for value in traces.values()}) != 1:
                raise AssertionError(f"source task/UE/position trace mismatch in {group} at {devices} devices")
            assignments = {method: choices(path) for method, path in run_paths.items()}
            trace_checks.append({
                "group": group,
                "devices": devices,
                "source_task_ue_position_traces_identical": True,
                "tradeoff_and_round_robin_destination_sequences_identical": assignments["trade-off"] == assignments["round-robin"],
                "queue_aware_destination_sequence_matches_tradeoff": assignments["queue-aware"] == assignments["trade-off"],
            })
    (EVIDENCE / "paired_trace_check.json").write_text(json.dumps(trace_checks, indent=2) + "\n")
    repeated_queue_runs = [row for row in index if row["method"] == "queue-aware"
                           and row["devices"] == 10 and row["seed"] == 8128]
    repeated_queue_paths = [RUNS / row["run_id"] for row in repeated_queue_runs]
    metric_keys = ("generated_tasks", "completed_tasks", "terminally_failed_tasks", "pending_tasks",
                   "average_completed_task_total_delay_seconds", "energy_consumption")
    repeated_results_identical = all(
        all(row["metrics"].get(key) == repeated_queue_runs[0]["metrics"].get(key) for key in metric_keys)
        for row in repeated_queue_runs[1:])
    repeat_check = {
        "same_seed_queue_aware_runs": [path.name for path in repeated_queue_paths],
        "count": len(repeated_queue_paths),
        "source_task_ue_position_traces_identical": len({tuple(trace(path)) for path in repeated_queue_paths}) == 1,
        "destination_assignment_sequences_identical": len({tuple(choices(path)) for path in repeated_queue_paths}) == 1,
        "selected_metric_values_identical": repeated_results_identical,
        "compared_metric_fields": list(metric_keys),
    }
    if repeated_queue_paths and not all((repeat_check["source_task_ue_position_traces_identical"],
                                         repeat_check["destination_assignment_sequences_identical"],
                                         repeat_check["selected_metric_values_identical"])):
        raise AssertionError("same-seed repeated Queue-Aware run was not identical")
    (EVIDENCE / "same_seed_repeatability_check.json").write_text(json.dumps(repeat_check, indent=2) + "\n")

    (EVIDENCE / "run_index.json").write_text(json.dumps(index, indent=2) + "\n")
    fields = ["audit_group", "run_id", "method", "devices", "duration_seconds", "seed", "queue_weight",
              "status", "generated_tasks", "completed_tasks", "terminally_failed_tasks", "pending_tasks",
              "task_success_rate", "average_completed_task_total_delay_seconds",
              "average_completed_task_waiting_time_seconds", "average_cpu_execution_time_seconds",
              "energy_consumption", "selected_mean_queue_wait_estimate_seconds",
              "selected_median_queue_wait_estimate_seconds", "selected_mean_waiting_queue_length",
              "queue_decision_count", "offloading_decision_count", "dispatched_task_count",
              "queue_decision_fraction_of_dispatched_tasks",
              "edc_destination_count_cv", "edc_1_decisions", "edc_2_decisions", "edc_3_decisions",
              "edc_4_decisions", "layer_dispatch_counts_json", "manifest_validation_errors",
              "metric_validation_errors"]
    with (EVIDENCE / "run_summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in index:
            metrics = row["metrics"]
            queue = metrics.get("queue_aware_metrics") or {}
            writer.writerow({
                **{key: row.get(key) for key in fields},
                "generated_tasks": metrics.get("generated_tasks"),
                "completed_tasks": metrics.get("completed_tasks"),
                "terminally_failed_tasks": metrics.get("terminally_failed_tasks"),
                "pending_tasks": metrics.get("pending_tasks"),
                "task_success_rate": metrics.get("task_success_rate"),
                "average_completed_task_total_delay_seconds": metrics.get("average_completed_task_total_delay_seconds"),
                "average_completed_task_waiting_time_seconds": metrics.get("average_completed_task_waiting_time_seconds"),
                "average_cpu_execution_time_seconds": metrics.get("average_cpu_execution_time_seconds"),
                "energy_consumption": metrics.get("energy_consumption"),
                "selected_mean_queue_wait_estimate_seconds": queue.get("selected_mean_queue_wait_estimate_seconds"),
                "selected_median_queue_wait_estimate_seconds": queue.get("selected_median_queue_wait_estimate_seconds"),
                "selected_mean_waiting_queue_length": queue.get("selected_mean_waiting_queue_length"),
                "queue_decision_count": queue.get("selected_queue_estimate_count"),
                "offloading_decision_count": row.get("offloading_decision_count"),
                "dispatched_task_count": row.get("dispatched_task_count"),
                "queue_decision_fraction_of_dispatched_tasks": (
                    queue.get("selected_queue_estimate_count") / row["dispatched_task_count"]
                    if queue.get("selected_queue_estimate_count") is not None and row.get("dispatched_task_count") else None),
                **{f"edc_{node_id}_decisions": row["destination_decision_counts_by_edc_id"].get(str(node_id), 0)
                   for node_id in range(1, 5)},
                "layer_dispatch_counts_json": json.dumps(metrics.get("workload_distribution"), sort_keys=True),
                "manifest_validation_errors": json.dumps(row["manifest_validation_errors"]),
                "metric_validation_errors": json.dumps(row["metric_validation_errors"]),
            })
    print(f"Indexed and copied {len(index)} completed audit runs ({len(matrix)} matrix runs).")


if __name__ == "__main__":
    main()
