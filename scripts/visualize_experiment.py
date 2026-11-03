#!/usr/bin/env python3
"""Render static PNG charts from aggregate.csv using Pillow."""
import argparse,csv,json,math,textwrap
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
W,H=1000,620; COLORS={'trade-off':(45,105,180),'queue-aware':(230,126,34)}; BG=(255,255,255); INK=(30,38,48); GRID=(220,225,230)
def font(size=16):
 try:return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',size)
 except OSError:return ImageFont.load_default()
def text(d,xy,s,fill=INK,size=16): d.text(xy,str(s),font=font(size),fill=fill)
def canvas(title,subtitle=''):
 im=Image.new('RGB',(W,H),BG); d=ImageDraw.Draw(im); text(d,(55,22),title,size=25)
 for i,line in enumerate(textwrap.wrap(subtitle,width=125)): text(d,(55,57+i*16),line,fill=(90,98,108),size=13)
 return im,d
def save(im,out,name):
 p=out/'charts'/name; p.parent.mkdir(parents=True,exist_ok=True); im.save(p); return p
def load_rows(root):
 p=root/'aggregate.csv'
 with p.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def complete_rows(rows):return [r for r in rows if r.get('status')=='completed' and not r.get('validation_errors')]
def chart_rates(rows,out):
 rs=complete_rows(rows); levels=['low','medium','high']; methods=['trade-off','queue-aware']; im,d=canvas('Task completion rate by workload','Points show each seed; thick bars show mean across available seeds. Completion = completed / generated.')
 x0,y0,x1,y1=100,130,880,500
 for i in range(6):
  y=y1-i*(y1-y0)/5; d.line((x0,y,x1,y),fill=GRID); text(d,(45,y-9),f'{i*20}%',size=12)
 for j,lvl in enumerate(levels):
  cx=x0+120+j*250
  for mi,m in enumerate(methods):
   group=[r for r in rs if r['workload']==lvl and r['method']==m and r.get('task_success_rate')]
   vals=[float(r['task_success_rate']) for r in group]; color=COLORS[m]; xx=cx+(mi-.5)*70
   if vals:
    mean=sum(vals)/len(vals); yy=y1-mean* (y1-y0)/.2
    d.line((xx,yy,x1 if False else xx+28,yy),fill=color,width=6)
    d.ellipse((xx+8,yy-7,xx+22,yy+7),fill=color)
    for k,v in enumerate(vals):
     py=y1-v*(y1-y0)/.2; d.ellipse((xx+12+k*9,py-4,xx+20+k*9,py+4),fill=(35,35,35))
  text(d,(cx-25,515),lvl.title(),size=15)
 for mi,m in enumerate(methods):
  x=110+mi*190; d.rectangle((x,95,x+18,109),fill=COLORS[m]); text(d,(x+25,93),m.title(),size=13)
 return save(im,out,'completion_rate.png')
def grouped_bars(rows,out):
 rs=complete_rows(rows); methods=['trade-off','queue-aware']; levels=['low','medium','high']; im,d=canvas('Task outcomes by workload','Mean stacked task counts per seed configuration; each segment separates completion, terminal failure, and horizon pending.')
 x0,y0,x1,y1=100,125,900,500
 groups=[]
 for lvl in levels:
  for m in methods:
   vals=[r for r in rs if r['workload']==lvl and r['method']==m]
   if vals:
    groups.append((lvl,m,[sum(int(r.get(k) or 0) for r in vals)/len(vals) for k in ('completed_tasks','terminally_failed_tasks','pending_tasks')]))
 maxv=max([sum(g[2]) for g in groups] or [1]); scale=(y1-y0)/maxv
 colors=[(57,160,96),(207,75,75),(237,184,65)]; y=y1
 for i in range(5):
  yy=y1-i*(y1-y0)/4; d.line((x0,yy,x1,yy),fill=GRID); text(d,(48,yy-8),str(round(maxv*i/4)),size=12)
 for i,(lvl,m,vals) in enumerate(groups):
  x=x0+30+i*125; bottom=y1
  for v,c in zip(vals,colors):
   h=v*scale; d.rectangle((x,bottom-h,x+52,bottom),fill=c); bottom-=h
  text(d,(x-4,510),f'{lvl[0].upper()} {m[0].upper()}',size=12)
 for i,(lab,c) in enumerate(zip(('Completed','Failed','Pending'),colors)):
  x=100+i*150; d.rectangle((x,90,x+16,105),fill=c); text(d,(x+22,88),lab,size=13)
 return save(im,out,'task_outcomes.png')
def metric_chart(rows,out,key,title,unit,filename,limitation=''):
 rs=complete_rows(rows); levels=['low','medium','high']; methods=['trade-off','queue-aware']; vals=[float(r[key]) for r in rs if r.get(key) not in ('',None)]
 im,d=canvas(title,unit+((' | '+limitation) if limitation else '')); x0,y0,x1,y1=100,130,880,500; vmax=max(vals or [1])*1.12
 for i in range(5):
  y=y1-i*(y1-y0)/4; d.line((x0,y,x1,y),fill=GRID); text(d,(25,y-8),f'{vmax*i/4:.3g}',size=12)
 for j,lvl in enumerate(levels):
  cx=x0+120+j*250
  for mi,m in enumerate(methods):
   g=[float(r[key]) for r in rs if r['workload']==lvl and r['method']==m and r.get(key) not in ('',None)]
   if g:
    mean=sum(g)/len(g); xx=cx+(mi-.5)*55; yy=y1-mean*(y1-y0)/vmax
    d.rectangle((xx,yy,xx+34,y1),fill=COLORS[m])
    for si,v in enumerate(g):
     py=y1-v*(y1-y0)/vmax; d.ellipse((xx+8+si*5,py-4,xx+16+si*5,py+4),fill=(25,25,25))
  text(d,(cx-25,515),lvl.title(),size=15)
 for i,m in enumerate(methods):
  x=110+i*190; d.rectangle((x,95,x+18,109),fill=COLORS[m]); text(d,(x+25,93),m.title(),size=13)
 return save(im,out,filename)
def distribution(rows,out):
 rs=complete_rows(rows); levels=['low','medium','high']; layers=['workload_cloud_tasks','workload_edge_tasks','workload_mist_tasks']; labs=['Cloud','Edge DC','Mist/UE']; colors=[(90,130,190),(55,165,130),(210,160,75)]
 im,d=canvas('Dispatched workload by destination layer','Mean task dispatch counts across completed runs. Not a per-device queue or utilization measurement.')
 x0,y0,x1,y1=100,130,900,500; allvals=[float(r[k] or 0) for r in rs for k in layers]; vmax=max(allvals or [1])*1.15
 for i in range(5):
  y=y1-i*(y1-y0)/4; d.line((x0,y,x1,y),fill=GRID); text(d,(30,y-8),f'{vmax*i/4:.3g}',size=12)
 for j,lvl in enumerate(levels):
  g=[r for r in rs if r['workload']==lvl]; cx=x0+120+j*250
  for li,k in enumerate(layers):
   v=sum(float(r[k] or 0) for r in g)/len(g) if g else 0; x=cx-50+li*35; y=y1-v*(y1-y0)/vmax; d.rectangle((x,y,x+28,y1),fill=colors[li])
  text(d,(cx-25,515),lvl.title(),size=15)
 for i,(lab,c) in enumerate(zip(labs,colors)):
  x=90+i*150; d.rectangle((x,95,x+16,110),fill=c); text(d,(x+22,93),lab,size=13)
 return save(im,out,'destination_workload.png')
def main():
 p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args(); root=a.output; rows=load_rows(root); out=root
 paths=[chart_rates(rows,out),grouped_bars(rows,out),metric_chart(rows,out,'energy_consumption','Computing energy consumption','Wh | simulator metric; computing nodes only','energy.png'),metric_chart(rows,out,'average_completed_task_total_delay_seconds','Average completed-task total delay','Simulator metric: accumulated network + queue waiting + CPU; not wall-clock or pure network latency. Event-clock elapsed may differ because per-hop latency accounting and event scheduling differ.','delay.png'),distribution(rows,out)]
 meta={"charts":[str(p.relative_to(root)) for p in paths],"per_device_queue_data_available":False,"queue_data_note":"Layer destination task counts are available; per-device queue length/utilization is not exposed in aggregate metrics."}; (root/'visualization_manifest.json').write_text(json.dumps(meta,indent=2)+'\n')
 html='''<!doctype html><meta charset="utf-8"><title>Experiment results</title><style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;color:#202832}img{width:100%;border:1px solid #ddd;margin:1rem 0}code{background:#eee;padding:.2rem}</style><h1>PureEdgeSim experiment results</h1><p>Charts and tables use simulator CSV-derived metrics in <code>aggregate.csv</code>. Quick mode is preliminary and not statistically conclusive.</p>'''
 for path in paths: html+=f'<h2>{path.stem.replace("_"," ").title()}</h2><img src="{path.relative_to(root)}" alt="{path.stem}">'
 html+='<p><a href="aggregate.csv">Seed-level aggregate CSV</a> · <a href="aggregate_summary.csv">Aggregate summary CSV</a> · <a href="EXPERIMENT_REPORT.md">Experiment report</a> · <a href="experiment.json">Experiment configuration and status</a></p>'
 (root/'index.html').write_text(html,encoding='utf-8')
 print('CHARTS='+','.join(str(p.resolve()) for p in paths))
if __name__=='__main__':main()
