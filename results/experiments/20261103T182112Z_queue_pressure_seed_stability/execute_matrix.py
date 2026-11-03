#!/usr/bin/env python3
import argparse,json,os,shutil,subprocess,sys
from pathlib import Path
script_dir=Path(__file__).resolve().parent
repo_root=script_dir.parents[2]
parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path,help='new empty experiment directory; defaults to this experiment directory')
args=parser.parse_args()
root=(args.output.resolve() if args.output else script_dir)
if root.exists() and any(root.iterdir()):
 if root==script_dir:
  raise SystemExit(f'Refusing to rerun into existing experiment directory: {root}; pass --output to a new empty directory.')
 raise SystemExit(f'Refusing to overwrite nonempty output directory: {root}')
root.mkdir(parents=True,exist_ok=True)
if root!=script_dir:
 for filename in ('matrix.json','analyze_matrix.py','execute_matrix.py'):
  shutil.copy2(script_dir/filename,root/filename)
cfg=json.loads((root/'matrix.json').read_text())
cfg['experiment_id']=root.name
(root/'matrix.json').write_text(json.dumps(cfg,indent=2)+'\n')
runs=[]
env=os.environ.copy();env['PAPER_TASK_EVENT_TRACE']='1';env['RUNS_ROOT']=str(root/'runs');env['PATH']='/tmp/task-trace-bin:'+env.get('PATH','')
for seed in cfg['seeds']:
 for method in cfg['methods']:
  cmd=[str(repo_root/'run.sh'),'--profile',cfg['profile'],'--method',method,'--devices',str(cfg['devices']),'--duration-seconds',str(cfg['duration_seconds']),'--destination-config',cfg['destination_config'],'--seed',str(seed),'--queue-weight',str(cfg['queue_penalty_lambda'])]
  label=f'{method}_seed{seed}'
  print(f'RUN_START {label} command='+' '.join(cmd),flush=True)
  log=(root/f'{label}_console.log').open('w')
  proc=subprocess.Popen(cmd,cwd=root.parents[2],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
  for line in proc.stdout:
   sys.stdout.write(line);sys.stdout.flush();log.write(line);log.flush()
  code=proc.wait();log.close()
  run_dirs=sorted((root/'runs').glob(f'*_{method}_30ue_EDGE_DC_ONLY_seed{seed}'))
  run_dir=str(run_dirs[-1].resolve()) if run_dirs else None
  record={'method':method,'seed':seed,'command':cmd,'exit_code':code,'run_dir':run_dir,'status':'completed' if code==0 and run_dir and (Path(run_dir)/'manifest.json').exists() and json.loads((Path(run_dir)/'manifest.json').read_text()).get('status')=='completed' else 'failed'}
  runs.append(record);(root/'run_status.json').write_text(json.dumps({'planned_runs':10,'runs':runs},indent=2)+'\n')
  print(f'RUN_END {label} exit={code} status={record["status"]} run_dir={run_dir}',flush=True)
