#!/usr/bin/env python3
"""Compare one trace-off and one trace-on experiment run conservatively."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

TOLERANCE = 1e-12
IDENTITY_FIELDS = ("profile", "method", "algorithm", "devices", "duration_seconds", "destination_config",
                   "architecture", "simulator_revision", "random_seed", "simulator_properties",
                   "configuration_sha256", "task_accounting")


def compare_value(a, b, path: str, differences: list[str]) -> None:
    if isinstance(a, bool) or isinstance(b, bool):
        if a != b: differences.append(f"{path}: {a!r} != {b!r}")
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if not math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=TOLERANCE):
            differences.append(f"{path}: {a!r} != {b!r} (abs tolerance {TOLERANCE})")
    elif isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b): differences.append(f"{path}: key sets differ")
        for key in sorted(set(a) & set(b)):
            compare_value(a[key], b[key], f"{path}.{key}", differences)
    elif a != b:
        differences.append(f"{path}: {a!r} != {b!r}")


def compare_csv(left: Path, right: Path, label: str) -> list[str]:
    errors = []
    with left.open(newline="", encoding="utf-8") as a, right.open(newline="", encoding="utf-8") as b:
        ra, rb = csv.DictReader(a), csv.DictReader(b)
        if ra.fieldnames != rb.fieldnames:
            return [f"{label}: CSV headers differ"]
        rows_a, rows_b = list(ra), list(rb)
    if len(rows_a) != len(rows_b): return [f"{label}: row count {len(rows_a)} != {len(rows_b)}"]
    for index, (row_a, row_b) in enumerate(zip(rows_a, rows_b), start=2):
        for field in ra.fieldnames or []:
            va, vb = row_a[field], row_b[field]
            if va == vb: continue
            try:
                fa, fb = float(va), float(vb)
                if math.isclose(fa, fb, rel_tol=0.0, abs_tol=TOLERANCE): continue
            except (TypeError, ValueError):
                pass
            errors.append(f"{label} row {index} field {field}: {va!r} != {vb!r}")
            if len(errors) >= 25:
                errors.append(f"{label}: further differences truncated")
                return errors
    return errors


def find_sequential_csv(run: Path) -> Path:
    matches = list((run / "raw").rglob("Sequential_simulation.csv"))
    if len(matches) != 1:
        raise ValueError(f"expected exactly one Sequential_simulation.csv in {run}, found {len(matches)}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace_off", type=Path)
    parser.add_argument("trace_on", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    off, on = args.trace_off.resolve(), args.trace_on.resolve()
    errors: list[str] = []
    manifests = [json.loads((run / "manifest.json").read_text(encoding="utf-8")) for run in (off, on)]
    metrics = [json.loads((run / "metrics.json").read_text(encoding="utf-8")) for run in (off, on)]
    for field in IDENTITY_FIELDS:
        compare_value(manifests[0].get(field), manifests[1].get(field), f"manifest.{field}", errors)
    if manifests[0].get("task_event_trace_enabled", False): errors.append("trace-off manifest says tracing was enabled")
    if not manifests[1].get("task_event_trace_enabled", False): errors.append("trace-on manifest says tracing was disabled")
    trace_off_file = off / "raw" / "task_event_trace.csv"
    trace_on_file = on / "raw" / "task_event_trace.csv"
    if trace_off_file.exists(): errors.append("trace-off created task_event_trace.csv")
    if not trace_on_file.is_file(): errors.append("trace-on did not create task_event_trace.csv")

    ignored_metrics = {"run_id", "source"}
    for key in sorted((set(metrics[0]) | set(metrics[1])) - ignored_metrics):
        if key not in metrics[0] or key not in metrics[1]: errors.append(f"metrics.{key}: missing on one side")
        else: compare_value(metrics[0][key], metrics[1][key], f"metrics.{key}", errors)
    seq_a, seq_b = find_sequential_csv(off), find_sequential_csv(on)
    errors.extend(compare_csv(seq_a, seq_b, "Sequential_simulation.csv"))
    dest_a, dest_b = off / "raw" / "destinations.csv", on / "raw" / "destinations.csv"
    if not dest_a.is_file() or not dest_b.is_file(): errors.append("destination audit missing on one side")
    else: errors.extend(compare_csv(dest_a, dest_b, "destinations.csv"))
    queue_a, queue_b = off / "raw" / "queue_decisions.csv", on / "raw" / "queue_decisions.csv"
    if queue_a.exists() != queue_b.exists(): errors.append("queue decision audit presence differs")
    elif queue_a.exists(): errors.extend(compare_csv(queue_a, queue_b, "queue_decisions.csv"))

    result = {
        "status": "FAIL" if errors else "INCONCLUSIVE",
        "measurable_outputs_equivalent": not errors,
        "strict_per_task_terminal_equivalence": "INCONCLUSIVE",
        "comparison": "trace-off vs trace-on",
        "trace_off_run": str(off), "trace_on_run": str(on),
        "absolute_float_tolerance": TOLERANCE,
        "exactly_checked": ["run configuration identity", "all metrics.json fields except run_id/source",
                            "all Sequential_simulation.csv cells", "all destination sequence cells",
                            "all queue candidate/score/selection cells when present",
                            "trace file enable/disable behavior"],
        "not_comparable": ["per-task terminal status/failure identity: trace-off intentionally emits no per-task terminal log"],
        "interpretation": ("all available non-trace summaries and decision sequences match, but strict per-task terminal identity cannot be established from trace-off outputs"
                           if not errors else "one or more compared outputs differ"),
        "errors": errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
