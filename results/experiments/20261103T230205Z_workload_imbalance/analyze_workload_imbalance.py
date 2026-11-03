#!/usr/bin/env python3
"""Validate virtual-ingress workload and analyze per-EDC paired outcomes."""
import argparse,csv,glob,json,math,itertools,collections
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

EXP=Path(__file__).resolve().parent
CFG=json.loads((EXP/'workload_profiles.json').read_text())
SEEDS=CFG['seeds']; CONDITIONS=list(CFG['home_workload_matrices_users_by_edc_app'])
METHODS=CFG['methods']; NODES=range(1,5); TCRIT=2.7764451051977987

def rows(path):
    with open(path,newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def write(name,data):
    if data:
        with (EXP/name).open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
def find_run(condition,method,weight,seed):
    root=EXP/'runs'/condition
    found=[]
    for p in root.glob('*/manifest.json') if root.exists() else []:
        m=json.loads(p.read_text())
        if m.get('method')==method and int(m.get('random_seed') or -999)==seed and m.get('home_workload_condition')==condition:
            if method!='queue-aware' or float(m.get('queue_penalty_weight',-1))==weight:found.append((p.parent,m))
    if len(found)!=1:raise ValueError(f'{condition}/{method}/{weight}/{seed}: expected 1 manifest, got {len(found)}')
    run,m=found[0];met=json.loads((run/'metrics.json').read_text())
    if m.get('status')!='completed' or m.get('process_exit_code')!=0 or m.get('validation_errors') or met.get('validation_errors') or met.get('metric_validation_errors'):
        raise ValueError(f'invalid run {run}')
    for f in ['raw/home_workload.csv','raw/destinations.csv','raw/task_event_trace.csv','raw/edc_node_state.csv']:
        if not (run/f).is_file():raise ValueError(f'missing {f}: {run}')
    if method=='queue-aware' and not (run/'raw/queue_decisions.csv').is_file():raise ValueError(f'missing queue audit {run}')
    return run,m,met
def mean(v):return sum(v)/len(v) if v else None
def sd(v):return math.sqrt(sum((x-mean(v))**2 for x in v)/(len(v)-1)) if len(v)>1 else None
def signflip(v):
    obs=abs(mean(v)); vals=[abs(mean([x*s for x,s in zip(v,ss)])) for ss in itertools.product((-1,1),repeat=len(v))]
    return sum(x>=obs-1e-15 for x in vals)/len(vals)
def allocation(run):
    return {int(r['task_id']):r for r in rows(run/'raw/destinations.csv') if r['record_type']=='DECISION'}
def terminal_trace(run):
    out={}
    for r in rows(run/'raw/task_event_trace.csv'):
        if r['event_name'] in ('TASK_COMPLETED','TASK_FAILED'):
            out[int(r['task_id'])]=r
    return out

parser=argparse.ArgumentParser();parser.add_argument('--pilot',action='store_true');args=parser.parse_args()
seeds=[1] if args.pilot else SEEDS
run_rows=[];edc_rows=[];pairs=[];queue_rows=[];checks=[]
all_metrics={}
for cond in CONDITIONS:
 for seed in seeds:
  base=None
  for method_obj in METHODS:
   method=method_obj['name'];weight=method_obj['queue_weight']
   run,m,met=find_run(cond,method,weight,seed)
   hrows=rows(run/'raw/home_workload.csv'); homes={int(r['task_id']):r for r in hrows}
   dest=allocation(run); terminals=terminal_trace(run)
   if len(homes)!=CFG['total_tasks_expected'] or len(dest)!=CFG['total_tasks_expected']:
    raise ValueError(f'task count mismatch {cond}/{method}/seed{seed}: home={len(homes)} destination={len(dest)}')
   if set(homes)!=set(dest):raise ValueError('home audit and destination task IDs differ')
   for tid,a in homes.items():
    if int(a['home_edc_id']) not in NODES:raise ValueError('invalid virtual home EDC id')
   home_tasks=collections.Counter(int(r['home_edc_id']) for r in hrows)
   home_work=collections.Counter()
   for r in hrows:home_work[int(r['home_edc_id'])]+=int(float(r['task_length_mi']))
   actual_dest=collections.Counter(int(r['destination_id']) for r in dest.values() if r['destination_type']=='EDGE_DATACENTER')
   statuses=collections.Counter()
   for t in terminals.values():statuses[t['event_name']]+=1
   node_states=rows(run/'raw/edc_node_state.csv')
   finals={int(r['node_id']):r for r in node_states if r['event']=='HORIZON_FINAL'}
   if len(finals)!=4:raise ValueError(f'expected four final EDC state records, got {len(finals)}')
   qdata=rows(run/'raw/queue_decisions.csv') if method=='queue-aware' else []
   candidate_ids=sorted({int(q['candidate_id']) for q in qdata})
   qby=collections.defaultdict(list)
   for q in qdata:qby[int(q['candidate_id'])].append(q)
   q_decisions=collections.defaultdict(list)
   for q in qdata:q_decisions[int(q['task_id'])].append(q)
   q_decision_rows=[v[0] for v in q_decisions.values()]
   for dc in NODES:
    assigned=[tid for tid,r in dest.items() if r['destination_type']=='EDGE_DATACENTER' and int(r['destination_id'])==dc]
    terminal=[terminals[tid] for tid in assigned if tid in terminals]
    complete=[t for t in terminal if t['event_name']=='TASK_COMPLETED']
    failed=[t for t in terminal if t['event_name']=='TASK_FAILED']
    actualwait=[float(t['queue_wait_seconds']) for t in complete if t.get('queue_wait_seconds') not in ('',None)]
    ss=[r for r in node_states if int(r['node_id'])==dc]
    qs=qby[dc]
    edc_rows.append({'condition':cond,'method':method,'lambda':weight if method=='queue-aware' else '', 'seed':seed,'edc_id':dc,
      'capacity_cores':10,'mips_per_core':40000,'ram_mb':16000,'ingress_offered_tasks':home_tasks[dc],
      'ingress_offered_work_mi':home_work[dc],'destination_assignments':len(assigned),
      'completed_at_destination':len(complete),'failed_at_destination':len(failed),
      'pending_at_destination':len(assigned)-len(complete)-len(failed),
      'actual_completed_waiting_mean_s':mean(actualwait),
      'horizon_active_task_count':int(float(finals[dc]['active_task_count'])),
      'horizon_waiting_queue_length':int(float(finals[dc]['waiting_queue_length'])),
      'direct_horizon_cpu_utilization_percent':float(finals[dc]['average_cpu_utilization_percent']),
      'direct_horizon_current_cpu_utilization_percent':float(finals[dc]['current_cpu_utilization_percent']),
      'direct_computing_energy_wh':float(finals[dc]['computing_energy_wh']),
      'node_state_observations':len(ss),
      'queue_estimate_candidate_observations':len(qs) if method=='queue-aware' else '',
      'queue_estimate_min_s':min((float(q['queue_wait_estimate_seconds']) for q in qs if q['queue_wait_estimate_seconds']),default='') if method=='queue-aware' else '',
      'queue_estimate_max_s':max((float(q['queue_wait_estimate_seconds']) for q in qs if q['queue_wait_estimate_seconds']),default='') if method=='queue-aware' else '',
      'queue_estimate_nonzero_n':sum(float(q['queue_wait_estimate_seconds'])>0 for q in qs if q['queue_wait_estimate_seconds']) if method=='queue-aware' else '',
      'queue_estimate_n':sum(bool(q['queue_wait_estimate_seconds']) for q in qs) if method=='queue-aware' else ''})
   record={'condition':cond,'method':method,'lambda':weight if method=='queue-aware' else '', 'seed':seed,'run_id':m['run_id'],
      'generated':met['generated_tasks'],'completed':met['completed_tasks'],'failed':met['terminally_failed_tasks'],'pending':met['pending_tasks'],
      'completion_rate':met['task_success_rate'],'energy_wh':met['energy_consumption'],
      'average_total_delay_s':met['average_completed_task_total_delay_seconds'],
      'actual_completed_waiting_s':met['average_completed_task_waiting_time_seconds'],
      'ingress_offered_tasks_total':len(hrows),'ingress_offered_work_mi_total':sum(int(float(r['task_length_mi'])) for r in hrows),
      'edc1_destination_assignments':actual_dest[1],'edc2_destination_assignments':actual_dest[2],
      'edc3_destination_assignments':actual_dest[3],'edc4_destination_assignments':actual_dest[4],
      'policy_candidate_ids_seen':';'.join(map(str,candidate_ids)) if method=='queue-aware' else '',
      'ranking_changed_decisions':sum(q['ranking_changed'].lower()=='true' for q in q_decision_rows) if method=='queue-aware' else '',
      'selected_destination_changed_decisions':sum(q['selected_destination_changed'].lower()=='true' for q in q_decision_rows) if method=='queue-aware' else '',
      'home_to_destination_cross_route_tasks':sum(int(homes[tid]['home_edc_id'])!=int(dest[tid]['destination_id']) for tid in dest if dest[tid]['destination_type']=='EDGE_DATACENTER'),
      'home_task_counts':'|'.join(str(home_tasks[i]) for i in NODES),
      'home_work_mi':'|'.join(str(home_work[i]) for i in NODES)}
   run_rows.append(record);all_metrics[(cond,method,weight,seed)]=(run,m,met,homes,dest,terminals)
   if method=='queue-aware':
    for dc in NODES:
     ss=qby[dc];est=[float(q['queue_wait_estimate_seconds']) for q in ss if q['queue_wait_estimate_seconds']]
     queue_rows.append({'condition':cond,'lambda':weight,'seed':seed,'edc_id':dc,'candidate_observations':len(ss),
      'queue_estimate_min_s':min(est) if est else '', 'queue_estimate_max_s':max(est) if est else '',
      'queue_estimate_nonzero_n':sum(x>0 for x in est),'active_task_count_mean':mean([float(q['active_task_count']) for q in ss if q['active_task_count']]),
      'waiting_queue_length_mean':mean([float(q['waiting_queue_length']) for q in ss if q['waiting_queue_length']]),
      'queue_estimate_mean_s':mean(est)})
   if method=='trade-off': base=(run,m,met,homes,dest,terminals)
  # paired config and offered-work verification per condition/seed
  if base:
   bm=base[1];bh=base[3];bd=base[4]
   for mo in METHODS[1:]:
    qrun,qm,qmet,qh,qd,qt=all_metrics[(cond,mo['name'],mo['queue_weight'],seed)]
    config_fields=['configuration_sha256','simulator_properties','profile','devices','duration_seconds','destination_config','simulator_revision','random_seed']
    mismatch=[f for f in config_fields if bm.get(f)!=qm.get(f)]
    paired_task_source_same=all(bh[tid]['source_id']==qh[tid]['source_id'] and bh[tid]['application_id']==qh[tid]['application_id'] for tid in bh)
    paired_home_matrix_same=all(bh[tid]['home_edc_id']==qh[tid]['home_edc_id'] and float(bh[tid]['task_length_mi'])==float(qh[tid]['task_length_mi']) for tid in bh)
    paired_source_position_same=all(bd[tid]['source_id']==qd[tid]['source_id'] and bd[tid]['source_x']==qd[tid]['source_x'] and bd[tid]['source_y']==qd[tid]['source_y'] for tid in bd)
    pairs.append({'condition':cond,'seed':seed,'queue_lambda':mo['queue_weight'],'config_valid':not mismatch,'config_mismatches':';'.join(mismatch),
      'same_generated_task_sources_apps':paired_task_source_same,'same_virtual_ingress_and_task_lengths':paired_home_matrix_same,
      'same_task_source_positions':paired_source_position_same,'tradeoff_generated':base[2]['generated_tasks'],'queue_aware_generated':qmet['generated_tasks'],
      'tradeoff_completion':base[2]['task_success_rate'],'queue_aware_completion':qmet['task_success_rate'],
      'completion_rate_diff':qmet['task_success_rate']-base[2]['task_success_rate'],
      'tradeoff_energy_wh':base[2]['energy_consumption'],'queue_aware_energy_wh':qmet['energy_consumption'],
      'energy_diff_wh':qmet['energy_consumption']-base[2]['energy_consumption'],
      'tradeoff_total_delay_s':base[2]['average_completed_task_total_delay_seconds'],'queue_aware_total_delay_s':qmet['average_completed_task_total_delay_seconds'],
      'total_delay_diff_s':qmet['average_completed_task_total_delay_seconds']-base[2]['average_completed_task_total_delay_seconds'],
      'tradeoff_waiting_s':base[2]['average_completed_task_waiting_time_seconds'],'queue_aware_waiting_s':qmet['average_completed_task_waiting_time_seconds'],
      'actual_waiting_diff_s':qmet['average_completed_task_waiting_time_seconds']-base[2]['average_completed_task_waiting_time_seconds'],
      'tradeoff_completed_diff':qmet['completed_tasks']-base[2]['completed_tasks'],
      'tradeoff_failed_diff':qmet['terminally_failed_tasks']-base[2]['terminally_failed_tasks'],
      'tradeoff_pending_diff':qmet['pending_tasks']-base[2]['pending_tasks']})

write('run_level.csv',run_rows);write('edc_metrics_by_run.csv',edc_rows);write('paired_by_seed_condition.csv',pairs);write('queue_metrics_by_edc.csv',queue_rows)
def grouped(rows_,keys):
    d=collections.defaultdict(list)
    for r in rows_:d[tuple(r[k] for k in keys)].append(r)
    return d
summary_rows=[]
for key,group in grouped(run_rows,['condition','method','lambda']).items():
    obj=dict(zip(['condition','method','lambda'],key));obj['n_seeds']=len(group)
    for metric in ['generated','completed','failed','pending','completion_rate','energy_wh','average_total_delay_s','actual_completed_waiting_s','edc1_destination_assignments','edc2_destination_assignments','edc3_destination_assignments','edc4_destination_assignments','ranking_changed_decisions','selected_destination_changed_decisions']:
        vals=[float(r[metric]) for r in group if r[metric] not in ('',None)]
        obj[f'{metric}_mean']=mean(vals);obj[f'{metric}_sd']=sd(vals)
    summary_rows.append(obj)
write('aggregate_summary.csv',summary_rows)
edc_summary=[]
for key,group in grouped(edc_rows,['condition','method','lambda','edc_id']).items():
    obj=dict(zip(['condition','method','lambda','edc_id'],key));obj['n_seeds']=len(group)
    for metric in ['ingress_offered_tasks','ingress_offered_work_mi','destination_assignments','completed_at_destination','failed_at_destination','pending_at_destination','actual_completed_waiting_mean_s','horizon_active_task_count','horizon_waiting_queue_length','direct_horizon_cpu_utilization_percent','direct_horizon_current_cpu_utilization_percent','direct_computing_energy_wh','queue_estimate_min_s','queue_estimate_max_s','queue_estimate_nonzero_n','queue_estimate_n']:
        vals=[float(r[metric]) for r in group if r[metric] not in ('',None)]
        obj[f'{metric}_mean']=mean(vals);obj[f'{metric}_sd']=sd(vals)
    edc_summary.append(obj)
write('edc_summary_across_seeds.csv',edc_summary)
# Validate expected totals and workload-class separation before the matrix gate.
home_summary=[]
for cond in CONDITIONS:
   rr=[r for r in run_rows if r['condition']==cond]
   expected=rr[0]
   offered_work=[int(x) for x in expected['home_work_mi'].split('|')]
   shares=[x/sum(offered_work) for x in offered_work]
   home_summary.append({'condition':cond,'generated_tasks':expected['generated'],'offered_work_mi_total':expected['ingress_offered_work_mi_total'],
      **{f'edc{i}_ingress_work_mi':offered_work[i-1] for i in NODES},
      **{f'edc{i}_work_share':shares[i-1] for i in NODES},
      'workload_cv':(math.sqrt(sum((x-mean(offered_work))**2 for x in offered_work)/len(offered_work))/mean(offered_work)),'home_task_counts':expected['home_task_counts']})
write('home_workload_summary.csv',home_summary)
expected_shares={'balanced':[.25]*4,'moderate':[.4,.3,.2,.1],'severe':[.7,.15,.1,.05]}
total_ok=all(r['generated']==CFG['total_tasks_expected'] and int(r['ingress_offered_work_mi_total'])==CFG['total_work_mi_expected'] for r in run_rows)
homeok=True
for r in home_summary:
    target=expected_shares[r['condition']]
    observed=[r[f'edc{i}_work_share'] for i in NODES]
    homeok &= max(abs(a-b) for a,b in zip(target,observed))<0.01
pair_ok=all(x['config_valid'] and x['same_generated_task_sources_apps'] and x['same_virtual_ingress_and_task_lengths'] and x['same_task_source_positions'] for x in pairs)
candidate_ok=all(set(r['policy_candidate_ids_seen'].split(';'))=={'1','2','3','4'} for r in run_rows if r['method']=='queue-aware')
state_ok=all(sum(1 for e in edc_rows if e['condition']==r['condition'] and e['method']==r['method'] and e['seed']==r['seed'] and e['lambda']==r['lambda'])==4 for r in run_rows)
pilot_valid=total_ok and homeok and pair_ok and candidate_ok and state_ok
validation={'pilot_only':args.pilot,'runs_analyzed':len(run_rows),'paired_comparisons':len(pairs),'total_task_work_invariant':total_ok,'workload_imbalance_targets_valid':homeok,
 'paired_method_configuration_and_input_valid':pair_ok,'all_four_edcs_seen_as_queueaware_candidates':candidate_ok,'per_edc_final_state_present_all_runs':state_ok,
 'pilot_valid':pilot_valid,'expected_home_work_shares':expected_shares,'observed_home_workloads':home_summary}
(EXP/'analysis_validation.json').write_text(json.dumps(validation,indent=2)+'\n')
if not args.pilot:
    metric_specs=['completion_rate','energy_wh','total_delay_diff_s','actual_waiting_diff_s','tradeoff_completed_diff','tradeoff_failed_diff','tradeoff_pending_diff']
    statrows=[]
    for cond in CONDITIONS:
      for weight in (.5,1.0):
       pp=[p for p in pairs if p['condition']==cond and p['queue_lambda']==weight]
       for key in metric_specs:
        diffkey={'completion_rate':'completion_rate_diff','energy_wh':'energy_diff_wh','total_delay_diff_s':'total_delay_diff_s','actual_waiting_diff_s':'actual_waiting_diff_s'}.get(key,key)
        ds=[float(p[diffkey]) for p in pp]
        dm=mean(ds);sdiff=sd(ds);half=TCRIT*sdiff/math.sqrt(len(ds)) if len(ds)==5 and sdiff is not None else None
        statrows.append({'condition':cond,'lambda':weight,'metric':key,'n_pairs':len(ds),'paired_mean_difference_QA_minus_TO':dm,'paired_diff_sd':sdiff,
         'paired_95ci_low':dm-half if half is not None else None,'paired_95ci_high':dm+half if half is not None else None,
         'exact_two_sided_signflip_p':signflip(ds) if ds else None,'test':'all 2^5 sign assignments; two-sided mean difference' if len(ds)==5 else 'pilot only; inferential test omitted'})
    write('paired_statistics.csv',statrows)

# Compact PNGs derived from the same simulator outputs.
if not args.pilot:
    chartdir=EXP/'charts';chartdir.mkdir(exist_ok=True)
    def font(size):
        try:return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',size)
        except OSError:return ImageFont.load_default()
    def base(title,subtitle):
        im=Image.new('RGB',(1200,680),'white');dr=ImageDraw.Draw(im);dr.text((45,22),title,font=font(25),fill='#1f2933');dr.text((45,58),subtitle,font=font(14),fill='#53616b');return im,dr
    colors={'trade-off':'#376da8','queue-aware λ=0.5':'#df873a','queue-aware λ=1':'#32936f'}
    labels=[('trade-off',None,'Trade-Off'),('queue-aware',.5,'Queue-Aware λ=0.5'),('queue-aware',1.0,'Queue-Aware λ=1')]
    im,dr=base('Completion rate by ingress workload condition','Mean across five paired seeds; values are simulator successful/generated task rate.')
    xcenters=[300,600,900];ybottom,ytop=555,140
    for tick in range(6):
        y=ybottom-tick*(ybottom-ytop)/5;dr.line((120,y,1090,y),fill='#e2e6e9');dr.text((55,y-8),f'{tick*2}%',font=font(12),fill='#4b5563')
    for ci,cond in enumerate(CONDITIONS):
        for mi,(method,lam,label) in enumerate(labels):
            r=next(x for x in summary_rows if x['condition']==cond and x['method']==method and ((lam is None and x['lambda']=='') or (lam is not None and float(x['lambda'])==lam)))
            val=float(r['completion_rate_mean']);h=val/.10*(ybottom-ytop);x=xcenters[ci]-90+mi*58
            dr.rectangle((x,ybottom-h,x+38,ybottom),fill=list(colors.values())[mi]);dr.text((x-5,ybottom-h-20),f'{val*100:.2f}',font=font(11),fill='#202832')
        dr.text((xcenters[ci]-44,570),cond,font=font(15),fill='#202832')
    for i,(_,_,label) in enumerate(labels):
        x=130+i*270;dr.rectangle((x,95,x+16,111),fill=list(colors.values())[i]);dr.text((x+23,93),label,font=font(13),fill='#202832')
    im.save(chartdir/'completion_by_workload_condition.png')
    im,dr=base('Virtual ingress work shares','Expected offered MI shares per condition; input audit, not execution destination allocation.')
    cols=['#376da8','#61a0a8','#e5ae38','#cc6b49'];maxv=1.0
    for ci,cond in enumerate(CONDITIONS):
        x=210+ci*310;y=540
        sr=next(r for r in home_summary if r['condition']==cond)
        for dc,col in zip(NODES,cols):
            share=float(sr[f'edc{dc}_work_share']);h=share*390;dr.rectangle((x,y-h,x+70,y),fill=col);dr.text((x+7,y-h-20),f'{share*100:.1f}%',font=font(12),fill='#202832');y-=h
        dr.text((x-8,560),cond,font=font(15),fill='#202832')
    for i,col in enumerate(cols):
        x=185+i*190;dr.rectangle((x,100,x+15,115),fill=col);dr.text((x+22,98),f'Home EDC {i+1}',font=font(12),fill='#202832')
    im.save(chartdir/'virtual_ingress_workload_shares.png')

print(json.dumps({'runs':len(run_rows),'pairs':len(pairs),'pilot_valid':pilot_valid,'total_work_constant':total_ok,
 'workload_targets_valid':homeok,'paired_inputs_valid':pair_ok,'all_four_edcs_candidate':candidate_ok,'edc_states_complete':state_ok},indent=2))
