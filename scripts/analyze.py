#!/usr/bin/env python3
"""Read PureEdgeSim run artifacts without changing historical summaries."""
import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

LAYERS = ("Cloud", "Edge", "Mist")


def _optional_number(value, cast):
    if value is None or str(value).strip() == "":
        return None
    return cast(float(value))


def parse(run):
    metrics = {
        "generated_tasks": None,
        "sent_tasks": None,
        "completed_tasks": None,
        "terminally_failed_tasks": None,
        "rejected_before_pipeline_tasks": None,
        "pending_tasks": None,
        "successful_tasks": None,
        "failed_tasks": None,
        "task_success_rate": None,
        "task_failure_rate": None,
        "task_pending_rate": None,
        "energy_consumption": None,
        "energy_unit": "Wh",
        "energy_scope": "computing nodes (Cloud + Edge Data Centers + user devices); network energy is separate",
        "workload_distribution": {layer: None for layer in LAYERS},
        "workload_distribution_unit": "tasks dispatched to each destination layer",
        "source": "N/A: simulator CSV not located",
        "validation_errors": [],
    }
    raw = run / "raw"
    found_metrics_csv = False
    for path in sorted(raw.rglob("*.csv")) if raw.exists() else []:
        try:
            with path.open(newline="", errors="replace") as stream:
                reader = csv.DictReader(stream)
                if not reader.fieldnames:
                    continue
                if "Number of generated tasks" not in reader.fieldnames:
                    continue
                found_metrics_csv = True
                required = ("Tasks successfully executed", "Tasks sent", "Tasks completed",
                            "Tasks terminally failed", "Tasks pending at cutoff", "Tasks rejected before pipeline")
                missing = [column for column in required if column not in reader.fieldnames]
                if missing:
                    metrics["source"] = str(path.relative_to(run))
                    metrics["validation_errors"].append("missing required simulator columns: " + ", ".join(missing))
                    return metrics
                for row in reader:
                    generated = _optional_number(row.get("Number of generated tasks"), int)
                    successful = _optional_number(row.get("Tasks successfully executed"), int)
                    if generated is None or successful is None:
                        metrics["source"] = str(path.relative_to(run))
                        metrics["validation_errors"].append("generated or successful task count is missing/empty")
                        continue
                    sent = _optional_number(row.get("Tasks sent"), int)
                    completed = _optional_number(row.get("Tasks completed"), int)
                    failed = _optional_number(row.get("Tasks terminally failed"), int)
                    pending = _optional_number(row.get("Tasks pending at cutoff"), int)
                    rejected = _optional_number(row.get("Tasks rejected before pipeline"), int)
                    metrics["generated_tasks"] = generated
                    metrics["sent_tasks"] = sent
                    metrics["completed_tasks"] = completed if completed is not None else successful
                    metrics["terminally_failed_tasks"] = failed
                    metrics["rejected_before_pipeline_tasks"] = rejected
                    metrics["pending_tasks"] = pending
                    metrics["successful_tasks"] = metrics["completed_tasks"]
                    metrics["failed_tasks"] = failed
                    metrics["task_success_rate"] = metrics["completed_tasks"] / generated if generated else None
                    metrics["task_failure_rate"] = failed / generated if failed is not None and generated is not None and generated else None
                    metrics["task_pending_rate"] = pending / generated if pending is not None and generated is not None and generated else None
                    if None not in (generated, completed, failed, pending):
                        if generated != completed + failed + pending:
                            metrics["validation_errors"].append("generated != completed + terminally_failed + pending")
                        if any(value < 0 for value in (generated, completed, failed, pending)):
                            metrics["validation_errors"].append("task accounting counters must be non-negative")
                        if rejected is not None and failed is not None and rejected > failed:
                            metrics["validation_errors"].append("rejected-before-pipeline count exceeds terminal failures")
                    if successful > generated or successful < 0:
                        metrics["validation_errors"].append("successful task count is outside [0, generated]")
                    metrics["energy_consumption"] = _optional_number(
                        row.get("Energy consumption of computing nodes (Wh)"), float
                    )
                    metrics["workload_distribution"] = {
                        layer: _optional_number(row.get(f"Total tasks executed ({layer})"), int)
                        for layer in LAYERS
                    }
                    metrics["layer_successful_completions"] = {
                        layer: _optional_number(row.get(f"Tasks successfully executed ({layer})"), int)
                        for layer in LAYERS
                    }
                    layer_values = metrics["layer_successful_completions"].values()
                    if all(value is not None for value in layer_values) and metrics["completed_tasks"] is not None:
                        if sum(layer_values) != metrics["completed_tasks"]:
                            metrics["validation_errors"].append(
                                "global completed tasks do not reconcile with successful destination-layer counts"
                            )
                    metrics["source"] = str(path.relative_to(run))
                    return metrics
        except (OSError, ValueError, csv.Error) as exc:
            if found_metrics_csv:
                metrics["source"] = str(path.relative_to(run))
                metrics["validation_errors"].append(f"invalid simulator CSV value: {exc}")
                return metrics
            continue
    if not found_metrics_csv:
        metrics["validation_errors"].append("no simulator CSV with required task-count columns")
    return metrics


def _dashboard_html():
    return """<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>PureEdgeSim experiment results</title>
<style>body{font:15px system-ui,sans-serif;margin:2rem;color:#172033}table{border-collapse:collapse;width:100%;font-size:13px}td,th{border:1px solid #ccd3df;padding:.45rem;text-align:left}th{background:#f1f4f8}pre{white-space:pre-wrap}</style>
<h1>PureEdgeSim experiment results</h1><p>Rates use generated tasks as denominator. Missing values are N/A; layer workload is dispatched tasks.</p><div id=\"status\">Loading…</div><div style=\"overflow:auto\"><table><thead><tr><th>Run</th><th>Status</th><th>Profile</th><th>Method</th><th>UE requested</th><th>Duration (s)</th><th>Target</th><th>Generated</th><th>Sent</th><th>Completed</th><th>Terminal failures</th><th>Rejected before pipeline</th><th>Pending</th><th>Success rate</th><th>Energy (Wh)</th><th>Workload Cloud / Edge / Mist</th></tr></thead><tbody id=\"rows\"></tbody></table></div>
<script>fetch('./summary.json').then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.json()}).then(data=>{status.textContent=data.length+' run records';for(const x of data){const tr=document.createElement('tr');const vals=[x.run_id,x.status,x.profile,x.method,x.devices,x.duration_seconds,x.destination_config??x.architecture,x.generated_tasks,x.sent_tasks,x.completed_tasks,x.terminally_failed_tasks,x.rejected_before_pipeline_tasks,x.pending_tasks,x.task_success_rate==null?'N/A':(100*x.task_success_rate).toFixed(2)+'%',x.energy_consumption??'N/A',...( ['Cloud','Edge','Mist'].map(k=>x.workload_distribution?.[k]??'N/A') )];for(const v of vals){const td=document.createElement('td');td.textContent=String(v??'N/A');tr.appendChild(td)}rows.appendChild(tr)}}).catch(e=>status.textContent='Could not load summary.json: '+e.message);</script></html>"""


def _read_config(run):
    for name in ("config.json", "manifest.json"):
        path = run / name
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def _row_for_run(run):
    config = _read_config(run)
    metrics = parse(run)

    # Keep run-level validation failures separate from parser/metric checks.
    # Previously, **metrics overwrote manifest.validation_errors with the
    # parser's usually-empty list, hiding why a simulation was marked failed.
    manifest_errors = config.get("validation_errors", [])
    metric_errors = metrics.pop("validation_errors", [])
    if not isinstance(manifest_errors, list):
        manifest_errors = [str(manifest_errors)]
    if not isinstance(metric_errors, list):
        metric_errors = [str(metric_errors)]

    row = {
        "run_id": config.get("run_id", run.name),
        "profile": config.get("profile", "technical-baseline"),
        "method": config.get("method"),
        "devices": config.get("devices"),
        "duration_seconds": config.get("duration_seconds"),
        "architecture": config.get("architecture"),
        "destination_config": config.get("destination_config"),
        "simulator_revision": config.get("simulator_revision"),
        "status": config.get("status", "unknown"),
        **metrics,
        "validation_errors": manifest_errors,
        "metric_validation_errors": metric_errors,
    }
    # Preserve execution-time accounting from the run manifest, if available.
    accounting = config.get("task_accounting")
    if isinstance(accounting, dict):
        for key in ("generated_tasks", "sent_tasks", "completed_tasks", "terminally_failed_tasks", "pending_tasks",
                    "rejected_before_pipeline_tasks",
                    "layer_successful_completions"):
            if accounting.get(key) is not None:
                row[key] = accounting[key]
    return row


def _unique_output_dir(base):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = base / stamp
    if path.exists():
        raise FileExistsError(f"refusing to overwrite prior processed output: {path}")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, help="analyze one run in place; does not write aggregate files")
    parser.add_argument("--latest", action="store_true", help="aggregate every manifest for one profile, including failed runs")
    parser.add_argument("--profile", default="technical-baseline")
    parser.add_argument("--output-dir", type=Path, help="new, empty destination for aggregate files")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    runs = root / "results" / "runs"
    if args.run:
        run = args.run.resolve()
        row = _row_for_run(run)
        (run / "metrics.json").write_text(json.dumps(row, indent=2) + "\n")
        (run / "summary.txt").write_text("\n".join(f"{k}: {v if v is not None else 'N/A'}" for k, v in row.items()) + "\n")
        print(json.dumps(row, indent=2))
        return 0
    if not args.latest:
        parser.error("choose --run or --latest")

    targets = []
    if runs.exists():
        for run in sorted((p for p in runs.iterdir() if p.is_dir()), key=lambda p: p.name):
            config = _read_config(run)
            if config and config.get("profile", "technical-baseline") == args.profile:
                targets.append(run)
    if not targets:
        parser.error(f"No run manifests found for profile {args.profile!r}")

    rows = [_row_for_run(run) for run in targets]
    output = args.output_dir or _unique_output_dir(root / "results" / "processed" / args.profile)
    if output.exists() and any(output.iterdir()):
        parser.error(f"refusing to overwrite non-empty output directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(json.dumps(rows, indent=2) + "\n")
    csv_rows = []
    for row in rows:
        csv_rows.append({**row, "workload_distribution": json.dumps(row["workload_distribution"], sort_keys=True),
                         "validation_errors": json.dumps(row["validation_errors"])})
    with (output / "summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)
    (output / "dashboard.html").write_text(_dashboard_html())
    print(f"Runs included: {len(rows)} (including failed/invalid records)")
    print(f"CSV: {output / 'summary.csv'}\nJSON: {output / 'summary.json'}\nDashboard: {output / 'dashboard.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
