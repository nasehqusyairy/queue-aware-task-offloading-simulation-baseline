#!/usr/bin/env python3
"""Build and execute one isolated PureEdgeSim experiment run."""
from __future__ import annotations

import csv
import hashlib
import json
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
    if len(sys.argv) != 9:
        print("usage: execute_run.py RUN_DIR PROFILE METHOD DEVICES DURATION_SECONDS TARGET ARCHITECTURE ALGORITHM", file=sys.stderr)
        return 2
    run, profile, method, devices_s, duration_s, target, architecture, algorithm = sys.argv[1:]
    run = Path(run).resolve()
    devices, duration = int(devices_s), int(duration_s)
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
        "random_seed": "not controlled; PureEdgeSim uses SecureRandom.getInstanceStrong()",
        "started_utc": start,
        "finished_utc": None,
        "process_exit_code": None,
        "status": "running",
        "simulator_properties": props,
        "configuration_sha256": {
            p.name: sha256(p) for p in sorted(config.iterdir()) if p.is_file()
        },
        "validity": "paper-aligned baseline; not Queue-Aware, GNN, or DQN",
        "energy_scope": "computing nodes (Cloud + Edge Data Centers + user devices); network energy is separate",
    }
    write_json(run / "config.json", manifest)
    write_json(run / "manifest.json", manifest)

    try:
        device_profiles, app_profiles, device_counts, app_counts, source_count, expected_tasks = profile_data(
            config, devices, duration
        )
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
                "duration_cutoff_policy": "hard horizon at t=duration_seconds; tasks still sent but not accounted by cutoff are added to unsuccessful-task accounting and recorded as pending_at_cutoff",
                "local_execution_policy": "destination equal to source UE is local execution, separately marked in destination audit",
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
            command = [
                "java", f"-Dpaper.profile-counts={','.join(map(str, device_counts))}",
                f"-Dpaper.app-counts={','.join(map(str, app_counts))}",
                f"-Dpaper.destination-log={destination_log}", "-cp", classpath,
                "com.mechalikh.pureedgesim.experiment.PaperAlignedMain",
            ]
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
        if "SimulationThread - Simulation Finished!" not in result.stdout:
            errors.append("missing simulator completion marker")
        if "Exception in thread" in result.stdout:
            errors.append("uncaught Java exception in simulator output")
        manifest["process_exit_code"] = result.returncode
        manifest["command"] = command
        manifest["working_directory"] = str(work)
        manifest["simulator_csvs"] = [str(p.relative_to(run)) for p in sorted(raw.rglob("*.csv"))
                                      if p.name != "destinations.csv"]

        if profile == "paper-aligned-baseline":
            device_match = re.search(r"PAPER_DEVICE_COUNTS requested=(\d+) actual=(\d+) profiles=([^ ]+) active_task_sources=(\d+) edge_data_centers=(\d+) cloud=(\d+)", result.stdout)
            task_match = re.search(r"PAPER_TASK_GENERATION simulated_seconds=(\d+) active_devices=(\d+) app_user_counts=([^ ]+) generated_tasks=(\d+)", result.stdout)
            horizon_match = re.search(r"PAPER_HORIZON time_seconds=([0-9.]+) generated=(\d+) sent=(\d+) accounted=(\d+) pending_at_cutoff=(\d+)", result.stdout)
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
                if orchestrator_types and orchestrator_types != {"CLOUD"}:
                    errors.append(f"unexpected orchestrator types: {sorted(orchestrator_types)}")
                manifest["destination_decision_count"] = decision_count
                manifest["destination_counts"] = decision_counts
                manifest["current_uplink_type_counts"] = current_up_counts
                manifest["ue_with_edge_dc_uplink_count"] = len(source_ids_with_edc_uplink)
                manifest["ue_decision_source_count"] = len(source_ids)
                manifest["none_decisions_with_edge_dc_uplink"] = none_with_edc_uplink
                manifest["local_execution_decisions"] = local_count
                manifest["offloading_decisions"] = decision_count - local_count
                manifest["orchestrator_types_observed"] = sorted(orchestrator_types)
                if len(source_ids) != devices:
                    errors.append(f"destination log observed {len(source_ids)} source UEs; expected {devices}")
                if target == "EDGE_DC_ONLY" and decision_counts.get("NONE", 0):
                    errors.append(f"{decision_counts['NONE']} EDGE_DC_ONLY tasks had no eligible EDC destination")

        metrics = parse(run)
        manifest["metrics"] = metrics
        if profile == "paper-aligned-baseline" and metrics["generated_tasks"] != expected_tasks:
            errors.append(f"CSV generated task count {metrics['generated_tasks']} != expected {expected_tasks}")
        if not manifest["simulator_csvs"]:
            errors.append("no authentic PureEdgeSim CSV was preserved")
        manifest["validation_errors"] = errors
        manifest["status"] = "completed" if not errors else "failed"
        manifest["validity"] = ("paper-aligned baseline run; not Queue-Aware/GNN/DQN" if not errors
                                else "invalid/failed run; artifacts retained and excluded from success claims")
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
