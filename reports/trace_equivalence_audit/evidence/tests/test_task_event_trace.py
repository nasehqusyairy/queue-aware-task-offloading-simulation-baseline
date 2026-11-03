import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "analyze_task_event_trace.py"
SPEC = importlib.util.spec_from_file_location("task_trace", SCRIPT)
trace = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trace)


def row(event, timestamp, **overrides):
    value = {key: "" for key in trace.HEADER}
    value.update({
        "schema_version": "1", "task_id": "001", "event_name": event,
        "timestamp_seconds": str(timestamp), "application_id": "0", "task_type": "Hard Real-time",
        "source_id": "10", "source_layer": "EDGE_DEVICE", "destination_id": "20",
        "destination_layer": "EDGE_DATACENTER", "status": "SUCCESS", "failure_reason": "",
        "stage": "", "total_delay_seconds": "0.01", "network_delay_seconds": "0.005",
        "queue_wait_seconds": "0.001", "cpu_time_seconds": "0.004", "deadline_seconds": "0.02",
    })
    value.update(overrides)
    return value


def completed_rows():
    names = ["TASK_GENERATED", "ORCHESTRATION_REQUEST", "DESTINATION_DECISION", "TASK_DISPATCH",
             "DESTINATION_ARRIVAL", "TASK_SUBMISSION", "EXECUTION_START", "EXECUTION_END",
             "RESULT_RETURN", "TASK_COMPLETED"]
    return [row(name, i / 1000, status="SUCCESS" if name != "TASK_COMPLETED" else "SUCCESS")
            for i, name in enumerate(names)]


def test_valid_completed_timeline_and_slack():
    validation, timelines, summaries = trace.analyze_rows(completed_rows())
    assert validation["valid"]
    assert timelines[0]["terminal_event"] == "TASK_COMPLETED"
    assert abs(float(timelines[0]["deadline_slack_seconds"]) - 0.01) < 1e-12
    assert summaries[0]["completed"] == 1


def test_duplicate_terminal_is_rejected():
    rows = completed_rows() + [row("TASK_FAILED", 0.011, status="FAILED", failure_reason="FAILED_DUE_TO_LATENCY")]
    validation, _, _ = trace.analyze_rows(rows)
    assert not validation["valid"]
    assert any("duplicate terminal" in error for error in validation["errors"])


def test_missing_event_timestamp_is_rejected():
    rows = completed_rows()
    rows[2]["timestamp_seconds"] = ""
    validation, _, _ = trace.analyze_rows(rows)
    assert not validation["valid"]
    assert any("missing/invalid simulation timestamp" in error for error in validation["errors"])


def test_pending_is_not_reclassified_as_failure():
    rows = [row("TASK_GENERATED", 0.0), row("ORCHESTRATION_REQUEST", 0.0),
            row("TASK_PENDING_AT_HORIZON", 1.0, stage="UNRESOLVED_AT_CUTOFF")]
    validation, timelines, _ = trace.analyze_rows(rows)
    assert validation["valid"]
    assert timelines[0]["terminal_event"] == "TASK_PENDING_AT_HORIZON"
    assert timelines[0]["last_event_before_cutoff"] == "ORCHESTRATION_REQUEST"
    assert timelines[0]["failure_reason"] == ""
