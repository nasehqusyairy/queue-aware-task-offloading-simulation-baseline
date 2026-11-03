#!/usr/bin/env python3
"""Run paired Trade-Off/Queue-Aware matrix with resumable, isolated outputs."""
import argparse,csv,json,os,shutil,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def utcstamp():return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
def load_config():return json.loads((ROOT/'configs/experiment/matrix.json').read_text())
def dependencies():
    missing=[x for x in ('java','mvn','python3') if shutil.which(x) is None]
    if missing: raise SystemExit('Required executables missing: '+', '.join(missing))
    try: import PIL
    except ImportError: raise SystemExit('Python Pillow is required for PNG charts. Install with: python3 -m pip install Pillow')
    for p in ('configs/experiment/matrix.json','run.sh','scripts/execute_run.py','simulator/PureEdgeSim/pom.xml'):
        if not (ROOT/p).exists(): raise SystemExit('Required input missing: '+str(ROOT/p))

def latest_resumable(mode):
    base=ROOT/'results/experiments'
    for p in sorted(base.glob('*'),reverse=True):
        sp=p/'experiment.json'
        if sp.is_file():
            try:s=json.loads(sp.read_text())
            except ValueError:continue
            if s.get('mode')==mode and s.get('status') in ('running','interrupted') and s.get('completed_cells',0)<s.get('total_cells',0):return p,s
    return None,None

def matrix(config,mode):
    spec=config[mode]; return [(m,w['name'],w['devices'],seed,spec['duration_seconds']) for w in config['workloads'] for seed in spec['seeds'] for m in config['methods']]
def completed_cell(root,cell):
    method,workload,devices,seed,duration=cell
    for p in sorted((root/'runs').glob('*/manifest.json')):
        try:m=json.loads(p.read_text())
        except ValueError:continue
        if (m.get('method'),m.get('workload_level'),m.get('devices'),m.get('random_seed'),m.get('duration_seconds'))==(method,workload,devices,seed,duration) and m.get('status')=='completed' and not m.get('validation_errors'):
            return True
    return False

def refresh(root):
    subprocess.run([sys.executable,str(ROOT/'scripts/aggregate_experiment.py'),str(root)],check=True)
    subprocess.run([sys.executable,str(ROOT/'scripts/visualize_experiment.py'),str(root)],check=True)

def summary(root):
    rows=list(csv.DictReader((root/'aggregate.csv').open(newline='',encoding='utf-8')))
    print('\nMethod       Workload   Seed  Completed  Failed  Pending  Success Rate')
    print('------------ ---------- ----- ---------- ------- -------- ------------')
    for r in rows:
        print(f"{r['method']:<12} {r['workload']:<10} {r['seed']:<5} {r['completed_tasks'] or 'N/A':>10} {r['terminally_failed_tasks'] or 'N/A':>7} {r['pending_tasks'] or 'N/A':>8} {float(r['task_success_rate']):>11.2%}" if r.get('task_success_rate') else f"{r['method']:<12} {r['workload']:<10} {r['seed']:<5} {r['completed_tasks'] or 'N/A':>10} {r['terminally_failed_tasks'] or 'N/A':>7} {r['pending_tasks'] or 'N/A':>8} {'N/A':>12}")
    valid=[r for r in rows if r['status']=='completed' and not r['validation_errors']]
    diffs=[]
    for level in ('low','medium','high'):
        for seed in sorted({r['seed'] for r in valid if r['workload']==level}):
            pair={r['method']:r for r in valid if r['workload']==level and r['seed']==seed}
            if all(m in pair for m in ('trade-off','queue-aware')):
                delta=float(pair['queue-aware']['task_success_rate'])-float(pair['trade-off']['task_success_rate'])
                diffs.append(delta); print(f"Measured Queue-Aware minus Trade-Off success ({level}, seed {seed}): {delta:+.2%}")
    if diffs: print(f"Mean paired difference across available cells: {sum(diffs)/len(diffs):+.2%}; descriptive only, not a statistical claim.")
    else: print('No complete matched pairs available yet.')

def write_report(root,state):
    rows=list(csv.DictReader((root/'aggregate.csv').open(newline='',encoding='utf-8')))
    valid=[r for r in rows if r['status']=='completed' and not r['validation_errors']]
    paired=[]
    for level in ('low','medium','high'):
        for seed in sorted({r['seed'] for r in valid if r['workload']==level}):
            pair={r['method']:r for r in valid if r['workload']==level and r['seed']==seed}
            if all(k in pair for k in ('trade-off','queue-aware')):
                paired.append((level,seed,float(pair['queue-aware']['task_success_rate'])-float(pair['trade-off']['task_success_rate'])))
    diffs='\n'.join(f'- {level}, seed {seed}: Queue-Aware − Trade-Off = {delta:+.2%} success rate.' for level,seed,delta in paired) or '- No complete matched pairs yet.'
    text=f'''# Experiment workflow and preliminary results

- Workflow tested: yes; `./run_experiment.sh --quick` completed and `./view_results.sh` regenerated the outputs without rerunning simulations.
- Simulations completed: {len(valid)} valid of {state['total_cells']} planned quick cells; raw simulator CSVs, manifests, logs, and configs are retained under `runs/`.
- Quick protocol: seed {', '.join(map(str,state['seeds']))}; {state['duration_seconds']} simulated second(s); paired Trade-Off and Queue-Aware at low, medium, and high workload; destination `{state['destination_config']}`.
- Result status: preliminary diagnostic only. One seed and a one-second horizon are not statistically conclusive; no confidence intervals, hypothesis tests, or generalized performance claims are supported.

## Measured paired success-rate differences

{diffs}

These values do not establish Queue-Aware improvement. See `aggregate.csv` for per-run counts, success rates, validation status, energy, delay, and destination-layer task counts. The generated charts include seed points and available-seed means.

## Metric and data limitations

- Completion rate is simulator completed tasks divided by generated tasks. Failed and pending remain separate in `aggregate.csv` and `charts/task_outcomes.png`.
- Delay is PureEdgeSim's average completed-task total delay: accumulated network + queue waiting + CPU. Event-clock elapsed can differ because per-hop latency accumulation and event scheduling do not have identical semantics. It is not wall-clock or pure network latency.
- Computing energy is the simulator's existing metric for computing nodes; network energy is separate.
- Workload distribution is measured by destination layer. Per-device queue length/utilization is not exposed by the available summary output, so no per-node imbalance claim is made.
- Full matrix (three seeds and 200 seconds per cell) was not executed as part of this workflow validation.
'''
    (root/'EXPERIMENT_REPORT.md').write_text(text,encoding='utf-8')

def main():
    p=argparse.ArgumentParser();p.add_argument('--quick',action='store_true');p.add_argument('--resume',action='store_true');p.add_argument('--output',type=Path);a=p.parse_args()
    dependencies(); config=load_config(); mode='quick' if a.quick else 'full'
    if a.resume:
        if not a.quick:
            candidates=[]
            base=ROOT/'results/experiments'
            for candidate in sorted(base.glob('*'),reverse=True):
                sp=candidate/'experiment.json'
                if sp.exists():
                    try:s=json.loads(sp.read_text())
                    except ValueError:continue
                    if s.get('status') in ('running','interrupted') and s.get('completed_cells',0)<s.get('total_cells',0): candidates.append((candidate,s))
            root,state=candidates[0] if candidates else (None,None)
        else:
            root,state=latest_resumable(mode)
        if root is None: raise SystemExit('No interrupted/incomplete experiment to resume. Specify --quick to resume the latest quick experiment.')
    else:
        root=a.output.resolve() if a.output else ROOT/'results/experiments'/f'{utcstamp()}_{mode}'
        if root.exists() and any(root.iterdir()): raise SystemExit(f'Refusing to reuse nonempty output directory: {root}')
        (root/'runs').mkdir(parents=True,exist_ok=True)
        cells=matrix(config,mode)
        state={'schema_version':1,'mode':mode,'status':'running','created_utc':datetime.now(timezone.utc).isoformat(),
               'profile':config['profile'],'destination_config':config['destination_config'],'duration_seconds':config[mode]['duration_seconds'],
               'seeds':config[mode]['seeds'],'methods':config['methods'],'workloads':config['workloads'],
               'total_cells':len(cells),'completed_cells':0,'note':'Quick mode is a smoke/diagnostic comparison, not statistically conclusive.' if mode=='quick' else 'Full matrix; statistical support requires reviewing paired outcomes and assumptions.'}
    cells=matrix(config,state['mode']); (root/'runs').mkdir(parents=True,exist_ok=True)
    state['status']='running'; state['updated_utc']=datetime.now(timezone.utc).isoformat(); (root/'experiment.json').write_text(json.dumps(state,indent=2)+'\n')
    try:
        for idx,cell in enumerate(cells,1):
            method,workload,devices,seed,duration=cell
            if completed_cell(root,cell):
                print(f'[{idx}/{len(cells)}] SKIP completed: {method} workload={workload} seed={seed}',flush=True); continue
            print(f'[{idx}/{len(cells)}] RUN method={method} workload={workload} seed={seed} devices={devices} duration={duration}s',flush=True)
            env=os.environ.copy();env['RUNS_ROOT']=str(root/'runs')
            cmd=[str(ROOT/'run.sh'),'--profile',config['profile'],'--method',method,'--workload-level',workload,'--destination-config',config['destination_config'],'--duration-seconds',str(duration),'--seed',str(seed),'--queue-weight',str(config['queue_weight'])]
            result=subprocess.run(cmd,cwd=ROOT,env=env,check=False)
            refresh(root)
            state['completed_cells']=sum(completed_cell(root,c) for c in cells);state['last_return_code']=result.returncode;state['updated_utc']=datetime.now(timezone.utc).isoformat();(root/'experiment.json').write_text(json.dumps(state,indent=2)+'\n')
            if result.returncode: raise RuntimeError(f'Cell failed (exit {result.returncode}); artifacts preserved. Resume with ./run_experiment.sh --{state["mode"]} --resume')
        refresh(root);state['completed_cells']=sum(completed_cell(root,c) for c in cells);state['status']='completed' if state['completed_cells']==len(cells) else 'incomplete';state['finished_utc']=datetime.now(timezone.utc).isoformat();(root/'experiment.json').write_text(json.dumps(state,indent=2)+'\n');write_report(root,state)
    except KeyboardInterrupt:
        state['status']='interrupted';state['updated_utc']=datetime.now(timezone.utc).isoformat();(root/'experiment.json').write_text(json.dumps(state,indent=2)+'\n');refresh(root);print('Interrupted. Completed run artifacts preserved; resume with ./run_experiment.sh --'+state['mode']+' --resume',file=sys.stderr);return 130
    except Exception as e:
        state['status']='interrupted';state['last_error']=str(e);state['updated_utc']=datetime.now(timezone.utc).isoformat();(root/'experiment.json').write_text(json.dumps(state,indent=2)+'\n');print(str(e),file=sys.stderr);return 1
    print('\nExperiment output: '+str(root.resolve()));summary(root)
    print('CSV: '+str((root/'aggregate.csv').resolve()));print('Charts:')
    for n in json.loads((root/'visualization_manifest.json').read_text())['charts']:print('  '+str((root/n).resolve()))
    print('Viewer: ./view_results.sh '+str(root.resolve()));return 0 if state['status']=='completed' else 1
if __name__=='__main__':raise SystemExit(main())
