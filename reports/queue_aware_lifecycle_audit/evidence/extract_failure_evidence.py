#!/usr/bin/env python3
"""Copy compact, audit-specific lifecycle evidence from the prior matrix runs."""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SOURCE_INDEX = ROOT / "reports/queue_aware_audit_20261103T154150Z/evidence/run_index.json"
SOURCE_RUNS = ROOT / "reports/queue_aware_audit_20261103T154150Z/evidence/runs"


def main() -> None:
    all_runs = json.loads(SOURCE_INDEX.read_text())
    runs = [r for r in all_runs if r["audit_group"] == "matrix_seed1"]
    if len(runs) != 9:
        raise AssertionError(f"expected 9 matrix runs in previous audit evidence, got {len(runs)}")
    fields = [
        "devices", "workload_level", "method", "run_id", "generated", "sent", "completed",
        "terminally_failed", "pending", "deadline_failures", "resource_or_long_wait_counter",
        "device_dead_failures", "mobility_failures", "not_generated_device_death",
        "rejected_before_pipeline", "network_usage_seconds", "wan_usage_seconds",
        "average_wait_all_executed_seconds", "edge_cpu_utilization_percent",
        "analyzer_success_rate", "accounting_reconciles",
    ]
    with (OUT / "failure_reason_counts.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in sorted(runs, key=lambda r: (r["devices"], r["method"])):
            src = SOURCE_RUNS / item["run_id"]
            manifest = json.loads((src / "manifest.json").read_text())
            raw_file = next((src / "raw").glob("*/Sequential_simulation.csv"))
            raw = next(csv.DictReader(raw_file.open(newline="")))
            accounting = manifest["task_accounting"]
            metrics = json.loads((src / "metrics.json").read_text())
            generated, completed = accounting["generated_tasks"], accounting["completed_tasks"]
            failed, pending = accounting["terminally_failed_tasks"], accounting["pending_tasks"]
            writer.writerow({
                "devices": manifest["devices"],
                "workload_level": manifest.get("workload_level"),
                "method": manifest["method"],
                "run_id": item["run_id"],
                "generated": generated,
                "sent": accounting["sent_tasks"],
                "completed": completed,
                "terminally_failed": failed,
                "pending": pending,
                "deadline_failures": raw["Tasks failed (delay)"],
                "resource_or_long_wait_counter": raw["Task not executed (No resources available or long waiting time)"],
                "device_dead_failures": raw["Tasks failed (device dead)"],
                "mobility_failures": raw["Tasks failed (mobility)"],
                "not_generated_device_death": raw["Tasks not generated due to the death of devices"],
                "rejected_before_pipeline": raw["Tasks rejected before pipeline"],
                "network_usage_seconds": raw["Network usage (s)"],
                "wan_usage_seconds": raw["Wan usage (s)"],
                "average_wait_all_executed_seconds": raw["Average waiting time (s)"],
                "edge_cpu_utilization_percent": raw["Average CPU usage (Edge) (%)"],
                "analyzer_success_rate": metrics["task_success_rate"],
                "accounting_reconciles": generated == completed + failed + pending,
            })
            target = OUT / "runs" / item["run_id"]
            (target / "raw").mkdir(parents=True, exist_ok=True)
            for name in ("manifest.json", "metrics.json"):
                shutil.copy2(src / name, target / name)
            shutil.copy2(raw_file, target / "raw" / "Sequential_simulation.csv")
            if item["method"] == "queue-aware":
                shutil.copy2(src / "raw/queue_decisions.csv", target / "raw/queue_decisions.csv")
            for name in ("applications.xml", "simulation_parameters.properties", "edge_datacenters.xml"):
                shutil.copy2(src / "config" / name, target / name)

    (OUT / "evidence_scope.txt").write_text(
        "Selected evidence: the nine seed=1, 200-second, EDGE_DC_ONLY matrix runs from the previous audit. "
        "Each run contributes its manifest, analyzed metrics, raw Sequential_simulation.csv, and run-specific "
        "application/simulation/EDC config. Queue-Aware runs also include raw/queue_decisions.csv. "
        "No simulator was rerun for this audit.\n"
    )
    print(f"Copied evidence for {len(runs)} matrix runs")


if __name__ == "__main__":
    main()
