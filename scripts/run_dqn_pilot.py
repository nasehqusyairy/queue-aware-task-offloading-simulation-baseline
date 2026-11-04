#!/usr/bin/env python3
"""Reproducible small DQN training/frozen-evaluation software validation pilot."""
import csv, hashlib, json, os, re, shutil, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TRAIN_SEEDS=[11,29,47]
EVAL_SEEDS=[8128,4401]

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read_json(p): return json.loads(p.read_text())
def main():
    base=ROOT/'results/experiments'; expid=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_dqn_pilot')
    out=base/expid
    if out.exists(): raise SystemExit(f"refusing to overwrite {out}")
    (out/'config').mkdir(parents=True);(out/'runs').mkdir();(out/'checkpoints').mkdir()
    shutil.copy2(ROOT/'configs/dqn/training.properties',out/'config/training.properties')
    shutil.copy2(ROOT/'configs/dqn/evaluation.properties',out/'config/evaluation.properties')
    training_cfg=out/'config/training.properties';eval_cfg=out/'config/evaluation.properties';checkpoint=out/'checkpoints/dqn_checkpoint.bin'
    manifest={'experiment_id':expid,'created_utc':datetime.now(timezone.utc).isoformat(),'profile':'paper-aligned-baseline','devices':10,'edcs':4,'target':'EDGE_DC_ONLY','duration_seconds':5,'workload':'per-task-validation-64-tasks-single-source','training_seeds':TRAIN_SEEDS,'evaluation_seeds':EVAL_SEEDS,'methods':['trade-off','queue-aware','dqn'],'status':'running','runs':[],'training_checkpoint':str(checkpoint.relative_to(out))}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    env=os.environ.copy();env['PAPER_PER_TASK_VALIDATION_WORKLOAD']='1';env['PAPER_TASK_EVENT_TRACE']='1'
    training=[];evaluation=[];failed=[]
    def execute(method,seed,mode=None):
        nonlocal manifest
        runroot=out/'runs';env_run=env.copy()
        if method=='dqn':
            env_run.update({'DQN_CONFIG':str(training_cfg if mode=='train' else eval_cfg),'DQN_CHECKPOINT':str(checkpoint),'DQN_MODE':mode or 'train'})
        cmd=[str(ROOT/'run.sh'),'--profile','paper-aligned-baseline','--method',method,'--devices','10','--duration-seconds','5','--destination-config','EDGE_DC_ONLY','--seed',str(seed)]
        env_run['RUNS_ROOT']=str(runroot)
        print(f"\n[RUN] method={method} mode={mode or ''} seed={seed} duration=5s",flush=True)
        proc=subprocess.Popen(cmd,cwd=ROOT,env=env_run,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        lines=[]
        for line in proc.stdout:
            print(line,end='',flush=True);lines.append(line)
        rc=proc.wait();text=''.join(lines);match=re.findall(r'RUN_DIR=(.+)',text)
        run=Path(match[-1].strip()) if match else None
        item={'method':method,'mode':mode,'seed':seed,'return_code':rc,'run_dir':str(run.relative_to(out)) if run and run.is_relative_to(out) else str(run) if run else None}
        if run and (run/'manifest.json').is_file():
            m=read_json(run/'manifest.json');item.update({'status':m.get('status'),'validation_errors':m.get('validation_errors',[]),'task_accounting':m.get('task_accounting'),'metrics':m.get('metrics'),'destination_counts':m.get('destination_counts'),'per_task_lifecycle_accounting':m.get('per_task_lifecycle_accounting'),'decision_count':m.get('per_task_decision_count')})
            item['pair_signature']={k:m.get(k) for k in ('devices','duration_seconds','destination_config','random_seed','simulator_revision','configuration_sha256','workload_override')}
            if method=='dqn':
                console=(run/'raw/simulator-console.log').read_text(errors='replace')
                stats=re.findall(r'DQN_EPISODE_STATS mode=(\S+) decisions=(\d+) replay_size=(\d+) updates=(\d+) loss=([^ ]+) epsilon=([^\s]+)',console)
                if stats:
                    z=stats[-1];item['dqn_stats']={'mode':z[0],'decisions':int(z[1]),'replay_size':int(z[2]),'updates':int(z[3]),'loss':float(z[4]),'epsilon':float(z[5])}
                transition=run/'raw/dqn_transitions.csv'
                if transition.is_file():
                    with transition.open(newline='') as f:
                        rows=list(csv.DictReader(f))
                    item['episode_reward']=sum(float(r['reward']) for r in rows if r.get('event_name')=='TERMINAL_REWARD' and r.get('reward'))
        else:item.update({'status':'failed','validation_errors':['missing run manifest']})
        manifest['runs'].append(item)
        if item['status']!='completed' or rc!=0:failed.append(item)
        return item
    try:
        for ep,seed in enumerate(TRAIN_SEEDS,1):
            item=execute('dqn',seed,'train');item['episode']=ep;training.append(item)
            if not checkpoint.is_file(): print('TRAINING_CHECKPOINT_NOT_YET_CREATED',flush=True)
        before=sha(checkpoint) if checkpoint.is_file() else None
        for seed in EVAL_SEEDS:
            for method in ('trade-off','queue-aware','dqn'):
                item=execute(method,seed,'eval' if method=='dqn' else None);evaluation.append(item)
        after=sha(checkpoint) if checkpoint.is_file() else None
        manifest['checkpoint_sha256_before_eval']=before;manifest['checkpoint_sha256_after_eval']=after
        manifest['frozen_evaluation_checkpoint_unchanged']=before is not None and before==after
    except Exception as exc:
        manifest['runner_exception']=repr(exc);failed.append({'status':'runner_exception','error':repr(exc)})
    write_rows(out/'training_metrics.csv',training)
    write_rows(out/'evaluation_comparison.csv',evaluation)
    pairing=[]
    for seed in EVAL_SEEDS:
        group=[r for r in evaluation if r['seed']==seed]
        signatures=[r.get('pair_signature') for r in group]
        valid=len(group)==3 and all(s==signatures[0] for s in signatures)
        pairing.append({'seed':seed,'methods':[r['method'] for r in group],'same_simulator_workload_config':valid})
    manifest['paired_evaluation_validation']=pairing
    manifest['status']='completed' if not failed and len(evaluation)==6 and manifest.get('frozen_evaluation_checkpoint_unchanged') and all(p['same_simulator_workload_config'] for p in pairing) else 'incomplete_or_failed'
    manifest['failed_runs']=failed
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(f"\nEXPERIMENT_DIR={out}\nCHECKPOINT={checkpoint}\nTRAINING_METRICS={out/'training_metrics.csv'}\nEVALUATION_COMPARISON={out/'evaluation_comparison.csv'}\nSTATUS={manifest['status']}")
    return 0 if manifest['status']=='completed' else 1

def write_rows(path,items):
    fields=['episode','method','mode','seed','status','generated','completed','failed','pending','completion_rate','episode_reward','energy_wh','average_total_delay_seconds','average_waiting_seconds','mean_queue_estimate','destination_counts','decision_count','lifecycle_accounting','loss','replay_size','updates','epsilon','validation_errors']
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for x in items:
            m=x.get('metrics') or {};a=x.get('task_accounting') or {};q=m.get('queue_aware_metrics') or {}
            w.writerow({'episode':x.get('episode',''),'method':x['method'],'mode':x.get('mode') or 'baseline','seed':x['seed'],'status':x.get('status'),
             'generated':a.get('generated_tasks',m.get('generated_tasks')),'completed':a.get('completed_tasks',m.get('completed_tasks')),'failed':a.get('terminally_failed_tasks',m.get('failed_tasks')),'pending':a.get('pending_tasks',m.get('pending_tasks')),
             'completion_rate':m.get('task_success_rate'),'episode_reward':x.get('episode_reward'),'energy_wh':m.get('energy_consumption'),'average_total_delay_seconds':m.get('average_completed_task_total_delay_seconds'),'average_waiting_seconds':m.get('average_completed_task_waiting_time_seconds'),
             'mean_queue_estimate':q.get('selected_mean_queue_wait_estimate_seconds'),'destination_counts':json.dumps(x.get('destination_counts')),'decision_count':x.get('decision_count'),'lifecycle_accounting':json.dumps(x.get('per_task_lifecycle_accounting')),'loss':(x.get('dqn_stats') or {}).get('loss'),'replay_size':(x.get('dqn_stats') or {}).get('replay_size'),'updates':(x.get('dqn_stats') or {}).get('updates'),'epsilon':(x.get('dqn_stats') or {}).get('epsilon'),'validation_errors':json.dumps(x.get('validation_errors',[]))})
if __name__=='__main__':sys.exit(main())
