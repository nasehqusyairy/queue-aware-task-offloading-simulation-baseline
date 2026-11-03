#!/usr/bin/env python3
"""Validate paired seed matrix, summarize metrics, exact paired tests and PNG evidence."""
import csv,json,math,itertools,collections
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parent
SEEDS=[1,8128,4401,2026,2027]
METHODS=['trade-off','queue-aware']

def loadcsv(p):
 with p.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def writecsv(p,rows):
 if not rows:return
 with p.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def read_run(method,seed):
 matches=[]
 for mp in (ROOT/'runs').glob('*/manifest.json'):
  m=json.loads(mp.read_text())
  if m.get('method')==method and str(m.get('random_seed'))==str(seed):matches.append((mp.parent,m))
 if len(matches)!=1:raise ValueError(f'{method} seed {seed}: expected one run manifest, found {len(matches)}')
 run,m=matches[0]; met=json.loads((run/'metrics.json').read_text())
 if m.get('status')!='completed' or m.get('process_exit_code')!=0 or m.get('validation_errors') or met.get('validation_errors') or met.get('metric_validation_errors'):
  raise ValueError(f'invalid run output: {run}')
 if not (run/'raw/task_event_trace.csv').is_file() or not (run/'raw/destinations.csv').is_file():raise ValueError(f'missing trace/destination log: {run}')
 dest=collections.Counter(r['destination_id'] for r in loadcsv(run/'raw/destinations.csv') if r['record_type']=='DECISION')
 trace=loadcsv(run/'raw/task_event_trace.csv'); events=collections.Counter(r['event_name'] for r in trace)
 stages=collections.Counter(r['stage'] for r in trace if r['event_name']=='DESTINATION_DECISION')
 qpath=run/'raw/queue_decisions.csv'; qrows=loadcsv(qpath) if qpath.exists() else []
 groups=collections.defaultdict(list)
 for r in qrows:groups[r['task_id']].append(r)
 waits=[float(r['queue_wait_estimate_seconds']) for r in qrows if r['queue_wait_estimate_seconds']!='']
 selected=[r for r in qrows if r['selected'].lower()=='true']
 swaits=[float(r['queue_wait_estimate_seconds']) for r in selected if r['queue_wait_estimate_seconds']!='']
 rec={'method':method,'seed':seed,'run_id':m['run_id'],'status':m['status'],'validation_errors':';'.join(m.get('validation_errors',[])),
      'profile':m['profile'],'devices':m['devices'],'edc_count':m.get('edge_datacenter_count'),'duration_seconds':m['duration_seconds'],'destination_config':m['destination_config'],'simulator_revision':m['simulator_revision'],
      'generated_tasks':met['generated_tasks'],'completed_tasks':met['completed_tasks'],'failed_tasks':met['terminally_failed_tasks'],'pending_tasks':met['pending_tasks'],'completion_rate':met['task_success_rate'],
      'energy_wh':met['energy_consumption'],'average_completed_total_delay_seconds':met['average_completed_task_total_delay_seconds'],'average_completed_waiting_seconds':met['average_completed_task_waiting_time_seconds'],
      'dest_dc1':dest['1'],'dest_dc2':dest['2'],'dest_dc3':dest['3'],'dest_dc4':dest['4'],
      'queue_enter_events':events['QUEUE_ENTER'],'queue_exit_events':events['QUEUE_EXIT'],'policy_selection_decisions':stages['POLICY_SELECTED'],'cached_placement_reuse_events':stages['CACHED_PLACEMENT_REUSED'],
      'queue_candidate_observations':len(qrows) if method=='queue-aware' else None,'queue_estimate_min_seconds':min(waits) if waits else (None if method=='queue-aware' else None),
      'queue_estimate_max_seconds':max(waits) if waits else None,'queue_estimate_nonzero_candidate_observations':sum(x>0 for x in waits) if waits else (0 if method=='queue-aware' else None),
      'selected_queue_observations':len(swaits) if method=='queue-aware' else None,'selected_queue_min_seconds':min(swaits) if swaits else None,'selected_queue_max_seconds':max(swaits) if swaits else None,
      'selected_queue_nonzero_observations':sum(x>0 for x in swaits) if method=='queue-aware' else None,
      'queue_estimate_mean_selected_seconds':sum(swaits)/len(swaits) if swaits else None,
      'queue_estimate_mean_candidate_waiting_length':(sum(int(r['waiting_queue_length']) for r in selected)/len(selected)) if selected else None,
      'ranking_changed_decisions':sum(v[0]['ranking_changed'].lower()=='true' for v in groups.values()) if method=='queue-aware' else None,
      'selected_destination_changed_decisions':sum(v[0]['selected_destination_changed'].lower()=='true' for v in groups.values()) if method=='queue-aware' else None,
      'queue_decision_count':len(groups) if method=='queue-aware' else None,
      'configuration_sha256':m['configuration_sha256'],'simulator_properties':m['simulator_properties'],'queue_penalty_weight':m.get('queue_penalty_weight')}
 if method=='queue-aware' and not qrows:raise ValueError(f'Queue-Aware audit missing: {run}')
 return run,m,met,rec

# Pairing validation and data tables.
allruns={}; raw_rows=[]; paired=[]; decision_effects=[]; statuses=[]
for seed in SEEDS:
 pair={}
 for method in METHODS:
  try:
   run,m,met,rec=read_run(method,seed);pair[method]=(run,m,met,rec);raw_rows.append({k:v for k,v in rec.items() if k not in ('configuration_sha256','simulator_properties')})
   statuses.append({'seed':seed,'method':method,'status':'completed','exit_code':m.get('process_exit_code'),'validation_errors':';'.join(m.get('validation_errors',[])),'run_id':m['run_id']})
  except Exception as e:
   statuses.append({'seed':seed,'method':method,'status':'failed_or_invalid','exit_code':'','validation_errors':str(e),'run_id':''})
 if len(pair)!=2:continue
 t=pair['trade-off'];q=pair['queue-aware'];tm,qm=t[1],q[1]
 same_fields=['profile','devices','duration_seconds','destination_config','simulator_revision','simulator_properties','configuration_sha256','random_seed']
 mismatches=[f for f in same_fields if tm.get(f)!=qm.get(f)]
 valid_pair=not mismatches and tm['random_seed']==seed and qm['random_seed']==seed
 for r in (t[3],q[3]): r['paired_config_valid']=valid_pair; r['pair_mismatches']=';'.join(mismatches)
 paired.append({'seed':seed,'paired_config_valid':valid_pair,'pair_mismatches':';'.join(mismatches),
  'tradeoff_run_id':tm['run_id'],'queue_aware_run_id':qm['run_id'],
  'tradeoff_generated':t[2]['generated_tasks'],'queue_aware_generated':q[2]['generated_tasks'],
  'tradeoff_completed':t[2]['completed_tasks'],'queue_aware_completed':q[2]['completed_tasks'],'completed_diff_QA_minus_TO':q[2]['completed_tasks']-t[2]['completed_tasks'],
  'tradeoff_failed':t[2]['terminally_failed_tasks'],'queue_aware_failed':q[2]['terminally_failed_tasks'],'failed_diff_QA_minus_TO':q[2]['terminally_failed_tasks']-t[2]['terminally_failed_tasks'],
  'tradeoff_pending':t[2]['pending_tasks'],'queue_aware_pending':q[2]['pending_tasks'],'pending_diff_QA_minus_TO':q[2]['pending_tasks']-t[2]['pending_tasks'],
  'tradeoff_completion_rate':t[2]['task_success_rate'],'queue_aware_completion_rate':q[2]['task_success_rate'],'completion_rate_diff_QA_minus_TO':q[2]['task_success_rate']-t[2]['task_success_rate'],'completion_rate_diff_percentage_points':100*(q[2]['task_success_rate']-t[2]['task_success_rate']),
  'tradeoff_energy_wh':t[2]['energy_consumption'],'queue_aware_energy_wh':q[2]['energy_consumption'],'energy_diff_QA_minus_TO_wh':q[2]['energy_consumption']-t[2]['energy_consumption'],
  'tradeoff_delay_seconds':t[2]['average_completed_task_total_delay_seconds'],'queue_aware_delay_seconds':q[2]['average_completed_task_total_delay_seconds'],'delay_diff_QA_minus_TO_seconds':q[2]['average_completed_task_total_delay_seconds']-t[2]['average_completed_task_total_delay_seconds'],
  'tradeoff_actual_wait_seconds':t[2]['average_completed_task_waiting_time_seconds'],'queue_aware_actual_wait_seconds':q[2]['average_completed_task_waiting_time_seconds'],'actual_wait_diff_QA_minus_TO_seconds':q[2]['average_completed_task_waiting_time_seconds']-t[2]['average_completed_task_waiting_time_seconds'],
  'tradeoff_dest_dc1':t[3]['dest_dc1'],'queue_aware_dest_dc1':q[3]['dest_dc1'],'tradeoff_dest_dc2':t[3]['dest_dc2'],'queue_aware_dest_dc2':q[3]['dest_dc2'],
  'tradeoff_dest_dc3':t[3]['dest_dc3'],'queue_aware_dest_dc3':q[3]['dest_dc3'],'tradeoff_dest_dc4':t[3]['dest_dc4'],'queue_aware_dest_dc4':q[3]['dest_dc4'],
  'dest_dc1_diff':q[3]['dest_dc1']-t[3]['dest_dc1'],'dest_dc2_diff':q[3]['dest_dc2']-t[3]['dest_dc2'],'dest_dc3_diff':q[3]['dest_dc3']-t[3]['dest_dc3'],'dest_dc4_diff':q[3]['dest_dc4']-t[3]['dest_dc4'],
  'queue_estimate_min_seconds':q[3]['queue_estimate_min_seconds'],'queue_estimate_max_seconds':q[3]['queue_estimate_max_seconds'],'queue_estimate_nonzero_observations':q[3]['queue_estimate_nonzero_candidate_observations'],'queue_candidate_observations':q[3]['queue_candidate_observations'],
  'selected_queue_mean_seconds':q[3]['queue_estimate_mean_selected_seconds'],'selected_queue_nonzero_observations':q[3]['selected_queue_nonzero_observations'],'selected_queue_observations':q[3]['selected_queue_observations'],
  'ranking_changed_decisions':q[3]['ranking_changed_decisions'],'selected_destination_changed_decisions':q[3]['selected_destination_changed_decisions'],'queue_policy_decisions':q[3]['queue_decision_count']})
 # candidate-decision effects rows for complete QA run
 qr=loadcsv(q[0]/'raw/queue_decisions.csv'); groups=collections.defaultdict(list)
 for x in qr:groups[x['task_id']].append(x)
 for task_id,xs in groups.items():
  f=xs[0];decision_effects.append({'seed':seed,'task_id':task_id,'timestamp_seconds':f['estimate_timestamp_seconds'],'candidate_count':len(xs),
   'queue_wait_min_seconds':min(float(x['queue_wait_estimate_seconds']) for x in xs),'queue_wait_max_seconds':max(float(x['queue_wait_estimate_seconds']) for x in xs),
   'positive_penalty_candidate_count':sum(float(x['queue_penalty_seconds'])>0 for x in xs),'ranking_changed':f['ranking_changed'],
   'baseline_selected_candidate_id':f['baseline_selected_candidate_id'],'selected_candidate_id':f['selected_candidate_id'],
   'selected_destination_changed':f['selected_destination_changed']} )

writecsv(ROOT/'run_level.csv',raw_rows);writecsv(ROOT/'paired_by_seed.csv',paired);writecsv(ROOT/'run_status.csv',statuses);writecsv(ROOT/'queue_decision_effects.csv',decision_effects)

# Exact two-sided paired sign-flip permutation test on mean difference; n=5 permits full enumeration.
T_CRIT_DF4=2.7764451051977987
def signflip_p(diffs):
 n=len(diffs);obs=abs(sum(diffs)/n); total=0; extreme=0
 for signs in itertools.product((-1,1),repeat=n):
  val=abs(sum(x*s for x,s in zip(diffs,signs))/n);total+=1
  if val>=obs-1e-15:extreme+=1
 return extreme/total
metric_specs=[('completion_rate','completion_rate_diff_QA_minus_TO','rate'),('completed_tasks','completed_diff_QA_minus_TO','tasks'),('failed_tasks','failed_diff_QA_minus_TO','tasks'),('pending_tasks','pending_diff_QA_minus_TO','tasks'),('energy_wh','energy_diff_QA_minus_TO_wh','Wh'),('average_completed_total_delay_seconds','delay_diff_QA_minus_TO_seconds','s'),('average_completed_waiting_seconds','actual_wait_diff_QA_minus_TO_seconds','s'),('dest_dc1','dest_dc1_diff','tasks'),('dest_dc2','dest_dc2_diff','tasks'),('dest_dc3','dest_dc3_diff','tasks'),('dest_dc4','dest_dc4_diff','tasks')]
statrows=[]
for metric,diffcol,unit in metric_specs:
 tvals=[];qvals=[];diffs=[]
 for pair in paired:
  seed=pair['seed'];t=next(x for x in raw_rows if x['method']=='trade-off' and x['seed']==seed);q=next(x for x in raw_rows if x['method']=='queue-aware' and x['seed']==seed)
  if t[metric] is None or q[metric] is None:continue
  tvals.append(float(t[metric]));qvals.append(float(q[metric]));diffs.append(float(pair[diffcol]))
 n=len(diffs);mean=lambda x:sum(x)/len(x) if x else None
 def sd(x):return math.sqrt(sum((v-mean(x))**2 for v in x)/(len(x)-1)) if len(x)>1 else None
 dm=mean(diffs);ds=sd(diffs);half=T_CRIT_DF4*ds/math.sqrt(n) if n==5 and ds is not None else None
 statrows.append({'metric':metric,'unit':unit,'n_pairs':n,'tradeoff_mean':mean(tvals),'tradeoff_sd':sd(tvals),'queue_aware_mean':mean(qvals),'queue_aware_sd':sd(qvals),
  'paired_mean_diff_QA_minus_TO':dm,'paired_diff_sd':ds,'paired_diff_95ci_low':dm-half if half is not None else None,'paired_diff_95ci_high':dm+half if half is not None else None,
  'paired_signflip_exact_two_sided_p':signflip_p(diffs) if n else None,'ci_method':'paired t interval, df=4; t*=2.776445' if n==5 else 'not calculated'})
writecsv(ROOT/'paired_statistics.csv',statrows)

# Queue signal/ranking variability across seeds.
qstats=[]
for seed in SEEDS:
 pair=next((p for p in paired if p['seed']==seed),None)
 if not pair:continue
 q=next(r for r in raw_rows if r['method']=='queue-aware' and r['seed']==seed)
 qstats.append({'seed':seed,'candidate_observations':q['queue_candidate_observations'],'queue_min_seconds':q['queue_estimate_min_seconds'],'queue_max_seconds':q['queue_estimate_max_seconds'],
  'nonzero_candidate_observations':q['queue_estimate_nonzero_candidate_observations'],'selected_observations':q['selected_queue_observations'],'selected_nonzero_observations':q['selected_queue_nonzero_observations'],
  'selected_mean_queue_seconds':q['queue_estimate_mean_selected_seconds'],'selected_mean_waiting_queue_length':q['queue_estimate_mean_candidate_waiting_length'],
  'policy_decisions':q['queue_decision_count'],'ranking_changed_decisions':q['ranking_changed_decisions'],'selected_destination_changed_decisions':q['selected_destination_changed_decisions']})
writecsv(ROOT/'queue_signal_by_seed.csv',qstats)

# Small static PNG charts.
def fnt(sz=16):
 try:return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',sz)
 except OSError:return ImageFont.load_default()
def chart(title,subtitle):
 im=Image.new('RGB',(1100,650),'white');d=ImageDraw.Draw(im);d.text((45,22),title,font=fnt(25),fill='#202832');d.text((45,58),subtitle,font=fnt(14),fill='#576575');return im,d
def save(im,name):
 p=ROOT/'charts'/name;p.parent.mkdir(exist_ok=True);im.save(p)
# Paired completion bars.
im,d=chart('Completion rate by seed','Paired observations; Trade-Off vs Queue-Aware. One bar pair per seed; not a population-level claim.')
levels=[x['seed'] for x in paired]; vals=[max([r['completion_rate'] for r in raw_rows] or [0]) for _ in []]
x0,y0,x1,y1=100,130,1030,540
for k in range(6):
 y=y1-k*(y1-y0)/5;d.line((x0,y,x1,y),fill='#dce2e8');d.text((45,y-8),f'{k*2}%',font=fnt(12),fill='#404c5c')
for i,seed in enumerate(levels):
 cx=x0+100+i*180
 for j,m in enumerate(METHODS):
  r=next(x for x in raw_rows if x['seed']==seed and x['method']==m);v=float(r['completion_rate']);h=v/0.10*(y1-y0);x=cx+j*43
  col='#376da8' if j==0 else '#df873a';d.rectangle((x,y1-h,x+30,y1),fill=col);d.text((x-4,y1-h-20),f'{v*100:.2f}',font=fnt(12),fill='#202832')
 d.text((cx+5,555),str(seed),font=fnt(15),fill='#202832')
for j,m in enumerate(METHODS):
 x=110+j*180;d.rectangle((x,95,x+16,110),fill='#376da8' if j==0 else '#df873a');d.text((x+22,94),m,font=fnt(13),fill='#202832')
save(im,'completion_by_seed.png')
# Queue and decision variability.
im,d=chart('Queue signal and decision changes by seed','Queue wait estimated at candidate selection; ranking and winner changes are per policy-selection call.')
maxq=max(float(x['queue_max_seconds']) for x in qstats) or 1
for i,x in enumerate(qstats):
 cx=150+i*180;lo=float(x['queue_min_seconds']);hi=float(x['queue_max_seconds']);mean=float(x['selected_mean_queue_seconds']); yb=500
 d.line((cx,yb-hi/maxq*330,cx,yb-lo/maxq*330),fill='#376da8',width=7);d.ellipse((cx-7,yb-mean/maxq*330-7,cx+7,yb-mean/maxq*330+7),fill='#df873a')
 d.text((cx-27,520),str(x['seed']),font=fnt(14),fill='#202832');d.text((cx-25,545),f"rank {x['ranking_changed_decisions']}",font=fnt(12),fill='#376da8');d.text((cx-25,562),f"select {x['selected_destination_changed_decisions']}",font=fnt(12),fill='#a85e18')
for k in range(5):
 y=500-k*82.5;d.line((85,y,1040,y),fill='#e1e5e9');d.text((35,y-8),f'{maxq*k/4:.1f}s',font=fnt(11),fill='#4e5a68')
d.text((100,100),'Blue line = min–max candidate estimate; orange dot = mean selected estimate.',font=fnt(13),fill='#202832');save(im,'queue_signal_decisions_by_seed.png')
# EDC allocation stacked by methods and seed.
im,d=chart('Per-EDC task allocation by seed','All 2,175 task destination audit records per run; colors identify dc1–dc4, grouped by method.')
colors=['#4575b4','#91bfdb','#fdae61','#d73027']; maxn=2175
for i,seed in enumerate(levels):
 cx=150+i*180
 for j,m in enumerate(METHODS):
  r=next(x for x in raw_rows if x['seed']==seed and x['method']==m);x=cx+j*45;y=520
  for edc,color in zip(('dest_dc1','dest_dc2','dest_dc3','dest_dc4'),colors):
   h=int(r[edc])/maxn*340;d.rectangle((x,y-h,x+28,y),fill=color);y-=h
 d.text((cx-5,535),str(seed),font=fnt(14),fill='#202832')
for j,label in enumerate(('dc1','dc2','dc3','dc4')):
 x=80+j*130;d.rectangle((x,95,x+15,110),fill=colors[j]);d.text((x+21,94),label,font=fnt(13),fill='#202832')
save(im,'edc_allocation_by_seed.png')

# Summary metadata; fail loudly for incomplete cells or invalid pair.
valid_pairs=len(paired)==5 and all(p['paired_config_valid'] for p in paired)
status={'planned_runs':10,'run_statuses':statuses,'completed_valid_runs':sum(x['status']=='completed' for x in statuses),'failed_or_invalid_runs':sum(x['status']!='completed' for x in statuses),'complete_pairs':len(paired),'all_pairs_configuration_valid':valid_pairs,
 'queue_nonzero_in_every_seed':len(qstats)==5 and all(int(x['nonzero_candidate_observations'])>0 for x in qstats),'queue_candidate_observations_by_seed':qstats,
 'statistics':'paired exact sign-flip permutation on mean differences, two-sided; paired t confidence interval df=4; n=5, exploratory'}
(ROOT/'analysis_validation.json').write_text(json.dumps(status,indent=2)+'\n')
print(json.dumps({'runs':status['completed_valid_runs'],'failures':status['failed_or_invalid_runs'],'pairs':len(paired),'pairs_valid':valid_pairs,'queue_nonzero_each_seed':status['queue_nonzero_in_every_seed'],'summary_csv':str(ROOT/'run_level.csv'),'paired_csv':str(ROOT/'paired_by_seed.csv'),'stats_csv':str(ROOT/'paired_statistics.csv')},indent=2))
