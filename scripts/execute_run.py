#!/usr/bin/env python3
"""Build and execute one isolated PureEdgeSim experiment run."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "simulator" / "PureEdgeSim"
sys.path.insert(0, str(ROOT / "scripts"))
from analyze import parse
from paper_experiment import allocate_profile_counts, coverage_summary, expected_task_count, target_allowed_types


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, data: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    temp.replace(path)


def property_map(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def profile_data(config: Path, devices: int, duration: int):
    device_profiles = ET.parse(config / "edge_devices.xml").getroot().findall("device")
    app_profiles = ET.parse(config / "applications.xml").getroot().findall("application")
    device_percentages = [int(d.findtext("percentage", "0")) for d in device_profiles]
    app_percentages = [int(a.findtext("usage_percentage", "0")) for a in app_profiles]
    profile_counts = allocate_profile_counts(devices, device_percentages)
    source_count = sum(n for n, profile in zip(profile_counts, device_profiles)
                       if profile.findtext("generateTasks", "false").strip().lower() == "true")
    app_counts = allocate_profile_counts(source_count, app_percentages)
    rates = [int(a.findtext("rate", "0")) for a in app_profiles]
    expected = expected_task_count(source_count, app_percentages, rates, duration)
    return device_profiles, app_profiles, profile_counts, app_counts, source_count, expected


def main() -> int:
    if len(sys.argv) not in (9, 11):
        print("usage: execute_run.py RUN_DIR PROFILE METHOD DEVICES DURATION_SECONDS TARGET ARCHITECTURE ALGORITHM [SEED QUEUE_WEIGHT]", file=sys.stderr)
        return 2
    if len(sys.argv) == 11:
        run, profile, method, devices_s, duration_s, target, architecture, algorithm, seed_s, queue_weight_s = sys.argv[1:]
        seed = int(seed_s)
        queue_weight = float(queue_weight_s)
    else:
        run, profile, method, devices_s, duration_s, target, architecture, algorithm = sys.argv[1:]
        seed = None
        queue_weight = 1.0
    run = Path(run).resolve()
    devices, duration = int(devices_s), int(duration_s)
    if not math.isfinite(queue_weight) or queue_weight < 0:
        print("queue weight must be finite and non-negative", file=sys.stderr)
        return 2
    if method == "queue-aware" and profile != "paper-aligned-baseline":
        print("queue-aware requires paper-aligned-baseline", file=sys.stderr)
        return 2
    config = run / "config"
    raw = run / "raw"
    work = run / "work"
    raw.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    provenance = json.loads((ROOT / "provenance/pureedgesim.json").read_text())
    root_commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True,
                                 capture_output=True, check=False).stdout.strip() or None
    java_version = subprocess.run(["java", "-version"], text=True, capture_output=True, check=False).stderr.splitlines()
    props = property_map(config / "simulation_parameters.properties")
    start = utc_now()
    manifest = {
        "schema_version": 2,
        "run_id": run.name,
        "profile": profile,
        "method": method,
        "algorithm": algorithm,
        "devices": devices,
        "requested_devices": devices,
        "duration_seconds": duration,
        "duration_property_minutes": float(props["simulation_time"]),
        "destination_config": target,
        "architecture": architecture,
        "simulator": "PureEdgeSim",
        "simulator_version": provenance["upstream_version"],
        "simulator_revision": provenance["upstream_commit"],
        "simulator_source_mode": provenance["distribution_mode"],
        "repository_commit": root_commit,
        "java_version": java_version[0] if java_version else None,
        "random_seed": seed if profile == "paper-aligned-baseline" else "not controlled for technical-baseline profile",
        "started_utc": start,
        "finished_utc": None,
        "process_exit_code": None,
        "status": "running",
        "simulator_properties": props,
        "configuration_sha256": {
            p.name: sha256(p) for p in sorted(config.iterdir()) if p.is_file()
        },
        "validity": ("deterministic per-task lifecycle validation only; not DQN or performance evidence"
                     if method == "per-task-test" else "paper-aligned baseline; not Queue-Aware, GNN, or DQN"),
        "energy_scope": "computing nodes (Cloud + Edge Data Centers + user devices); network energy is separate",
    }
    write_json(run / "config.json", manifest)
    write_json(run / "manifest.json", manifest)

    try:
        device_profiles, app_profiles, device_counts, app_counts, source_count, expected_tasks = profile_data(
            config, devices, duration
        )
        if method in {"per-task-test", "dqn"} or os.environ.get("PAPER_PER_TASK_VALIDATION_WORKLOAD") == "1":
            expected_tasks = 64
            manifest["workload_override"] = {
                "kind": "deterministic_per_task_validation",
                "task_count": 64,
                "source_ue_count": 1,
                "arrival_gap_seconds": 0.03,
                "application_index": 2,
                "changes_baseline_configuration": False,
            }
        home_matrix_encoded = os.environ.get("PAPER_HOME_WORKLOAD_MATRIX", "").strip()
        home_condition = os.environ.get("PAPER_HOME_WORKLOAD_CONDITION", "").strip()
        home_matrix = None
        if home_matrix_encoded:
            rows = [[int(value.strip()) for value in row.split(",")] for row in home_matrix_encoded.split(";")]
            if len(rows) != 4 or any(len(row) != len(app_counts) for row in rows):
                raise ValueError("PAPER_HOME_WORKLOAD_MATRIX must be 4 rows by application profile count")
            if any(value < 0 for row in rows for value in row):
                raise ValueError("home workload matrix values must be non-negative")
            column_sums = [sum(row[col] for row in rows) for col in range(len(app_counts))]
            if column_sums != app_counts:
                raise ValueError(f"home workload matrix columns {column_sums} != application users {app_counts}")
            if not home_condition:
                raise ValueError("PAPER_HOME_WORKLOAD_CONDITION is required with a home workload matrix")
            home_matrix = rows
            manifest["home_workload_condition"] = home_condition
            manifest["home_workload_matrix_users_by_edc_app"] = rows
            manifest["home_workload_semantics"] = "virtual ingress demand attribution only; does not constrain execution destination"
        elif home_condition:
            raise ValueError("PAPER_HOME_WORKLOAD_MATRIX is required with a workload condition")
        if profile == "paper-aligned-baseline":
            if any(p.findtext("generateTasks", "false").strip().lower() != "true" for p in device_profiles):
                raise ValueError("paper-aligned profile requires every UE type to be permitted to generate tasks")
            app_percentages = [int(a.findtext("usage_percentage", "0")) for a in app_profiles]
            rates = [int(a.findtext("rate", "0")) for a in app_profiles]
            manifest.update({
                "device_profile_counts": {f"type_{i+1}": count for i, count in enumerate(device_counts)},
                "application_user_counts": {a.get("name", f"app_{i+1}"): n for i, (a, n) in enumerate(zip(app_profiles, app_counts))},
                "expected_generated_tasks": expected_tasks,
                "task_rate_semantics": "tasks per simulated second per UE assigned to the application profile; usage_percentage allocates UE groups by largest remainder (implementation interpretation)",
                "application_percentages": app_percentages,
                "application_rates_per_second": rates,
                "duration_cutoff_policy": "hard horizon at t=duration_seconds; unresolved generated tasks remain pending and are excluded from terminal failures",
                "local_execution_policy": "destination equal to source UE is local execution, separately marked in destination audit",
            })
            task_lengths = [int(a.findtext("task_length", "0")) for a in app_profiles]
            offered_work_mi_per_second = sum(users * rate * length for users, rate, length
                                             in zip(app_counts, rates, task_lengths))
            cloud_nodes = ET.parse(config / "cloud.xml").getroot().findall(".//datacenter")
            edc_nodes = ET.parse(config / "edge_datacenters.xml").getroot().findall(".//datacenter")
            cloud_capacity = sum(int(n.findtext("cores", "0")) * float(n.findtext("mips", "0")) for n in cloud_nodes)
            edc_capacity = sum(int(n.findtext("cores", "0")) * float(n.findtext("mips", "0")) for n in edc_nodes)
            mist_capacity = sum(count * int(profile_node.findtext("cores", "0"))
                                * float(profile_node.findtext("mips", "0"))
                                for count, profile_node in zip(device_counts, device_profiles))
            allowed = target_allowed_types(target)
            candidate_capacity = ((cloud_capacity if "CLOUD" in allowed else 0)
                                  + (edc_capacity if "EDGE_DATACENTER" in allowed else 0)
                                  + (mist_capacity if "EDGE_DEVICE" in allowed else 0))
            manifest.update({
                "workload_level": ({10: "low", 20: "medium", 30: "high"}.get(devices)
                                   if target == "EDGE_DC_ONLY" else None),
                "offered_task_rate_per_second": sum(u * rate for u, rate in zip(app_counts, rates)),
                "offered_work_mi_per_second": offered_work_mi_per_second,
                "candidate_compute_capacity_mips": candidate_capacity,
                "theoretical_offered_load_ratio": (offered_work_mi_per_second / candidate_capacity
                                                    if candidate_capacity > 0 else None),
            })
        write_json(run / "config.json", manifest)
        write_json(run / "manifest.json", manifest)

        classpath_file = run / "classpath.txt"
        cp = subprocess.run(["mvn", "-q", f"-Dmdep.outputFile={classpath_file}", "dependency:build-classpath"],
                            cwd=SIM, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if cp.returncode:
            raise RuntimeError("Maven dependency classpath failed: " + cp.stdout[-5000:])
        dependency_cp = classpath_file.read_text().strip()
        class_dir = run / "classes"
        class_dir.mkdir(exist_ok=True)
        classpath = f"{SIM / 'target/classes'}:{dependency_cp}"

        expected_settings = work / "PureEdgeSim" / "settings"
        expected_settings.mkdir(parents=True, exist_ok=True)
        for item in config.iterdir():
            if item.is_file():
                shutil.copy2(item, expected_settings / item.name)
        output_dir = expected_settings.parent / "output"
        output_dir.mkdir(exist_ok=True)

        if profile == "paper-aligned-baseline":
            java_sources = sorted((ROOT / "experiment/src").rglob("*.java"))
            if not java_sources:
                raise RuntimeError("experiment Java launcher sources are missing")
            compile_result = subprocess.run(["javac", "-cp", classpath, "-d", str(class_dir),
                                             *map(str, java_sources)], text=True,
                                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if compile_result.returncode:
                raise RuntimeError("experiment launcher compilation failed: " + compile_result.stdout[-8000:])
            classpath = f"{class_dir}:{classpath}"
            destination_log = raw / "destinations.csv"
            common_properties = [f"-Dpaper.seed={seed}"] if seed is not None else []
            if os.environ.get("PAPER_PER_TASK_VALIDATION_WORKLOAD") == "1":
                common_properties.append("-Dpaper.per-task-validation-workload=true")
            trace_events = (os.environ.get("PAPER_TASK_EVENT_TRACE", "").strip().lower() in {"1", "true", "yes"}
                            or method in {"per-task-test", "dqn"})
            manifest["task_event_trace_enabled"] = trace_events
            command = [
                "java", *common_properties,
                f"-Dpaper.profile-counts={','.join(map(str, device_counts))}",
                f"-Dpaper.app-counts={','.join(map(str, app_counts))}",
                f"-Dpaper.destination-log={destination_log}",
            ]
            if home_matrix is not None:
                matrix_arg = ";".join(",".join(map(str, row)) for row in home_matrix)
                home_audit = raw / "home_workload.csv"
                command.extend([f"-Dpaper.home-workload-matrix={matrix_arg}",
                                f"-Dpaper.home-workload-audit={home_audit}"])
            if trace_events:
                command.append(f"-Dpaper.task-event-trace={raw / 'task_event_trace.csv'}")
                command.append(f"-Dpaper.node-state-log={raw / 'edc_node_state.csv'}")
            if method == "queue-aware-trade-off" or method == "queue-aware":
                queue_audit = raw / "queue_decisions.csv"
                command.extend([f"-Dpaper.queue-audit-log={queue_audit}",
                                f"-Dpaper.queue-penalty-weight={queue_weight}"])
                command.extend(["-cp", classpath, "com.mechalikh.pureedgesim.experiment.QueueAwareMain"])
                manifest["queue_penalty_weight"] = queue_weight
                manifest["algorithm"] = "QUEUE_AWARE_TRADE_OFF"
            elif method == "per-task-test":
                command.extend([f"-Dpaper.per-task-policy=deterministic-task-modulo",
                                f"-Dpaper.per-task-decision-log={raw / 'per_task_decisions.csv'}",
                                f"-Dpaper.per-task-ledger-log={raw / 'per_task_ledger.csv'}",
                                "-cp", classpath, "com.mechalikh.pureedgesim.experiment.PerTaskTestMain"])
                manifest["algorithm"] = "DETERMINISTIC_TEST_POLICY_NOT_DQN"
            elif method == "dqn":
                dqn_mode = os.environ.get("DQN_MODE", "train")
                dqn_config = os.environ.get("DQN_CONFIG")
                dqn_checkpoint = os.environ.get("DQN_CHECKPOINT")
                if not dqn_config or not dqn_checkpoint:
                    raise ValueError("DQN_CONFIG and DQN_CHECKPOINT environment variables are required for method=dqn")
                transition_log = raw / "dqn_transitions.csv"
                command.extend(["-Dpaper.per-task-policy=dqn", f"-Dpaper.dqn-mode={dqn_mode}",
                                f"-Dpaper.dqn-config={Path(dqn_config).resolve()}",
                                f"-Dpaper.dqn-checkpoint={Path(dqn_checkpoint).resolve()}",
                                f"-Dpaper.dqn-transition-log={transition_log}",
                                f"-Dpaper.per-task-decision-log={raw / 'per_task_decisions.csv'}",
                                f"-Dpaper.per-task-ledger-log={raw / 'per_task_ledger.csv'}",
                                "-cp", classpath, "com.mechalikh.pureedgesim.experiment.DqnMain"])
                manifest["algorithm"] = "DQN_PER_TASK_OFFLOADING"
                manifest["dqn_mode"] = dqn_mode
                manifest["dqn_config"] = str(Path(dqn_config).resolve())
                manifest["dqn_checkpoint"] = str(Path(dqn_checkpoint).resolve())
                manifest["training_seed"] = seed if dqn_mode == "train" else None
                manifest["validity"] = "DQN pilot software validation; not evidence of learned performance"
            else:
                command.extend(["-cp", classpath, "com.mechalikh.pureedgesim.experiment.PaperAlignedMain"])
                if os.environ.get("PAPER_PER_TASK_VALIDATION_WORKLOAD") == "1":
                    command.append("-Dpaper.per-task-validation-workload=true")
        else:
            command = ["java", "-cp", classpath, "com.mechalikh.pureedgesim.MainApplication"]
        result = subprocess.run(command, cwd=work, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (raw / "simulator-console.log").write_text(result.stdout)
        output_files = [p for p in output_dir.rglob("*") if p.is_file()]
        for source in output_files:
            destination = raw / source.relative_to(output_dir)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise RuntimeError(f"refusing to overwrite run artifact {destination}")
            shutil.copy2(source, destination)

        errors = []
        if result.returncode != 0:
            errors.append(f"simulator exit code {result.returncode}")
        if home_matrix is not None and not (raw / "home_workload.csv").is_file():
            errors.append("home workload audit CSV is missing")
        if "SimulationThread - Simulation Finished!" not in result.stdout:
            errors.append("missing simulator completion marker")
        if "Exception in thread" in result.stdout:
            errors.append("uncaught Java exception in simulator output")
        manifest["process_exit_code"] = result.returncode
        manifest["command"] = command
        manifest["working_directory"] = str(work)
        manifest["simulator_csvs"] = [str(p.relative_to(run)) for p in sorted(raw.rglob("*.csv"))
                                      if p.name != "destinations.csv"]

        if method in {"per-task-test", "dqn"}:
            decision_path = raw / "per_task_decisions.csv"
            ledger_path = raw / "per_task_ledger.csv"
            if not decision_path.is_file() or not ledger_path.is_file():
                errors.append("per-task decision or lifecycle ledger CSV is missing")
            else:
                with decision_path.open(newline="") as stream:
                    decisions = list(csv.DictReader(stream))
                with (raw / "destinations.csv").open(newline="") as stream:
                    destination_rows = [row for row in csv.DictReader(stream) if row.get("record_type") == "DECISION"]
                decision_ids = [row.get("task_id") for row in decisions]
                destination_by_id = {row.get("task_id"): row.get("destination_id", "") for row in destination_rows}
                duplicate_ids = len(decision_ids) != len(set(decision_ids))
                if duplicate_ids:
                    errors.append("per-task decision audit contains duplicate task IDs")
                if len(decisions) != len(destination_rows):
                    errors.append("per-task and destination audit decision row counts differ")
                mismatches = [row.get("task_id") for row in decisions
                              if row.get("actual_applied_destination_id", "") != destination_by_id.get(row.get("task_id"), "")]
                if mismatches:
                    errors.append(f"selected/applied destination audit mismatch for task IDs {mismatches[:10]}")
                unaccounted_calls = [row.get("task_id") for row in decisions
                                     if row.get("decision_status") not in {"DECIDED", "NO_ELIGIBLE_DESTINATION", "POLICY_NOT_CALLED"}]
                if unaccounted_calls:
                    errors.append("per-task decision has unknown decision status")
                for row in decisions:
                    if row.get("decision_status") != "DECIDED":
                        continue
                    try:
                        ids = json.loads(row["candidate_edc_ids"])
                        mask = json.loads(row["action_mask"])
                        action = int(row["selected_action"])
                        chosen = int(row["selected_edc_id"])
                    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
                        errors.append(f"malformed action mapping for task {row.get('task_id')}")
                        continue
                    if len(ids) != len(mask) or action < 0 or action >= len(mask) or not mask[action] or ids[action] != chosen:
                        errors.append(f"masked or inconsistent action mapping for task {row.get('task_id')}")
                    if row.get("cache_bypassed", "").lower() != "true":
                        errors.append(f"per-task decision did not bypass placement cache for task {row.get('task_id')}")
                with ledger_path.open(newline="") as stream:
                    ledger_rows = list(csv.DictReader(stream))
                generated_ids = {row["task_id"] for row in ledger_rows if row["event_name"] == "TASK_GENERATED"}
                terminal_by_kind = {
                    kind: [row["task_id"] for row in ledger_rows if row["event_name"] == event_name]
                    for kind, event_name in (("completed", "TASK_COMPLETED"), ("failed", "TASK_FAILED"), ("pending", "TASK_PENDING_AT_HORIZON"))
                }
                if len(generated_ids) != expected_tasks:
                    errors.append(f"task ledger generated ID count {len(generated_ids)} != {expected_tasks}")
                if any(len(values) != len(set(values)) for values in terminal_by_kind.values()):
                    errors.append("task ledger contains duplicate terminal outcomes")
                terminal_sets = [set(values) for values in terminal_by_kind.values()]
                if any(terminal_sets[i] & terminal_sets[j] for i in range(3) for j in range(i + 1, 3)):
                    errors.append("task ledger terminal outcome categories overlap")
                terminal_ids = set().union(*terminal_sets)
                if not terminal_ids <= generated_ids:
                    errors.append("task ledger terminal outcome references an unknown task")
                terminal_task_ids = terminal_sets[0] | terminal_sets[1]
                if not terminal_task_ids <= set(decision_ids):
                    errors.append("terminal task outcome is missing its task decision")
                ledger_accounting = {"generated": len(generated_ids), **{key: len(values) for key, values in terminal_by_kind.items()},
                                     "terminal_task_ids": len(terminal_ids), "accounting_valid": len(generated_ids) == len(terminal_ids)}
                manifest["per_task_lifecycle_accounting"] = ledger_accounting
                if not ledger_accounting["accounting_valid"]:
                    errors.append("task ledger lifecycle does not account for every generated task exactly once")
                manifest["per_task_decision_count"] = len(decisions)
                manifest["per_task_unique_task_ids"] = len(set(decision_ids))
                manifest["per_task_destination_mismatches"] = len(mismatches)
                manifest["per_task_cached_placement_bypasses"] = sum(row.get("cache_bypassed", "").lower() == "true" for row in decisions)
                manifest["per_task_decision_status_counts"] = {
                    status: sum(row.get("decision_status") == status for row in decisions)
                    for status in ("DECIDED", "NO_ELIGIBLE_DESTINATION", "POLICY_NOT_CALLED")
                }

        if profile == "paper-aligned-baseline":
            device_match = re.search(r"PAPER_DEVICE_COUNTS requested=(\d+) actual=(\d+) profiles=([^ ]+) active_task_sources=(\d+) edge_data_centers=(\d+) cloud=(\d+)", result.stdout)
            task_match = re.search(r"PAPER_TASK_GENERATION simulated_seconds=(\d+) active_devices=(\d+) app_user_counts=([^ ]+) generated_tasks=(\d+)", result.stdout)
            horizon_match = re.search(r"PAPER_HORIZON time_seconds=([0-9.]+) generated=(\d+) sent=(\d+) accounted=(\d+) pending_at_cutoff=(\d+) completed=(\d+) terminally_failed=(\d+) accounting_valid=(true|false) cloud_pending=(\d+) edge_pending=(\d+) mist_pending=(\d+) rejected_before_pipeline=(\d+)", result.stdout)
            if not device_match:
                errors.append("missing actual UE/EDC generation marker")
            else:
                actual, actual_edcs, actual_cloud = int(device_match.group(2)), int(device_match.group(5)), int(device_match.group(6))
                manifest["actual_edge_device_count"] = actual
                manifest["edge_datacenter_count"] = actual_edcs
                manifest["cloud_count"] = actual_cloud
                if actual != devices: errors.append(f"actual UE count {actual} != requested {devices}")
                if actual_edcs != 4: errors.append(f"actual EDC count {actual_edcs} != 4")
                if actual_cloud != 1: errors.append(f"actual cloud count {actual_cloud} != 1")
            if not task_match:
                errors.append("missing generated task-rate marker")
            else:
                generated = int(task_match.group(4))
                manifest["task_generator_seconds"] = int(task_match.group(1))
                manifest["task_generator_device_count"] = int(task_match.group(2))
                manifest["task_generator_app_user_counts"] = task_match.group(3)
                manifest["task_generator_generated_tasks"] = generated
                if generated != expected_tasks: errors.append(f"task generator created {generated}; expected {expected_tasks}")
            if not horizon_match:
                errors.append("missing simulation horizon marker")
            else:
                end = float(horizon_match.group(1))
                pending = int(horizon_match.group(5))
                manifest["simulated_end_seconds"] = end
                manifest["pending_tasks_at_horizon"] = pending
                accounting = {
                    "generated_tasks": int(horizon_match.group(2)),
                    "sent_tasks": int(horizon_match.group(3)),
                    "completed_tasks": int(horizon_match.group(6)),
                    "terminally_failed_tasks": int(horizon_match.group(7)),
                    "pending_tasks": pending,
                    "rejected_before_pipeline_tasks": int(horizon_match.group(12)),
                    "pending_by_layer": {
                        "Cloud": int(horizon_match.group(9)),
                        "Edge": int(horizon_match.group(10)),
                        "Mist": int(horizon_match.group(11)),
                    },
                }
                manifest["task_accounting"] = accounting
                if horizon_match.group(8) != "true":
                    errors.append("runtime task accounting invariant failed")
                if accounting["generated_tasks"] != (accounting["completed_tasks"] + accounting["terminally_failed_tasks"] + accounting["pending_tasks"]):
                    errors.append("generated tasks do not reconcile with completed, terminally failed, and pending")
                if accounting["rejected_before_pipeline_tasks"] > accounting["terminally_failed_tasks"]:
                    errors.append("rejected-before-pipeline count exceeds terminal failures")
                manifest["task_accounting"]["layer_successful_completions"] = None
                if abs(end - duration) > 1e-6: errors.append(f"simulation ended at {end}s, expected {duration}s")
                if int(horizon_match.group(2)) != expected_tasks: errors.append("horizon generated count does not match expected task count")
            destination_path = raw / "destinations.csv"
            decision_counts = {}
            current_up_counts = {}
            source_ids = set()
            source_ids_with_edc_uplink = set()
            none_with_edc_uplink = 0
            source_points = []
            local_count = 0
            orchestrator_types = set()
            decision_count = 0
            if not destination_path.is_file():
                errors.append("destination audit CSV is missing")
            else:
                allowed = target_allowed_types(target)
                with destination_path.open(newline="") as stream:
                    for row in csv.DictReader(stream):
                        if row.get("record_type") != "DECISION":
                            continue
                        decision_count += 1
                        kind = row.get("destination_type", "NONE")
                        up_type = row.get("current_up_type", "NONE")
                        source_id = row.get("source_id", "")
                        if row.get("source_x") not in (None, "") and row.get("source_y") not in (None, ""):
                            source_points.append((float(row["source_x"]), float(row["source_y"])))
                        if source_id: source_ids.add(source_id)
                        current_up_counts[up_type] = current_up_counts.get(up_type, 0) + 1
                        if source_id and up_type == "EDGE_DATACENTER": source_ids_with_edc_uplink.add(source_id)
                        if kind == "NONE" and up_type == "EDGE_DATACENTER": none_with_edc_uplink += 1
                        if kind != "NONE" and kind not in allowed:
                            errors.append(f"forbidden destination {kind} for {target}")
                        decision_counts[kind] = decision_counts.get(kind, 0) + 1
                        if row.get("local_execution", "").lower() == "true": local_count += 1
                        if row.get("orchestrator_type") not in (None, "", "UNKNOWN"):
                            orchestrator_types.add(row["orchestrator_type"])
                coverage_centers = []
                for dc in ET.parse(config / "edge_datacenters.xml").getroot().findall(".//datacenter"):
                    loc = dc.find("location")
                    if loc is not None:
                        x, y = loc.findtext("x_pos"), loc.findtext("y_pos")
                        if x is None or y is None:
                            raise ValueError(f"EDC {dc.get('name')} lacks explicit x_pos/y_pos")
                        coverage_centers.append((float(x), float(y)))
                coverage = coverage_summary(
                    source_points, coverage_centers, float(props["edge_datacenters_coverage"]),
                    float(props["length"]), float(props["width"]),
                )
                manifest["coverage_geometry"] = {
                    "shape": "circular reach tested against nearest EDC center; not a square network radius",
                    "radius": float(props["edge_datacenters_coverage"]),
                    "centers": coverage_centers,
                    "sampled_decision_positions": coverage["points_checked"],
                    "max_nearest_distance": coverage["max_nearest_distance"],
                }
                manifest["coverage_violation_count"] = coverage["coverage_violation_count"]
                manifest["area_violation_count"] = coverage["area_violation_count"]
                if coverage["points_checked"] != decision_count:
                    errors.append("destination audit lacks a position sample for one or more decisions")
                if coverage["coverage_violation_count"]:
                    errors.append(f"{coverage['coverage_violation_count']} task positions fall outside every EDC radius")
                if coverage["area_violation_count"]:
                    errors.append(f"{coverage['area_violation_count']} task positions fall outside the simulation area")
                if decision_count == 0: errors.append("no destination decisions recorded")
                if props.get("enable_orchestrators", "false").lower() == "true":
                    configured_orchestrator = props.get("deploy_orchestrator", "").upper()
                    expected_orchestrator_type = {
                        "CLOUD": "CLOUD",
                        "EDGE": "EDGE_DATACENTER",
                        "MIST": "EDGE_DEVICE",
                    }.get(configured_orchestrator)
                    if expected_orchestrator_type and orchestrator_types != {expected_orchestrator_type}:
                        errors.append(
                            "orchestrator type mismatch: "
                            f"configured {configured_orchestrator}, observed {sorted(orchestrator_types)}"
                        )
                    elif not expected_orchestrator_type:
                        errors.append(f"unsupported deploy_orchestrator value: {configured_orchestrator!r}")
                manifest["destination_decision_count"] = decision_count
                manifest["destination_counts"] = decision_counts
                manifest["current_uplink_type_counts"] = current_up_counts
                manifest["ue_with_edge_dc_uplink_count"] = len(source_ids_with_edc_uplink)
                manifest["ue_decision_source_count"] = len(source_ids)
                manifest["none_decisions_with_edge_dc_uplink"] = none_with_edc_uplink
                manifest["local_execution_decisions"] = local_count
                manifest["offloading_decisions"] = decision_count - local_count
                manifest["orchestrator_types_observed"] = sorted(orchestrator_types)
                expected_decision_sources = 1 if method in {"per-task-test", "dqn"} or os.environ.get("PAPER_PER_TASK_VALIDATION_WORKLOAD") == "1" else devices
                if len(source_ids) != expected_decision_sources:
                    errors.append(f"destination log observed {len(source_ids)} source UEs; expected {expected_decision_sources}")
                if target == "EDGE_DC_ONLY" and decision_counts.get("NONE", 0):
                    errors.append(f"{decision_counts['NONE']} EDGE_DC_ONLY tasks had no eligible EDC destination")

        metrics = parse(run)
        manifest["metrics"] = metrics
        if profile == "paper-aligned-baseline" and manifest.get("task_accounting"):
            layer_successes = metrics.get("layer_successful_completions", {})
            if all(layer_successes.get(layer) is not None for layer in ("Cloud", "Edge", "Mist")):
                manifest["task_accounting"]["layer_successful_completions"] = layer_successes
                if sum(layer_successes.values()) != manifest["task_accounting"]["completed_tasks"]:
                    errors.append("global completed tasks do not reconcile with successful destination-layer counts")
        if profile == "paper-aligned-baseline" and metrics["generated_tasks"] != expected_tasks:
            errors.append(f"CSV generated task count {metrics['generated_tasks']} != expected {expected_tasks}")
        if not manifest["simulator_csvs"]:
            errors.append("no authentic PureEdgeSim CSV was preserved")
        manifest["validation_errors"] = errors
        manifest["status"] = "completed" if not errors else "failed"
        if errors:
            manifest["validity"] = "invalid/failed run; artifacts retained and excluded from success claims"
        elif method in {"per-task-test", "dqn"}:
            manifest["validity"] = "deterministic per-task lifecycle validation only; not DQN or performance evidence"
        else:
            manifest["validity"] = "paper-aligned baseline run; not Queue-Aware/GNN/DQN"
        manifest["finished_utc"] = utc_now()
        write_json(run / "config.json", manifest)
        write_json(run / "manifest.json", manifest)
        print(f"Run status: {manifest['status']}; exit={result.returncode}; validation_errors={len(errors)}")
        print(f"RUN_DIR={run}")
        if errors:
            for error in errors: print("VALIDATION_ERROR: " + error)
            print(result.stdout[-5000:])
            return 1
        return 0
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["finished_utc"] = utc_now()
        manifest["validation_errors"] = [str(exc)]
        manifest["validity"] = "failed before successful simulator verification; artifacts retained"
        try:
            (raw / "setup-error.log").write_text(traceback.format_exc())
        except OSError:
            pass
        write_json(run / "config.json", manifest)
        write_json(run / "manifest.json", manifest)
        print(f"Run status: failed; {exc}", file=sys.stderr)
        print(f"RUN_DIR={run}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
