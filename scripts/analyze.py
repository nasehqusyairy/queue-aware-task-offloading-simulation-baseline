#!/usr/bin/env python3
import argparse,csv,json
from pathlib import Path

def parse(run):
 metrics={'generated_tasks':None,'successful_tasks':None,'failed_tasks':None,'task_success_rate':None,'energy_consumption':None,'energy_unit':'Wh','workload_distribution':None,'source':'N/A: simulator CSV not located'}
 for path in (run/'raw').rglob('*.csv'):
  try:
   with path.open(newline='',errors='replace') as f:
    for row in csv.DictReader(f):
     gen=row.get('Number of generated tasks'); success=row.get('Tasks successfully executed')
     if gen is None or success is None: continue
     metrics['generated_tasks']=int(float(gen)); metrics['successful_tasks']=int(float(success))
     metrics['failed_tasks']=metrics['generated_tasks']-metrics['successful_tasks']
     metrics['task_success_rate']=metrics['successful_tasks']/metrics['generated_tasks'] if metrics['generated_tasks'] else None
     energy=row.get('Energy consumption of computing nodes (Wh)'); metrics['energy_consumption']=float(energy) if energy else None
     metrics['workload_distribution']={n:int(float(row.get(f'Tasks successfully executed ({n})') or 0)) for n in ('Cloud','Edge','Mist')}
     metrics['source']=str(path.relative_to(run)); return metrics
  except (ValueError,csv.Error): continue
 return metrics

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--run',type=Path); ap.add_argument('--latest',action='store_true'); a=ap.parse_args()
 root=Path(__file__).resolve().parents[1]; runs=root/'results/runs'
 if a.latest:
  targets=[]
  for p in sorted((q for q in runs.iterdir() if q.is_dir()),key=lambda q:q.name):
   try:
    if (p/'manifest.json').exists() and json.loads((p/'manifest.json').read_text()).get('status')=='completed' and any((p/'raw').rglob('*.csv')): targets.append(p)
   except (json.JSONDecodeError,OSError): continue
 else: targets=[a.run] if a.run else []
 if not targets: ap.error('No completed run found; refusing to create aggregate data')
 rows=[]
 for r in targets:
  m=parse(r); (r/'metrics.json').write_text(json.dumps(m,indent=2)+'\n'); cfg=json.loads((r/'config.json').read_text())
  row={**{k:cfg.get(k) for k in ['run_id','method','devices','duration_minutes','duration_seconds','architecture','validity','status']},**m}; rows.append(row)
  (r/'summary.txt').write_text('\n'.join(f'{k}: {v if v is not None else "N/A"}' for k,v in row.items())+'\n')
  print(f"\nRun {r.name}: {cfg['method']} | devices {cfg['devices']} | {cfg['status']}")
  print('Metric                         Result\n'+'-'*54)
  for k in ('generated_tasks','successful_tasks','failed_tasks','task_success_rate','energy_consumption','workload_distribution'): print(f'{k:30} {m[k] if m[k] is not None else "N/A (not present in source CSV)"}')
 (root/'results/processed').mkdir(parents=True,exist_ok=True)
 with (root/'results/processed/summary.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
 (root/'results/processed/summary.json').write_text(json.dumps(rows,indent=2)+'\n')
 html='''<!doctype html><meta charset="utf-8"><title>PureEdgeSim baseline dashboard</title><style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd;padding:.5rem;text-align:left}pre{background:#f4f6f8;padding:1rem}</style><h1>Technical baseline results</h1><p>Values are read from successful-run metrics.json generated from PureEdgeSim CSV. Missing values are shown as N/A.</p><div id="table"></div><canvas id="chart" width="900" height="300"></canvas><h2>Run data</h2><pre id="json"></pre><script>fetch('processed/summary.json').then(r=>r.json()).then(rows=>{json.textContent=JSON.stringify(rows,null,2);table.innerHTML='<table><tr><th>Run</th><th>Method</th><th>UE</th><th>Generated</th><th>Successful</th><th>Success rate</th><th>Energy (Wh)</th></tr>'+rows.map(x=>`<tr><td>${x.run_id}</td><td>${x.method}</td><td>${x.devices}</td><td>${x.generated_tasks??'N/A'}</td><td>${x.successful_tasks??'N/A'}</td><td>${x.task_success_rate==null?'N/A':(100*x.task_success_rate).toFixed(2)+'%'}</td><td>${x.energy_consumption??'N/A'}</td></tr>`).join('')+'</table>';let c=chart.getContext('2d');rows.forEach((x,i)=>{let y=35+i*45;c.fillText(x.method+' ('+x.devices+')',8,y+15);if(x.task_success_rate==null)c.fillText('N/A',220,y+15);else {c.fillStyle='#198754';c.fillRect(220,y,Math.max(1,600*x.task_success_rate),22);c.fillStyle='#111';c.fillText((100*x.task_success_rate).toFixed(2)+'%',830,y+15)}})});</script>'''
 (root/'results/dashboard.html').write_text(html)
 print(f"CSV: {root/'results/processed/summary.csv'}\nJSON: {root/'results/processed/summary.json'}\nDashboard: {root/'results/dashboard.html'}")
if __name__=='__main__': main()
