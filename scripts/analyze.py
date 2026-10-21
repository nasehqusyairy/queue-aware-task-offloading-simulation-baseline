#!/usr/bin/env python3
import argparse,csv,json,math,re,sys
from pathlib import Path

def parse(run):
 raw=run/'raw'; logs=list(raw.rglob('*.txt'))+list(raw.rglob('*.log'))
 text='\n'.join(p.read_text(errors='replace') for p in logs)
 # Simulator log records are parsed conservatively; absent values remain null.
 patterns={'generated_tasks':r'(?:Generated tasks|generated tasks)\s*[:=]\s*(\d+)', 'successful_tasks':r'(?:Successful tasks|successfully executed tasks|Tasks executed successfully)\s*[:=]\s*(\d+)', 'failed_tasks':r'(?:Failed tasks|tasks failed)\s*[:=]\s*(\d+)'}
 metrics={k:(int(m.group(1)) if (m:=re.search(p,text,re.I)) else None) for k,p in patterns.items()}
 if metrics['generated_tasks'] is not None and metrics['successful_tasks'] is not None:
  metrics['task_success_rate']=metrics['successful_tasks']/metrics['generated_tasks'] if metrics['generated_tasks'] else None
 else: metrics['task_success_rate']=None
 metrics.update(energy_consumption=None,energy_unit=None,workload_distribution=None,source='PureEdgeSim raw output; parsed only when identifiable')
 return metrics

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--run',type=Path); ap.add_argument('--latest',action='store_true'); a=ap.parse_args()
 root=Path(__file__).resolve().parents[1]; runs=root/'results/runs'
 targets=[a.run] if a.run else sorted((p for p in runs.iterdir() if p.is_dir()),key=lambda p:p.name) if a.latest else []
 if not targets: ap.error('Specify --run DIR or --latest')
 rows=[]
 for r in targets:
  m=parse(r); (r/'metrics.json').write_text(json.dumps(m,indent=2)+'\n')
  cfg=json.loads((r/'config.json').read_text()) if (r/'config.json').exists() else {}
  rows.append({**{k:cfg.get(k) for k in ['run_id','method','devices','duration_minutes','architecture','validity']},**m})
  (r/'summary.txt').write_text('\n'.join(f'{k}: {v if v is not None else "N/A (not extracted from simulator output)"}' for k,v in rows[-1].items())+'\n')
  print(f"\nRun: {r.name} | Method: {cfg.get('method')} | devices: {cfg.get('devices')} | Status: {cfg.get('status','unknown')}")
  print(f"{'Metric':28} Result\n{'-'*48}")
  for k in ('generated_tasks','successful_tasks','failed_tasks','task_success_rate','energy_consumption'):
   v=m.get(k); print(f'{k:28} {v if v is not None else "N/A (metric unavailable / parser not matched)"}')
  print(f'raw simulator files           {sum(1 for p in (r/"raw").rglob("*") if p.is_file())}')
 with (root/'results/processed/summary.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
 (root/'results/processed/summary.json').write_text(json.dumps(rows,indent=2)+'\n')
 html='''<!doctype html><html><head><meta charset="utf-8"><title>Task Offloading Results</title><style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#182230}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd;padding:.5rem;text-align:left}pre{background:#f4f6f8;padding:1rem;overflow:auto}</style></head><body><h1>Task Offloading Baseline Results</h1><p>Dashboard generated from actual run metrics JSON. Unavailable measures remain N/A.</p><div id="summary"></div><canvas id="chart" width="900" height="320"></canvas><h2>Raw run records</h2><pre id="raw"></pre><script>fetch('../processed/summary.json').then(r=>r.json()).then(rows=>{document.querySelector('#raw').textContent=JSON.stringify(rows,null,2);let d=rows.map(x=>`<tr><td>${x.method||'N/A'}</td><td>${x.devices??'N/A'}</td><td>${x.generated_tasks??'N/A'}</td><td>${x.successful_tasks??'N/A'}</td><td>${x.task_success_rate==null?'N/A':(100*x.task_success_rate).toFixed(2)+'%'}</td><td>${x.energy_consumption??'N/A'}</td></tr>`).join('');document.querySelector('#summary').innerHTML='<table><thead><tr><th>Method</th><th>Devices</th><th>Generated</th><th>Success</th><th>Success rate</th><th>Energy</th></tr></thead><tbody>'+d+'</tbody></table>';let c=document.querySelector('#chart').getContext('2d'), w=800,h=250;c.fillStyle='#52677c';c.font='14px sans-serif';rows.forEach((x,i)=>{let y=35+i*45;c.fillText((x.method||'run')+' ('+(x.devices||'?')+')',8,y+15);if(x.task_success_rate!=null){c.fillStyle='#2a8';c.fillRect(220,y,Math.max(1,w*x.task_success_rate),24);c.fillStyle='#111';c.fillText((100*x.task_success_rate).toFixed(2)+'%',230+w*x.task_success_rate,y+17)}else{c.fillStyle='#777';c.fillText('N/A — success-rate source not parsed',220,y+17)}});});</script></body></html>'''
 (root/'results/dashboard.html').write_text(html)
 print(f'CSV: {root}/results/processed/summary.csv\nJSON: {root}/results/processed/summary.json\nDashboard: {root}/results/dashboard.html')
if __name__=='__main__': main()
