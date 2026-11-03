#!/usr/bin/env python3
"""Analyze paired lambda sensitivity outputs and generate audit charts."""
import csv, json, math, itertools, collections
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parent
SEEDS=[1,8128,4401,2026,2027]
LAMBDAS=[0.0,0.5,1.0,2.0]
TCRIT=2.7764451051977987

def readcsv(p):
    with p.open(newline='',encoding='utf-8') as f: return list(csv.DictReader(f))
def writecsv(name, rows):
    if rows:
        with (ROOT/name).open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
def loadruns():
    out={}
    for p in (ROOT/'runs').glob('*/manifest.json'):
        m=json.loads(p.read_text()); method=m['method']; seed=int(m['random_seed'])
        lam=None if method=='trade-off' else float(m['queue_penalty_weight'])
        key=(method,lam,seed)
        if key in out: raise ValueError(f'duplicate run {key}')
        run=p.parent; met=json.loads((run/'metrics.json').read_text())
        if m['status']!='completed' or m.get('process_exit_code')!=0 or m.get('validation_errors') or met.get('validation_errors') or met.get('metric_validation_errors'):
            raise ValueError(f'invalid run {run}')
        for f in ['raw/destinations.csv','raw/task_event_trace.csv']:
            if not (run/f).is_file(): raise ValueError(f'missing {f} in {run}')
        if method=='queue-aware' and not (run/'raw/queue_decisions.csv').is_file(): raise ValueError(f'missing queue audit {run}')
        out[key]=(run,m,met)
    if len(out)!=25: raise ValueError(f'expected 25 runs, found {len(out)}')
    return out
def dests(run):
    return {r['task_id']: (r['destination_type'],r['destination_id']) for r in readcsv(run/'raw/destinations.csv') if r['record_type']=='DECISION'}
def sd(v): return math.sqrt(sum((x-sum(v)/len(v))**2 for x in v)/(len(v)-1)) if len(v)>1 else None
def mean(v): return sum(v)/len(v) if v else None
def signflip(d):
    observed=abs(mean(d)); vals=[abs(mean([x*s for x,s in zip(d,ss)])) for ss in itertools.product((-1,1),repeat=len(d))]
    return sum(x>=observed-1e-15 for x in vals)/len(vals)

runs=loadruns(); runrows=[]; paired=[]; qrows=[]; decisions=[]; lambda_equiv=[]
for seed in SEEDS:
    base=runs[('trade-off',None,seed)]; bm=base[1]; bmet=base[2]; bd=dests(base[0])
    for lam in LAMBDAS:
        run,m,met=runs[('queue-aware',lam,seed)]
        fields=['profile','devices','duration_seconds','destination_config','simulator_revision','simulator_properties','configuration_sha256','random_seed']
        mismatch=[x for x in fields if bm.get(x)!=m.get(x)]
        if mismatch or bm['random_seed']!=seed or m['random_seed']!=seed: raise ValueError(f'pair mismatch seed={seed} lambda={lam}: {mismatch}')
        dd=dests(run); q=readcsv(run/'raw/queue_decisions.csv'); groups=collections.defaultdict(list)
        for x in q: groups[x['task_id']].append(x)
        waits=[float(x['queue_wait_estimate_seconds']) for x in q if x['queue_wait_estimate_seconds']!='']
        selected=[x for x in q if x['selected'].lower()=='true']
        sw=[float(x['queue_wait_estimate_seconds']) for x in selected if x['queue_wait_estimate_seconds']!='']
        alloc=collections.Counter(v[1] for v in dd.values())
        changed=sum(x[0]['ranking_changed'].lower()=='true' for x in groups.values())
        dest_changed=sum(x[0]['selected_destination_changed'].lower()=='true' for x in groups.values())
        bydc={f'dc{i}':alloc[str(i)] for i in range(1,5)}
        row={'method':'queue-aware','lambda':lam,'seed':seed,'run_id':m['run_id'],'generated':met['generated_tasks'],'completed':met['completed_tasks'],'failed':met['terminally_failed_tasks'],'pending':met['pending_tasks'],'completion_rate':met['task_success_rate'],'energy_wh':met['energy_consumption'],'average_total_delay_s':met['average_completed_task_total_delay_seconds'],'actual_waiting_s':met['average_completed_task_waiting_time_seconds'],**bydc,'queue_observations':len(q),'queue_min_s':min(waits) if waits else None,'queue_max_s':max(waits) if waits else None,'queue_nonzero_observations':sum(x>0 for x in waits),'selected_queue_mean_s':mean(sw),'selected_queue_nonzero':sum(x>0 for x in sw),'ranking_changed_decisions':changed,'selected_destination_changed_decisions':dest_changed,'policy_decisions':len(groups)}
        runrows.append(row)
        basealloc=collections.Counter(v[1] for v in bd.values())
        pair={'seed':seed,'lambda':lam,'generated':met['generated_tasks'],'completed':met['completed_tasks'],'failed':met['terminally_failed_tasks'],'pending':met['pending_tasks'],'completion_rate':met['task_success_rate'],'energy_wh':met['energy_consumption'],'average_total_delay_s':met['average_completed_task_total_delay_seconds'],'actual_waiting_s':met['average_completed_task_waiting_time_seconds'],'completion_rate_diff':met['task_success_rate']-bmet['task_success_rate'],'completed_diff':met['completed_tasks']-bmet['completed_tasks'],'failed_diff':met['terminally_failed_tasks']-bmet['terminally_failed_tasks'],'pending_diff':met['pending_tasks']-bmet['pending_tasks'],'energy_diff_wh':met['energy_consumption']-bmet['energy_consumption'],'total_delay_diff_s':met['average_completed_task_total_delay_seconds']-bmet['average_completed_task_total_delay_seconds'],'actual_waiting_diff_s':met['average_completed_task_waiting_time_seconds']-bmet['average_completed_task_waiting_time_seconds'],'changed_task_destinations_vs_TO':sum(dd.get(k)!=v for k,v in bd.items()),'tradeoff_destinations':len(bd),'queue_destinations':len(dd),**{f'{k}_diff':alloc[str(i)]-basealloc[str(i)] for i,k in enumerate(('dc1','dc2','dc3','dc4'),1)},'queue_min_s':min(waits) if waits else None,'queue_max_s':max(waits) if waits else None,'queue_nonzero_observations':sum(x>0 for x in waits),'queue_observations':len(q),'ranking_changed_decisions':changed,'selected_destination_changed_decisions':dest_changed,'decision_count':len(groups)}
        paired.append(pair)
        qrows.append({'lambda':lam,'seed':seed,'queue_min_s':min(waits) if waits else None,'queue_max_s':max(waits) if waits else None,'queue_nonzero':sum(x>0 for x in waits),'queue_observations':len(q),'ranking_changed':changed,'destination_changed':dest_changed,'decisions':len(groups),'dest_change_fraction':dest_changed/len(groups) if groups else None,'rank_change_fraction':changed/len(groups) if groups else None})
        for tid,xs in groups.items():
            x=xs[0]; decisions.append({'lambda':lam,'seed':seed,'task_id':tid,'timestamp_s':x['estimate_timestamp_seconds'],'candidate_count':len(xs),'queue_wait_min_s':min(float(y['queue_wait_estimate_seconds']) for y in xs),'queue_wait_max_s':max(float(y['queue_wait_estimate_seconds']) for y in xs),'ranking_changed':x['ranking_changed'],'baseline_selected_candidate_id':x['baseline_selected_candidate_id'],'selected_candidate_id':x['selected_candidate_id'],'selected_destination_changed':x['selected_destination_changed'],'placement_cache_used':x['placement_cache_used']})
        if lam==0:
            all_task_ids=set(dd)|set(bd); same_dest=all(dd.get(k)==bd.get(k) for k in all_task_ids)
            same_metrics=all(met[k]==bmet[k] for k in ('generated_tasks','completed_tasks','terminally_failed_tasks','pending_tasks','task_success_rate','energy_consumption','average_completed_task_total_delay_seconds','average_completed_task_waiting_time_seconds'))
            zero_penalty=all(float(x['queue_penalty_seconds'])==0 for x in q)
            same_rank=all(x['baseline_rank']==x['combined_rank'] for x in q)
            same_winner=all(x['baseline_selected_candidate_id']==x['selected_candidate_id'] for x in q)
            lambda_equiv.append({'seed':seed,'same_all_task_destinations':same_dest,'same_metrics':same_metrics,'zero_penalty':zero_penalty,'same_candidate_ranks':same_rank,'same_winner_per_decision':same_winner,'queue_estimates_recorded':all(x['queue_estimate_available'].lower()=='true' for x in q),'queue_nonzero_observations':sum(float(x['queue_wait_estimate_seconds'])>0 for x in q),'queue_observations':len(q)})

writecsv('run_level.csv',runrows);writecsv('paired_by_seed_lambda.csv',paired);writecsv('queue_signal_by_lambda_seed.csv',qrows);writecsv('queue_decision_effects.csv',decisions);writecsv('lambda0_equivalence_by_seed.csv',lambda_equiv)

metrics=['completion_rate','completed','failed','pending','energy_wh','average_total_delay_s','actual_waiting_s','dc1','dc2','dc3','dc4']
summary=[]; stats=[]
for lam in LAMBDAS:
    rows=[r for r in runrows if r['lambda']==lam]; ps=[p for p in paired if p['lambda']==lam]
    summary.append({'method':'queue-aware','lambda':lam,'n_seeds':len(rows),**{f'{m}_mean':mean([float(r[m]) for r in rows]) for m in metrics},**{f'{m}_sd':sd([float(r[m]) for r in rows]) for m in metrics},'ranking_changed_mean':mean([r['ranking_changed_decisions'] for r in rows]),'destination_changed_mean':mean([r['selected_destination_changed_decisions'] for r in rows]),'queue_estimate_min_overall_s':min(r['queue_min_s'] for r in rows),'queue_estimate_max_overall_s':max(r['queue_max_s'] for r in rows),'queue_nonzero_observations_total':sum(r['queue_nonzero_observations'] for r in rows),'queue_observations_total':sum(r['queue_observations'] for r in rows)})
    for metric in metrics:
        diffkey={'completion_rate':'completion_rate_diff','completed':'completed_diff','failed':'failed_diff','pending':'pending_diff','energy_wh':'energy_diff_wh','average_total_delay_s':'total_delay_diff_s','actual_waiting_s':'actual_waiting_diff_s'}.get(metric,f'{metric}_diff')
        diffs=[float(p[diffkey]) for p in ps]
        # Paired baseline and treatment mean/SD.
        treatment=[float(r[metric]) for r in rows]
        basemetric={'completion_rate':'task_success_rate','completed':'completed_tasks','failed':'terminally_failed_tasks','pending':'pending_tasks','energy_wh':'energy_consumption','average_total_delay_s':'average_completed_task_total_delay_seconds','actual_waiting_s':'average_completed_task_waiting_time_seconds'}.get(metric,metric)
        basevals=[]
        for seed in SEEDS:
            _,_,bmet=runs[('trade-off',None,seed)]
            if metric in ('dc1','dc2','dc3','dc4'):
                basealloc=collections.Counter(v[1] for v in dests(runs[('trade-off',None,seed)][0]).values()); basevals.append(float(basealloc[str(int(metric[-1]))]))
            else: basevals.append(float(bmet[basemetric]))
        dm=mean(diffs); ds=sd(diffs); half=TCRIT*ds/math.sqrt(5) if ds is not None else None
        stats.append({'lambda':lam,'metric':metric,'unit':'proportion' if metric=='completion_rate' else ('Wh' if metric=='energy_wh' else ('seconds' if metric.endswith('_s') else 'tasks')),'n_pairs':5,'tradeoff_mean':mean(basevals),'tradeoff_sd':sd(basevals),'queue_aware_mean':mean(treatment),'queue_aware_sd':sd(treatment),'paired_mean_difference_QA_minus_TO':dm,'paired_difference_sd':ds,'paired_95ci_low':dm-half if half is not None else None,'paired_95ci_high':dm+half if half is not None else None,'exact_signflip_two_sided_p':signflip(diffs),'signflip_method':'full enumeration of 2^5 sign assignments; two-sided mean-difference statistic','CI_method':'paired t interval df=4; t*=2.776445'})
writecsv('lambda_summary.csv',summary);writecsv('paired_statistics.csv',stats)

# Charts
def font(sz):
    try:return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',sz)
    except OSError:return ImageFont.load_default()
def canvas(title,sub):
    im=Image.new('RGB',(1200,700),'white');d=ImageDraw.Draw(im);d.text((50,24),title,font=font(26),fill='#1f2933');d.text((50,62),sub,font=font(14),fill='#52616b');return im,d
chartdir=ROOT/'charts';chartdir.mkdir(exist_ok=True)
im,d=canvas('Completion rate by seed and queue penalty λ','Raw simulator task_success_rate; lines connect paired seeds; exploratory n=5 per setting.')
colors=['#1768ac','#2a9d8f','#e9a03b','#c44536']; xs=[250,450,650,850,1050]; y0,y1=550,130
for k in range(6):
    y=y0-k*(y0-y1)/5;d.line((100,y,1120,y),fill='#e2e6e9');d.text((45,y-8),f'{k*2}%',font=font(12),fill='#4b5563')
for li,lam in enumerate(LAMBDAS):
    points=[]
    for i,seed in enumerate(SEEDS):
        v=next(r['completion_rate'] for r in runrows if r['lambda']==lam and r['seed']==seed);y=y0-v/.10*(y0-y1);points.append((xs[i],y));d.ellipse((xs[i]-6,y-6,xs[i]+6,y+6),fill=colors[li])
    d.line(points,fill=colors[li],width=3)
for x,s in zip(xs,SEEDS):d.text((x-25,570),str(s),font=font(14),fill='#29323c')
for i,lam in enumerate(LAMBDAS):d.rectangle((100+i*170,95,116+i*170,111),fill=colors[i]);d.text((123+i*170,93),f'λ={lam:g}',font=font(14),fill='#29323c')
im.save(chartdir/'completion_rate_by_lambda_seed.png')
im,d=canvas('Queue penalty and decision changes','Mean per-seed fraction of Queue-Aware decisions with changed candidate ranking or selected destination.')
for k in range(6):
    y=550-k*80;d.line((110,y,1110,y),fill='#e2e6e9');d.text((55,y-8),f'{k*20}%',font=font(12),fill='#4b5563')
for i,lam in enumerate(LAMBDAS):
    rr=[x for x in qrows if x['lambda']==lam];x=230+i*210
    rank=100*mean([r['rank_change_fraction'] for r in rr]);dest=100*mean([r['dest_change_fraction'] for r in rr])
    for offset,val,color in [(0,rank,'#376da8'),(45,dest,'#df873a')]:
        h=val/100*400;d.rectangle((x+offset,550-h,x+offset+32,550),fill=color);d.text((x+offset-4,530-h),f'{val:.1f}',font=font(12),fill='#263238')
    d.text((x-5,570),f'λ={lam:g}',font=font(14),fill='#263238')
d.rectangle((220,95,236,111),fill='#376da8');d.text((243,93),'ranking changed',font=font(13),fill='#263238');d.rectangle((420,95,436,111),fill='#df873a');d.text((443,93),'destination changed',font=font(13),fill='#263238')
im.save(chartdir/'decision_change_frequency_by_lambda.png')
im,d=canvas('Paired mean differences vs Trade-Off','Queue-Aware minus Trade-Off; each panel has its own unit and scale; zero line means no difference.')
plotmetrics=[('completion_rate_diff','Completion (pp)',100,'#1768ac'),('energy_diff_wh','Energy (Wh)',1,'#e9a03b'),('total_delay_diff_s','Total delay (s)',1,'#c44536'),('actual_waiting_diff_s','Actual waiting (s)',1,'#2a9d8f')]
for j,(key,label,mult,col) in enumerate(plotmetrics):
    left=80+(j%2)*560; top=120+(j//2)*270; right=left+470; bottom=top+180
    vals=[100*mean([p[key] for p in paired if p['lambda']==lam]) if mult==100 else mean([p[key] for p in paired if p['lambda']==lam]) for lam in LAMBDAS]
    span=max(max(abs(v) for v in vals),0.001)*1.25
    d.text((left,top-26),label,font=font(16),fill=col)
    for tick in (-1,-.5,0,.5,1):
        y=top+90-tick*78
        d.line((left,y,right,y),fill='#e2e6e9' if tick else '#6b7280',width=2 if tick==0 else 1)
        d.text((left-40,y-7),f'{tick*span:.3g}',font=font(10),fill='#4b5563')
    points=[]
    for i,(lam,val) in enumerate(zip(LAMBDAS,vals)):
        x=left+65+i*115;y=top+90-(val/span)*78;points.append((x,y));d.ellipse((x-5,y-5,x+5,y+5),fill=col);d.text((x-18,bottom+7),f'λ={lam:g}',font=font(11),fill='#263238')
    d.line(points,fill=col,width=3)
im.save(chartdir/'paired_metric_differences.png')

valid_equiv=all(all(x[k] for k in ('same_all_task_destinations','same_metrics','zero_penalty','same_candidate_ranks','same_winner_per_decision','queue_estimates_recorded')) for x in lambda_equiv)
status={'planned_runs':25,'successful_runs':25,'failed_runs':0,'complete_paired_seed_sets':5,'configuration_pairs_valid':True,'lambda0_equivalent_all_seeds':valid_equiv,'lambda0_checks':lambda_equiv,'queue_nonzero_all_lambda_seed_cells':all(x['queue_nonzero']>0 for x in qrows),'queue_estimates_recorded_at_lambda0':all(x['queue_estimates_recorded'] for x in lambda_equiv),'statistics':'paired t 95% CI df=4 and exact two-sided paired sign-flip test via all 32 sign assignments, n=5; exploratory'}
(ROOT/'analysis_validation.json').write_text(json.dumps(status,indent=2)+'\n')
print(json.dumps({'runs':25,'equivalence_lambda0_all_seeds':valid_equiv,'queue_nonzero_all_cells':status['queue_nonzero_all_lambda_seed_cells'],'summary_csv':str(ROOT/'run_level.csv'),'stats_csv':str(ROOT/'paired_statistics.csv')},indent=2))
