#!/usr/bin/env python3
import json,shutil,subprocess,sys,re
from datetime import datetime,timezone
from pathlib import Path
run=Path(sys.argv[1]); method,devices,duration,arch,algorithm=sys.argv[2:]
root=Path(__file__).resolve().parents[1]; sim=root/'simulator/PureEdgeSim'; settings=run/'config'
start=datetime.now(timezone.utc).isoformat()
# The calling run.sh has already built PureEdgeSim after applying the tracked source-root patch.
cpfile=run/'classpath.txt'
cp=subprocess.run(['mvn','-q','dependency:build-classpath','-Dmdep.outputFile='+str(cpfile)],cwd=sim,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
if cp.returncode: print(cp.stdout); sys.exit(cp.returncode)
# Upstream MainApplication reads relative PureEdgeSim/settings paths; stage the exact config in a fresh per-run cwd.
wd=run/'work'; expected=wd/'PureEdgeSim/settings'; expected.mkdir(parents=True)
for f in settings.iterdir(): shutil.copy2(f,expected/f.name)
(expected.parent/'output').mkdir(exist_ok=True)
cpstr=f"{sim/'target/classes'}:{cpfile.read_text().strip()}"
cmd=['java','-cp',cpstr,'com.mechalikh.pureedgesim.MainApplication']
r=subprocess.run(cmd,cwd=wd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
(run/'raw/simulator-console.log').write_text(r.stdout)
outputs=expected.parent/'output'
for p in outputs.rglob('*'):
 if p.is_file():
  dest=run/'raw'/p.relative_to(outputs); dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,dest)
completed='SimulationThread - Simulation Finished!' in r.stdout and any((run/'raw').rglob('*.csv'))
manifest={'run_id':run.name,'method':method,'devices':int(devices),'duration_minutes':int(duration),'duration_seconds':int(duration)*60,'architecture':arch,'algorithm':algorithm,'simulator':'PureEdgeSim','simulator_commit':subprocess.run(['git','-C',str(sim),'rev-parse','HEAD'],capture_output=True,text=True).stdout.strip(),'java_version':subprocess.run(['java','-version'],capture_output=True,text=True).stderr.splitlines()[0],'start_utc':start,'finish_utc':datetime.now(timezone.utc).isoformat(),'command':' '.join(cmd),'working_directory':str(wd),'process_exit_code':r.returncode,'status':'completed' if r.returncode==0 and completed else 'failed','random_seed':'not exposed through selected settings/API','validity':'technical baseline using built-in default orchestrator' if r.returncode==0 and completed else 'invalid: simulator did not complete and save CSV output'}
(run/'config.json').write_text(json.dumps(manifest,indent=2)+'\n'); (run/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(f"Simulation process exit: {r.returncode}; completion marker: {'yes' if completed else 'no'}; authentic raw files: {sum(p.is_file() for p in (run/'raw').rglob('*'))}; saved {run}")
if r.returncode or not completed: print(r.stdout[-6000:]); sys.exit(r.returncode or 1)
