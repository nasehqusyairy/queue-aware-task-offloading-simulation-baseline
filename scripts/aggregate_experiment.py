#!/usr/bin/env python3
"""Aggregate authentic metrics.json from one experiment output directory."""
import argparse, csv, json
from pathlib import Path

FIELDS = ["run_id", "method", "workload", "devices", "seed", "duration_seconds", "status",
          "generated_tasks", "completed_tasks", "terminally_failed_tasks", "pending_tasks",
          "task_success_rate", "energy_consumption", "average_completed_task_total_delay_seconds",
          "average_completed_task_waiting_time_seconds", "average_cpu_execution_time_seconds",
          "workload_cloud_tasks", "workload_edge_tasks", "workload_mist_tasks", "destination_layer_cv",
          "source_metrics", "validation_errors"]

def aggregate(root: Path):
    rows=[]
    for mp in sorted(root.glob("runs/*/manifest.json")):
        try: m=json.loads(mp.read_text()); metric_path=mp.parent/"metrics.json"; metrics=json.loads(metric_path.read_text()) if metric_path.exists() else m.get("metrics", {})
        except (OSError, ValueError): continue
        devices=m.get("devices", metrics.get("devices")); level={10:"low",20:"medium",30:"high"}.get(devices, m.get("workload_level", "unknown"))
        dist=metrics.get("workload_distribution") or {}
        vals=[float(dist.get(k) or 0) for k in ("Cloud","Edge","Mist")]
        mean=sum(vals)/3
        cv=(sum((x-mean)**2 for x in vals)/3)**0.5/mean if mean else None
        acct=m.get("task_accounting", {})
        completed=metrics.get("completed_tasks",acct.get("completed_tasks")); failed=metrics.get("terminally_failed_tasks",acct.get("terminally_failed_tasks")); pending=metrics.get("pending_tasks",acct.get("pending_tasks")); generated=metrics.get("generated_tasks",acct.get("generated_tasks"))
        success=(completed/generated if generated else None)
        row={"run_id":m.get("run_id",mp.parent.name), "method":m.get("method",metrics.get("method")), "workload":level,
             "devices":devices,"seed":m.get("random_seed"),"duration_seconds":m.get("duration_seconds"),
             "status":m.get("status","unknown"),"generated_tasks":generated,"completed_tasks":completed,
             "terminally_failed_tasks":failed,"pending_tasks":pending,"task_success_rate":success if success is not None else metrics.get("task_success_rate"),
             "energy_consumption":metrics.get("energy_consumption"),
             "average_completed_task_total_delay_seconds":metrics.get("average_completed_task_total_delay_seconds"),
             "average_completed_task_waiting_time_seconds":metrics.get("average_completed_task_waiting_time_seconds"),
             "average_cpu_execution_time_seconds":metrics.get("average_cpu_execution_time_seconds"),
             "workload_cloud_tasks":vals[0],"workload_edge_tasks":vals[1],"workload_mist_tasks":vals[2],"destination_layer_cv":cv,
             "source_metrics":metrics.get("source",""),"validation_errors":"; ".join(m.get("validation_errors",[])+metrics.get("validation_errors",[])+metrics.get("metric_validation_errors",[]))}
        rows.append(row)
    rows.sort(key=lambda r:(str(r['workload']),int(r['seed']) if str(r['seed']).lstrip('-').isdigit() else -1,str(r['method']),r['run_id']))
    out=root/"aggregate.csv"; out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    # Keep aggregate with successful runs only; include all rows and status in CSV for audit.
    valid=[r for r in rows if r['status']=='completed' and not r['validation_errors']]
    groups={}
    for r in valid:
        k=(r['method'],r['workload']); groups.setdefault(k,[]).append(r)
    summary=[]
    for (method,workload), group in sorted(groups.items()):
        for metric in ('task_success_rate','energy_consumption','average_completed_task_total_delay_seconds'):
            vals=[float(x[metric]) for x in group if x[metric] not in (None,'')]
            summary.append({"method":method,"workload":workload,"metric":metric,"n":len(vals),"mean":sum(vals)/len(vals) if vals else None,
                            "min":min(vals) if vals else None,"max":max(vals) if vals else None})
    with (root/"aggregate_summary.csv").open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=["method","workload","metric","n","mean","min","max"]); w.writeheader(); w.writerows(summary)
    return rows

def main():
    p=argparse.ArgumentParser(); p.add_argument('output',type=Path); a=p.parse_args(); rows=aggregate(a.output); print(f"AGGREGATE_ROWS={len(rows)} OUTPUT={a.output.resolve()/'aggregate.csv'}")
if __name__=='__main__': main()
