#!/usr/bin/env python3
"""Validate and summarize PureEdgeSim task event trace CSV files."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

SCHEMA_VERSION = "1"
TERMINAL_EVENTS = {"TASK_COMPLETED", "TASK_FAILED"}
KNOWN_EVENTS = {
    "TASK_GENERATED", "ORCHESTRATION_REQUEST", "DESTINATION_DECISION", "TASK_DISPATCH",
    "DESTINATION_ARRIVAL", "QUEUE_ENTER", "QUEUE_EXIT", "EXECUTION_START", "EXECUTION_END",
    "RESULT_RETURN", "TASK_COMPLETED", "TASK_FAILED", "TASK_PENDING_AT_HORIZON",
    "DESTINATION_EXECUTION_READY", "TASK_SUBMISSION",
}
TIMESTAMP_FIELDS = {
    "TASK_GENERATED": "t_generate",
    "ORCHESTRATION_REQUEST": "t_orchestration_request",
    "DESTINATION_DECISION": "t_decision",
    "TASK_DISPATCH": "t_dispatch",
    "DESTINATION_ARRIVAL": "t_destination_arrival",
    "TASK_SUBMISSION": "t_destination_submit",
    "QUEUE_ENTER": "t_queue_enter",
    "QUEUE_EXIT": "t_queue_exit",
    "EXECUTION_START": "t_execution_start",
    "EXECUTION_END": "t_execution_end",
    "RESULT_RETURN": "t_result_arrival",
    "TASK_COMPLETED": "t_terminal",
    "TASK_FAILED": "t_terminal",
    "TASK_PENDING_AT_HORIZON": "t_pending_cutoff",
}
HEADER = [
    "schema_version", "task_id", "event_name", "timestamp_seconds", "scheduled_release_time_seconds",
    "application_id", "task_type",
    "source_id", "source_layer", "destination_id", "destination_layer", "status", "failure_reason",
    "stage", "total_delay_seconds", "network_delay_seconds", "queue_wait_seconds", "cpu_time_seconds",
    "deadline_seconds",
]


def read_trace(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != HEADER:
            raise ValueError(f"unexpected trace header: {reader.fieldnames}")
        return list(reader)


def analyze_rows(rows: list[dict[str, str]]) -> tuple[dict, list[dict], list[dict]]:
    errors: list[str] = []
    by_task: dict[str, list[dict[str, str]]] = defaultdict(list)
    counts = Counter()
    for index, row in enumerate(rows, start=2):
        task_id = row.get("task_id", "")
        event = row.get("event_name", "")
        if not task_id:
            errors.append(f"row {index}: missing task_id")
            continue
        if row.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"row {index}: unsupported schema_version {row.get('schema_version')!r}")
        if event not in KNOWN_EVENTS:
            errors.append(f"row {index}: unknown event {event!r}")
        try:
            timestamp = float(row.get("timestamp_seconds", ""))
            if timestamp < 0:
                errors.append(f"row {index}: negative timestamp")
        except (TypeError, ValueError):
            errors.append(f"row {index}: missing/invalid simulation timestamp")
        by_task[task_id].append(row)
        counts[event] += 1

    timelines: list[dict] = []
    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for task_id, events in by_task.items():
        names = [row["event_name"] for row in events]
        terminal = [name for name in names if name in TERMINAL_EVENTS]
        pending = names.count("TASK_PENDING_AT_HORIZON")
        if names.count("TASK_GENERATED") != 1:
            errors.append(f"task {task_id}: TASK_GENERATED count is {names.count('TASK_GENERATED')}, expected 1")
        if len(terminal) > 1:
            errors.append(f"task {task_id}: duplicate terminal events {terminal}")
        if terminal and pending:
            errors.append(f"task {task_id}: both terminal and pending-at-horizon")
        if not terminal and not pending:
            errors.append(f"task {task_id}: no terminal or pending-at-horizon event")
        for event_name in KNOWN_EVENTS:
            event_count = names.count(event_name)
            if event_count > 1:
                errors.append(f"task {task_id}: duplicate {event_name} ({event_count})")
        if names.count("QUEUE_EXIT") and not names.count("QUEUE_ENTER"):
            errors.append(f"task {task_id}: QUEUE_EXIT without QUEUE_ENTER")
        if names.count("EXECUTION_END") and not names.count("EXECUTION_START"):
            errors.append(f"task {task_id}: EXECUTION_END without EXECUTION_START")
        if names.count("DESTINATION_ARRIVAL") and not names.count("TASK_DISPATCH"):
            errors.append(f"task {task_id}: DESTINATION_ARRIVAL without TASK_DISPATCH")
        if names.count("TASK_COMPLETED") and not (names.count("RESULT_RETURN") and names.count("EXECUTION_END")):
            errors.append(f"task {task_id}: completion lacks result return or execution end")
        if names.count("RESULT_RETURN") and not names.count("EXECUTION_END"):
            errors.append(f"task {task_id}: result return without execution end")
        order_requirements = [
            ("TASK_GENERATED", "ORCHESTRATION_REQUEST"), ("ORCHESTRATION_REQUEST", "DESTINATION_DECISION"),
            ("DESTINATION_DECISION", "TASK_DISPATCH"), ("TASK_DISPATCH", "DESTINATION_ARRIVAL"),
            ("DESTINATION_ARRIVAL", "TASK_SUBMISSION"), ("QUEUE_ENTER", "QUEUE_EXIT"),
            ("QUEUE_EXIT", "EXECUTION_START"), ("EXECUTION_START", "EXECUTION_END"),
            ("EXECUTION_END", "RESULT_RETURN"), ("RESULT_RETURN", "TASK_COMPLETED"),
        ]
        for before, after in order_requirements:
            if before in names and after in names and names.index(before) > names.index(after):
                errors.append(f"task {task_id}: {after} logged before {before}")
        times = []
        for row in events:
            try:
                times.append(float(row["timestamp_seconds"]))
            except (TypeError, ValueError):
                continue
        if times != sorted(times):
            errors.append(f"task {task_id}: event timestamps move backwards")
        network_snapshots = []
        for row in events:
            try:
                network_snapshots.append(float(row["network_delay_seconds"]))
            except (TypeError, ValueError):
                continue
        if network_snapshots != sorted(network_snapshots):
            errors.append(f"task {task_id}: accumulated network delay moves backwards")

        timeline = {"task_id": task_id, "terminal_event": terminal[0] if terminal else ("TASK_PENDING_AT_HORIZON" if pending else "INCOMPLETE_TRACE")}
        pending_index = next((i for i, row in enumerate(events) if row["event_name"] == "TASK_PENDING_AT_HORIZON"), None)
        timeline["last_event_before_cutoff"] = (events[pending_index - 1]["event_name"]
                                                if pending_index is not None and pending_index > 0 else "")
        for event, field in TIMESTAMP_FIELDS.items():
            matching = [row for row in events if row["event_name"] == event]
            timeline[field] = matching[-1]["timestamp_seconds"] if matching else ""
        def delta(start: str, end: str) -> str:
            try:
                return str(float(timeline[end]) - float(timeline[start]))
            except (KeyError, TypeError, ValueError):
                return ""
        def network_delta(start_event: str, end_event: str) -> str:
            start_rows = [r for r in events if r["event_name"] == start_event]
            end_rows = [r for r in events if r["event_name"] == end_event]
            if not start_rows or not end_rows:
                return ""
            try:
                return str(float(end_rows[-1]["network_delay_seconds"]) - float(start_rows[-1]["network_delay_seconds"]))
            except (KeyError, TypeError, ValueError):
                return ""
        timeline["orchestration_request_elapsed_seconds"] = delta("t_orchestration_request", "t_decision")
        timeline["orchestration_request_network_delay_seconds"] = network_delta("ORCHESTRATION_REQUEST", "DESTINATION_DECISION")
        timeline["dispatch_to_destination_arrival_seconds"] = delta("t_dispatch", "t_destination_arrival")
        timeline["dispatch_network_delay_seconds"] = network_delta("TASK_DISPATCH", "DESTINATION_ARRIVAL")
        timeline["post_arrival_pre_submit_seconds"] = delta("t_destination_arrival", "t_destination_submit")
        timeline["post_arrival_pre_submit_network_delay_seconds"] = network_delta("DESTINATION_ARRIVAL", "TASK_SUBMISSION")
        timeline["observed_queue_wait_seconds"] = delta("t_queue_enter", "t_queue_exit")
        timeline["observed_cpu_execution_seconds"] = delta("t_execution_start", "t_execution_end")
        timeline["result_return_elapsed_seconds"] = delta("t_execution_end", "t_result_arrival")
        timeline["result_return_network_delay_seconds"] = network_delta("EXECUTION_END", "RESULT_RETURN")
        timeline["generation_to_terminal_elapsed_seconds"] = delta("t_generate", "t_terminal")
        first = events[0] if events else {}
        for field in ("application_id", "task_type", "source_id", "source_layer", "destination_id", "destination_layer",
                      "status", "failure_reason", "deadline_seconds", "scheduled_release_time_seconds"):
            val = first.get(field, "")
            if field == "destination_id" and not val:
                val = next((r[field] for r in reversed(events) if r.get(field)), "")
            if field == "destination_layer" and not val:
                val = next((r[field] for r in reversed(events) if r.get(field)), "")
            timeline[field] = val
        terminal_row = next((r for r in reversed(events) if r["event_name"] in TERMINAL_EVENTS), None)
        if terminal_row:
            timeline["status"] = terminal_row["status"]
            timeline["failure_reason"] = terminal_row["failure_reason"]
            for field in ("total_delay_seconds", "network_delay_seconds", "queue_wait_seconds", "cpu_time_seconds", "deadline_seconds"):
                timeline[field] = terminal_row[field]
            try:
                timeline["deadline_slack_seconds"] = str(float(terminal_row["deadline_seconds"]) - float(terminal_row["total_delay_seconds"]))
            except (ValueError, TypeError):
                timeline["deadline_slack_seconds"] = ""
            try:
                expected_delay = (float(terminal_row["network_delay_seconds"])
                                  + float(terminal_row["queue_wait_seconds"])
                                  + float(terminal_row["cpu_time_seconds"]))
                actual_delay = float(terminal_row["total_delay_seconds"])
                if abs(expected_delay - actual_delay) > 1e-12:
                    errors.append(f"task {task_id}: total delay does not equal network + queue + CPU")
            except (TypeError, ValueError):
                errors.append(f"task {task_id}: terminal delay components are missing")
        else:
            timeline["total_delay_seconds"] = timeline["network_delay_seconds"] = ""
            timeline["queue_wait_seconds"] = timeline["cpu_time_seconds"] = ""
            timeline["deadline_slack_seconds"] = ""
        timelines.append(timeline)
        key = (timeline["application_id"], timeline["task_type"], timeline["destination_layer"])
        grouped[key].append(timeline)

    summaries = []
    for (app_id, task_type, layer), tasks in sorted(grouped.items()):
        completed = sum(t["terminal_event"] == "TASK_COMPLETED" for t in tasks)
        failed = sum(t["terminal_event"] == "TASK_FAILED" for t in tasks)
        pending_count = sum(t["terminal_event"] == "TASK_PENDING_AT_HORIZON" for t in tasks)
        delays = [float(t["total_delay_seconds"]) for t in tasks if t.get("total_delay_seconds") not in (None, "")]
        summaries.append({
            "application_id": app_id, "task_type": task_type, "destination_layer": layer,
            "task_count": len(tasks), "completed": completed, "failed": failed, "pending": pending_count,
            "mean_terminal_total_delay_seconds": (sum(delays) / len(delays) if delays else ""),
            "mean_orchestration_request_elapsed_seconds": mean_field(tasks, "orchestration_request_elapsed_seconds"),
            "mean_orchestration_request_network_delay_seconds": mean_field(tasks, "orchestration_request_network_delay_seconds"),
            "mean_dispatch_to_arrival_seconds": mean_field(tasks, "dispatch_to_destination_arrival_seconds"),
            "mean_dispatch_network_delay_seconds": mean_field(tasks, "dispatch_network_delay_seconds"),
            "mean_observed_queue_wait_seconds": mean_field(tasks, "observed_queue_wait_seconds"),
            "mean_observed_cpu_execution_seconds": mean_field(tasks, "observed_cpu_execution_seconds"),
            "mean_result_return_elapsed_seconds": mean_field(tasks, "result_return_elapsed_seconds"),
            "mean_result_return_network_delay_seconds": mean_field(tasks, "result_return_network_delay_seconds"),
        })
    validation = {
        "schema_version": SCHEMA_VERSION,
        "record_count": len(rows), "task_count": len(by_task), "event_counts": dict(sorted(counts.items())),
        "terminal_task_count": sum(counts[name] for name in TERMINAL_EVENTS),
        "pending_event_count": counts["TASK_PENDING_AT_HORIZON"], "errors": errors,
        "valid": not errors,
    }
    validation["destination_assignment_modes"] = dict(sorted(Counter(
        row["stage"] for row in rows if row["event_name"] == "DESTINATION_DECISION").items()))
    validation["pending_last_event_counts"] = dict(sorted(Counter(
        row["last_event_before_cutoff"] for row in timelines
        if row["terminal_event"] == "TASK_PENDING_AT_HORIZON").items()))
    return validation, timelines, summaries


def mean_field(rows: list[dict], field: str) -> float | str:
    values = []
    for row in rows:
        try:
            values.append(float(row[field]))
        except (KeyError, TypeError, ValueError):
            pass
    return sum(values) / len(values) if values else ""


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-manifest", type=Path)
    parser.add_argument("--summary-csv", type=Path)
    parser.add_argument("--destination-csv", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    validation, timelines, summaries = analyze_rows(read_trace(args.trace))
    if args.destination_csv:
        with args.destination_csv.open(newline="", encoding="utf-8") as stream:
            decisions = [row for row in csv.DictReader(stream) if row.get("record_type") == "DECISION"]
        trace_decisions = [row for row in read_trace(args.trace) if row["event_name"] == "DESTINATION_DECISION"]
        comparable = [(row["task_id"], row["destination_type"], row["destination_id"]) for row in decisions]
        traced = [(row["task_id"], row["destination_layer"], row["destination_id"]) for row in trace_decisions]
        matches = comparable == traced
        validation["destination_decision_sequence_matches"] = matches
        validation["destination_decision_sequence_count"] = len(traced)
        if not matches:
            validation["errors"].append("trace destination decision sequence does not match destination audit")
            validation["valid"] = False
    if args.summary_csv:
        with args.summary_csv.open(newline="", encoding="utf-8") as stream:
            summary_rows = list(csv.DictReader(stream))
        if len(summary_rows) != 1:
            validation["errors"].append(f"expected one simulator summary row, found {len(summary_rows)}")
            validation["valid"] = False
        else:
            summary = summary_rows[0]
            reason_counts = Counter(row["failure_reason"] for row in read_trace(args.trace)
                                    if row["event_name"] == "TASK_FAILED")
            reason_map = {
                "FAILED_DUE_TO_LATENCY": "Tasks failed (delay)",
                "FAILED_BECAUSE_DEVICE_DEAD": "Tasks failed (device dead)",
                "FAILED_DUE_TO_DEVICE_MOBILITY": "Tasks failed (mobility)",
            }
            reason_check = {}
            for reason, column in reason_map.items():
                trace_count = reason_counts[reason]
                summary_count = int(float(summary[column]))
                reason_check[reason] = {"trace": trace_count, "summary": summary_count,
                                        "matches": trace_count == summary_count}
            resource_trace = sum(reason_counts[r] for r in
                                 ("NO_OFFLOADING_DESTINATIONS", "INSUFFICIENT_RESOURCES", "INSUFFICIENT_POWER"))
            resource_summary = int(float(summary["Task not executed (No resources available or long waiting time)"]))
            reason_check["resource_category"] = {"trace": resource_trace, "summary": resource_summary,
                                                   "matches": resource_trace == resource_summary}
            validation["failure_reason_summary_check"] = reason_check
            if not all(item["matches"] for item in reason_check.values()):
                validation["errors"].append("failure reason counts do not match simulator summary")
                validation["valid"] = False
    if args.expected_manifest:
        manifest = json.loads(args.expected_manifest.read_text(encoding="utf-8"))
        accounting = manifest.get("task_accounting", {})
        trace_counts = Counter(row["terminal_event"] for row in timelines)
        expected = {
            "generated_tasks": len(timelines),
            "completed_tasks": trace_counts["TASK_COMPLETED"],
            "terminally_failed_tasks": trace_counts["TASK_FAILED"],
            "pending_tasks": trace_counts["TASK_PENDING_AT_HORIZON"],
        }
        actual = {key: accounting.get(key) for key in expected}
        validation["summary_accounting_expected"] = expected
        validation["summary_accounting_actual"] = actual
        validation["summary_accounting_matches"] = expected == actual
        if expected != actual:
            validation["errors"].append(f"trace accounting {expected} != manifest accounting {actual}")
            validation["valid"] = False
    write_csv(args.output_dir / "task_timeline.csv", timelines,
              ["task_id", "application_id", "task_type", "source_id", "source_layer", "destination_id", "destination_layer",
               "terminal_event", "last_event_before_cutoff", "status", "failure_reason", "t_generate", "t_orchestration_request", "t_decision", "t_dispatch",
               "scheduled_release_time_seconds", "t_destination_arrival", "t_destination_submit", "t_queue_enter", "t_queue_exit", "t_execution_start", "t_execution_end", "t_result_arrival",
               "t_terminal", "t_pending_cutoff", "orchestration_request_elapsed_seconds", "orchestration_request_network_delay_seconds",
               "dispatch_to_destination_arrival_seconds", "dispatch_network_delay_seconds", "post_arrival_pre_submit_seconds",
               "post_arrival_pre_submit_network_delay_seconds", "observed_queue_wait_seconds", "observed_cpu_execution_seconds",
               "result_return_elapsed_seconds", "result_return_network_delay_seconds", "generation_to_terminal_elapsed_seconds", "total_delay_seconds",
               "network_delay_seconds", "queue_wait_seconds", "cpu_time_seconds", "deadline_seconds", "deadline_slack_seconds"])
    write_csv(args.output_dir / "task_type_destination_summary.csv", summaries,
              ["application_id", "task_type", "destination_layer", "task_count", "completed", "failed", "pending",
               "mean_terminal_total_delay_seconds", "mean_orchestration_request_elapsed_seconds", "mean_dispatch_to_arrival_seconds",
               "mean_orchestration_request_network_delay_seconds", "mean_dispatch_network_delay_seconds",
               "mean_observed_queue_wait_seconds", "mean_observed_cpu_execution_seconds", "mean_result_return_elapsed_seconds",
               "mean_result_return_network_delay_seconds"])
    (args.output_dir / "trace_validation.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(validation, indent=2))
    return 0 if validation["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
