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
        "successful_tasks": None,
        "failed_tasks": None,
        "task_success_rate": None,
        "energy_consumption": None,
        "energy_unit": "Wh",
        "energy_scope": "computing nodes (Cloud + Edge Data Centers + user devices); network energy is separate",
        "workload_distribution": {layer: None for layer in LAYERS},
        "workload_distribution_unit": "tasks executed at each PureEdgeSim layer",
        "source": "N/A: simulator CSV not located",
        "validation_errors": [],
    }
    raw = run / "raw"
    for path in sorted(raw.rglob("*.csv")) if raw.exists() else []:
        try:
            with path.open(newline="", errors="replace") as stream:
                reader = csv.DictReader(stream)
                if not reader.fieldnames or "Number of generated tasks" not in reader.fieldnames:
                    continue
                for row in reader:
                    generated = _optional_number(row.get("Number of generated tasks"), int)
                    successful = _optional_number(row.get("Tasks successfully executed"), int)
                    if generated is None or successful is None:
                        continue
                    metrics["generated_tasks"] = generated
                    metrics["successful_tasks"] = successful
                    metrics["failed_tasks"] = generated - successful
                    metrics["task_success_rate"] = successful / generated if generated else None
                    if successful > generated or successful < 0:
                        metrics["validation_errors"].append("successful task count is outside [0, generated]")
                    metrics["energy_consumption"] = _optional_number(
                        row.get("Energy consumption of computing nodes (Wh)"), float
                    )
                    metrics["workload_distribution"] = {
                        layer: _optional_number(row.get(f"Total tasks executed ({layer})"), int)
                        for layer in LAYERS
                    }
                    metrics["source"] = str(path.relative_to(run))
                    return metrics
        except (OSError, ValueError, csv.Error):
            continue
    return metrics


def _dashboard_html():
    return """<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>PureEdgeSim experiment results</title>
<style>body{font:15px system-ui,sans-serif;margin:2rem;color:#172033}table{border-collapse:collapse;width:100%;font-size:13px}td,th{border:1px solid #ccd3df;padding:.45rem;text-align:left}th{background:#f1f4f8}pre{white-space:pre-wrap}</style>
<h1>PureEdgeSim experiment results</h1><p>Missing source values are N/A; zero is a measured value. Workload is total tasks executed per layer.</p><div id=\"status\">Loading…</div><div style=\"overflow:auto\"><table><thead><tr><th>Run</th><th>Status</th><th>Profile</th><th>Method</th><th>UE requested</th><th>Duration (s)</th><th>Target</th><th>Generated</th><th>Successful</th><th>Failed</th><th>Success rate</th><th>Energy (Wh)</th><th>Workload Cloud / Edge / Mist</th></tr></thead><tbody id=\"rows\"></tbody></table></div>
<script>fetch('./summary.json').then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.json()}).then(data=>{status.textContent=data.length+' run records';for(const x of data){const tr=document.createElement('tr');const vals=[x.run_id,x.status,x.profile,x.method,x.devices,x.duration_seconds,x.destination_config??x.architecture,x.generated_tasks,x.successful_tasks,x.failed_tasks,x.task_success_rate==null?'N/A':(100*x.task_success_rate).toFixed(2)+'%',x.energy_consumption??'N/A',...( ['Cloud','Edge','Mist'].map(k=>x.workload_distribution?.[k]??'N/A') )];for(const v of vals){const td=document.createElement('td');td.textContent=String(v??'N/A');tr.appendChild(td)}rows.appendChild(tr)}}).catch(e=>status.textContent='Could not load summary.json: '+e.message);</script></html>"""


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
    }
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
