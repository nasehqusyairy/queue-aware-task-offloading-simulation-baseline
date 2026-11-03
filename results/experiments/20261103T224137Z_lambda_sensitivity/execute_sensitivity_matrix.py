#!/usr/bin/env python3
"""Run the remaining cells after a successful lambda-zero equivalence pilot."""
import json,os,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
root=Path(__file__).resolve().parent
repo=root.parents[2]
cfg=json.loads((root/'matrix.json').read_text())
pilot=json.loads((root/'pilot_validation.json').read_text())
if not pilot.get('validation_pass'):
 raise SystemExit('Pilot equivalence gate failed; refusing to start full matrix.')
plan=[]
for seed in cfg['seeds']:
 plan.append(('trade-off',None,seed))
 for weight in cfg['queue_penalty_weights']:
  plan.append(('queue-aware',weight,seed))

def find_run(method,weight,seed):
 for mp in sorted((root/'runs').glob('*/manifest.json')):
  try:m=json.loads(mp.read_text())
  except Exception:continue
  if m.get('method')!=method or str(m.get('random_seed'))!=str(seed):continue
  if method=='queue-aware' and float(m.get('queue_penalty_weight',-1))!=float(weight):continue
  if method=='trade-off' and m.get('status')=='completed':return mp.parent,m
  if method=='queue-aware':return mp.parent,m
 return None,None

def valid_completed(method,weight,seed):
 p,m=find_run(method,weight,seed)
 return (p,m) if p and m.get('status')=='completed' and m.get('process_exit_code')==0 and not m.get('validation_errors') else (None,m)

status={'experiment_id':root.name,'planned_runs':25,'pilot_pass':True,'runs':[],'started_utc':datetime.now(timezone.utc).isoformat()}
# Record pilot runs as the first two planned cells.
for method,weight,seed in [('trade-off',None,1),('queue-aware',0.0,1)]:
 p,m=valid_completed(method,weight,seed)
 if p is None:raise SystemExit(f'Pilot run missing or invalid: {method}, lambda={weight}, seed={seed}')
 status['runs'].append({'method':method,'lambda':weight,'seed':seed,'status':'completed','exit_code':0,'run_id':m['run_id']})
(root/'run_status.json').write_text(json.dumps(status,indent=2)+'\n')
commands=[]
for method,weight,seed in plan:
 lam=1.0 if method=='trade-off' else weight
 cmd=[str(repo/'run.sh'),'--profile',cfg['profile'],'--method',method,'--devices',str(cfg['devices']),'--duration-seconds',str(cfg['duration_seconds']),'--destination-config',cfg['destination_config'],'--seed',str(seed),'--queue-weight',str(lam)]
 commands.append('PATH=/tmp/task-trace-bin:$PATH PAPER_TASK_EVENT_TRACE=1 RUNS_ROOT=results/experiments/'+root.name+'/runs '+' '.join(cmd))
(root/'commands_run.txt').write_text('Exact command per matrix cell (pilot cells are also included):\n\n'+'\n'.join(commands)+'\n\nThe local PATH prefix invokes Maven offline in this host. On a normal clone, omit only `PATH=/tmp/task-trace-bin:$PATH`.\n')

completed=2
for idx,(method,weight,seed) in enumerate(plan,1):
 p,m=valid_completed(method,weight,seed)
 if p:
  print(f'[{idx}/25] SKIP completed {method} lambda={weight} seed={seed} run={m["run_id"]}',flush=True);continue
 if m:
  # Preserve failed attempt artifacts; the run.sh creates a fresh unique directory on retry.
  print(f'[{idx}/25] RETRY prior invalid attempt {method} lambda={weight} seed={seed}',flush=True)
 lam=1.0 if method=='trade-off' else weight
 cmd=[str(repo/'run.sh'),'--profile',cfg['profile'],'--method',method,'--devices',str(cfg['devices']),'--duration-seconds',str(cfg['duration_seconds']),'--destination-config',cfg['destination_config'],'--seed',str(seed),'--queue-weight',str(lam)]
 env=os.environ.copy();env['PAPER_TASK_EVENT_TRACE']='1';env['RUNS_ROOT']=str(root/'runs');env['PATH']='/tmp/task-trace-bin:'+env.get('PATH','')
 label=f'{method}_lambda{lam}_seed{seed}'
 print(f'[{idx}/25] RUN {label}',flush=True)
 log=(root/f'{label}_console.log').open('w')
 proc=subprocess.Popen(cmd,cwd=repo,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
 for line in proc.stdout:
  sys.stdout.write(line);sys.stdout.flush();log.write(line);log.flush()
 rc=proc.wait();log.close()
 # Identify newly-created run from method/seed/lambda; only current new run is latest.
 found=[]
 for mp in (root/'runs').glob('*/manifest.json'):
  try:mm=json.loads(mp.read_text())
  except Exception:continue
  if mm.get('method')==method and str(mm.get('random_seed'))==str(seed) and (method!='queue-aware' or float(mm.get('queue_penalty_weight',-1))==float(weight)):
   found.append((mp.parent,mm))
 found.sort(key=lambda x:x[0].name)
 run_dir,manifest=found[-1] if found else (None,None)
 ok=rc==0 and manifest is not None and manifest.get('status')=='completed' and not manifest.get('validation_errors')
 status['runs'].append({'method':method,'lambda':weight,'seed':seed,'status':'completed' if ok else 'failed','exit_code':rc,'run_id':manifest.get('run_id') if manifest else None,'validation_errors':manifest.get('validation_errors',[]) if manifest else ['run manifest missing']})
 completed+=int(ok)
 status['successful_runs']=completed;status['updated_utc']=datetime.now(timezone.utc).isoformat();(root/'run_status.json').write_text(json.dumps(status,indent=2)+'\n')
 print(f'[{idx}/25] END {label} exit={rc} status={"completed" if ok else "failed"}',flush=True)
status['successful_runs']=sum(x['status']=='completed' for x in status['runs']);status['failed_runs']=25-status['successful_runs'];status['status']='completed' if status['successful_runs']==25 else 'completed_with_failures';status['finished_utc']=datetime.now(timezone.utc).isoformat();(root/'run_status.json').write_text(json.dumps(status,indent=2)+'\n')
print(f'MATRIX_STATUS={status["status"]} successful={status["successful_runs"]}/25 failed={status["failed_runs"]}',flush=True)
raise SystemExit(0 if status['failed_runs']==0 else 1)
