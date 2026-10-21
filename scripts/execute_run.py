#!/usr/bin/env python3
import json,shutil,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
run=Path(sys.argv[1]); method,devices,duration,arch,algorithm=sys.argv[2:]
root=Path(__file__).resolve().parents[1]; sim=root/'simulator/PureEdgeSim'; work=root/'scripts/java'
(work/'experiment').mkdir(parents=True,exist_ok=True); shutil.copy2(root/'scripts/RunBaseline.java',work/'experiment/RunBaseline.java')
start=datetime.now(timezone.utc).isoformat()
# Repository pom excludes examples; compile their source tree explicitly as Maven's additional source root, untracked.
helper=sim/'compile-research-wrapper.sh'
helper.write_text('''#!/usr/bin/env bash\nset -euo pipefail\nROOT="$(cd "$(dirname "$0")" && pwd)"\nmvn -q -DskipTests package\nCP="$(mvn -q dependency:build-classpath -Dmdep.outputFile=/tmp/pes-cp >/dev/null && true)"\njavac -cp "$ROOT/target/classes:$(python3 -c \\\"from pathlib import Path; print(Path('/tmp/pes-cp').read_text())\\\")" -d "$ROOT/target/classes" "$ROOT/PureEdgeSim/examples/ResearchBaselineLauncher.java"\n''')
# use javac classpath from installed Maven compile dependencies emitted by build-classpath
cpfile=work/'classpath.txt'
cpres=subprocess.run(['mvn','-q','dependency:build-classpath','-Dmdep.outputFile='+str(cpfile)],cwd=sim,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
build=subprocess.run(['mvn','-q','-DskipTests','package'],cwd=sim,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
if build.returncode or cpres.returncode: print(build.stdout+cpres.stdout); sys.exit(build.returncode or cpres.returncode)
deps=cpfile.read_text().strip(); cls=sim/'target/classes'; cls.mkdir(exist_ok=True)
launcher=sim/'PureEdgeSim/examples/ResearchBaselineLauncher.java'
launcher.write_text('''package examples;\nimport com.mechalikh.pureedgesim.simulationmanager.Simulation;\npublic class ResearchBaselineLauncher { public static void main(String[] a) { Simulation s=new Simulation(); s.setCustomSettingsFolder(a[0]); s.setCustomOutputFolder(a[1]); s.launchSimulation(); } }\n''')
comp=subprocess.run(['javac','-cp',f'{cls}:{deps}','-d',str(cls),str(launcher)],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
launcher.unlink(missing_ok=True); helper.unlink(missing_ok=True)
if comp.returncode: print(comp.stdout); sys.exit(comp.returncode)
cmd=['java','-cp',f'{cls}:{deps}','examples.ResearchBaselineLauncher',str((run/'config').resolve()),str((run/'raw').resolve())]
r=subprocess.run(cmd,cwd=sim,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
(run/'raw/simulator-console.log').write_text(r.stdout)
out=sim/'PureEdgeSim/output'
if out.exists():
 for p in list(out.iterdir()):
  target=run/'raw'/p.name
  if target.exists(): target=run/'raw'/('upstream_'+p.name)
  shutil.move(str(p),target)
manifest={'run_id':run.name,'method':method,'devices':int(devices),'duration_minutes':int(duration),'architecture':arch,'algorithm':algorithm,'simulator':'PureEdgeSim','simulator_commit':subprocess.run(['git','-C',str(sim),'rev-parse','HEAD'],capture_output=True,text=True).stdout.strip(),'start_utc':start,'finish_utc':datetime.now(timezone.utc).isoformat(),'command':' '.join(cmd),'status':'completed' if r.returncode==0 else 'failed','exit_code':r.returncode,'random_seed':'not exposed through selected settings/API','validity':'technical baseline using built-in default orchestrator' if r.returncode==0 else 'invalid: simulator exited nonzero'}
(run/'config.json').write_text(json.dumps(manifest,indent=2)+'\n'); (run/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(f"Simulation process exit: {r.returncode}; raw output files: {sum(p.is_file() for p in (run/'raw').rglob('*'))}; saved {run}")
if r.returncode: print(r.stdout); sys.exit(r.returncode)
