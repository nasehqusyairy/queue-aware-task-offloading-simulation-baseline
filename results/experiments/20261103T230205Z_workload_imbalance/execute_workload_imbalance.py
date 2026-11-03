#!/usr/bin/env python3
"""Run seed-1 pilot first; only enter 45-cell matrix after pilot validation."""
import argparse, csv, json, os, shlex, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
EXP=Path(__file__).resolve().parent
CFG=json.loads((EXP/'workload_profiles.json').read_text())
CONDITIONS=CFG['home_workload_matrices_users_by_edc_app']
METHODS=CFG['methods']
SEEDS=CFG['seeds']
STATUS=EXP/'run_status.json'

def matrix_string(mat): return ';'.join(','.join(map(str,row)) for row in mat)
def key(condition,method,weight,seed): return (condition,method,1.0 if weight is None else float(weight),int(seed))
def load_status():
    if STATUS.exists(): return json.loads(STATUS.read_text())
    return {'experiment_id':CFG['experiment_id'],'planned_full_runs':45,'runs':[],'status':'not_started'}
def store(s):
    STATUS.write_text(json.dumps(s,indent=2)+'\n')
def find_run(condition,method,weight,seed):
    root=EXP/'runs'/condition
    paths=root.glob('*/manifest.json') if root.exists() else []
    for p in paths:
        m=json.loads(p.read_text())
        if (m.get('home_workload_condition')==condition and m.get('method')==method
            and int(m.get('random_seed') or -999)==seed
            and (method!='queue-aware' or float(m.get('queue_penalty_weight',-1))==float(weight))):
            return p.parent,m
    return None,None

def run_cell(condition,method,weight,seed,status):
    found,m=find_run(condition,method,weight,seed)
    if found and m.get('status')=='completed' and m.get('process_exit_code')==0 and not m.get('validation_errors'):
        print(f'SKIP existing valid {condition}/{method}/lambda{weight}/seed{seed} run={m["run_id"]}',flush=True)
        return True
    matrix=matrix_string(CONDITIONS[condition])
    runroot=EXP/'runs'/condition
    env=os.environ.copy()
    env.update({'PAPER_TASK_EVENT_TRACE':'1','PAPER_HOME_WORKLOAD_CONDITION':condition,
                'PAPER_HOME_WORKLOAD_MATRIX':matrix,'RUNS_ROOT':str(runroot),
                'PATH':'/tmp/task-trace-bin:'+env.get('PATH','')})
    cmd=[str(ROOT/'run.sh'),'--profile',CFG['profile'],'--method',method,'--devices',str(CFG['devices']),
         '--duration-seconds',str(CFG['duration_seconds']),'--destination-config',CFG['destination'],
         '--seed',str(seed),'--queue-weight',str(weight)]
    label=f'{condition}_{method}_lambda{weight:g}_seed{seed}'
    (EXP/'commands_run.txt').open('a').write(
        ' '.join([f'PAPER_HOME_WORKLOAD_CONDITION={shlex.quote(condition)}',
                  f'PAPER_HOME_WORKLOAD_MATRIX={shlex.quote(matrix)}',
                  'PAPER_TASK_EVENT_TRACE=1',f'RUNS_ROOT={shlex.quote(str(runroot))}',
                  'PATH=/tmp/task-trace-bin:$PATH']+[shlex.quote(x) for x in cmd])+'\n')
    print(f'RUN {label}',flush=True)
    proc=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
    log=(EXP/f'{label}_console.log').open('w')
    for line in proc.stdout:
        sys.stdout.write(line);sys.stdout.flush();log.write(line);log.flush()
    rc=proc.wait();log.close()
    run,m=find_run(condition,method,weight,seed)
    ok=(rc==0 and m is not None and m.get('status')=='completed' and m.get('process_exit_code')==0
        and not m.get('validation_errors'))
    record={'condition':condition,'method':method,'queue_weight':float(weight) if method=='queue-aware' else None,
            'seed':seed,'status':'completed' if ok else 'failed','exit_code':rc,
            'run_id':m.get('run_id') if m else None,'validation_errors':m.get('validation_errors',[]) if m else ['manifest missing']}
    old=[r for r in status['runs'] if key(r['condition'],r['method'],r.get('queue_weight',1.0),r['seed'])!=key(condition,method,weight,seed)]
    status['runs']=old+[record];status['updated_utc']=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat();store(status)
    print(f'END {label} exit={rc} status={record["status"]}',flush=True)
    return ok

def pilot_valid():
    p=EXP/'analysis_validation.json'
    if not p.exists(): return False
    return json.loads(p.read_text()).get('pilot_valid',False)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--pilot-only',action='store_true');ap.add_argument('--full',action='store_true')
    args=ap.parse_args()
    if args.pilot_only and args.full: ap.error('choose either --pilot-only or --full')
    status=load_status();status['status']='pilot_running';store(status)
    pilotcells=[(c,m['name'],m['queue_weight'],1) for c in CONDITIONS for m in METHODS]
    for cell in pilotcells:
        if not run_cell(*cell,status):
            status['status']='pilot_run_failed';store(status);return 1
    an=subprocess.run([sys.executable,str(EXP/'analyze_workload_imbalance.py'),'--pilot'],cwd=ROOT)
    if an.returncode or not pilot_valid():
        status['status']='pilot_gate_failed';store(status)
        print('PILOT_GATE=FAIL; full matrix not started',flush=True);return 2
    status['pilot_valid']=True;status['status']='pilot_validated';store(status)
    if args.pilot_only:
        print('PILOT_GATE=PASS; full matrix not requested',flush=True);return 0
    if not args.full:
        print('Pilot passed. Re-run with --full to execute the remaining 36 cells.',flush=True);return 0
    status['status']='full_matrix_running';store(status)
    for seed in SEEDS:
        if seed==1: continue
        for condition in CONDITIONS:
            for m in METHODS:
                if not run_cell(condition,m['name'],m['queue_weight'],seed,status):
                    status['status']='matrix_run_failed';store(status);return 3
    status['status']='completed';status['successful_runs']=sum(r['status']=='completed' for r in status['runs'])
    status['failed_runs']=sum(r['status']!='completed' for r in status['runs']);store(status)
    subprocess.run([sys.executable,str(EXP/'analyze_workload_imbalance.py')],cwd=ROOT,check=False)
    print(f'MATRIX_STATUS={status["status"]} completed={status["successful_runs"]}/45 failed={status["failed_runs"]}',flush=True)
    return 0 if status['successful_runs']==45 and status['failed_runs']==0 else 4

if __name__=='__main__': raise SystemExit(main())
