#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
METHOD=trade-off; DEVICES=10; DURATION=1; ARCH=EDGE_AND_CLOUD
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  printf 'Usage: ./run.sh [--method trade-off|round-robin|all] [--all-baselines] [--devices 10|20|30] [--duration-minutes N] [--architecture EDGE_AND_CLOUD]\n'
  printf 'If the PureEdgeSim submodule is absent, this script initializes it automatically.\n'
  exit 0
fi
while (($#)); do
 case "$1" in
  --method) METHOD="${2:?Missing method}"; shift 2;;
  --all-baselines) METHOD=all; shift;;
  --devices) DEVICES="${2:?Missing device count}"; shift 2;;
  --duration-minutes) DURATION="${2:?Missing duration}"; shift 2;;
  --architecture) ARCH="${2:?Missing architecture}"; shift 2;;
  *) echo "Error: unknown argument $1 (use --help)" >&2; exit 2;;
 esac
done
[[ "$METHOD" == trade-off || "$METHOD" == round-robin || "$METHOD" == all ]] || { echo 'Error: method must be trade-off, round-robin, or all' >&2; exit 2; }
[[ "$DEVICES" =~ ^[0-9]+$ ]] && ((DEVICES>0)) || { echo 'Error: devices must be a positive integer' >&2; exit 2; }
[[ "$DURATION" =~ ^[0-9]+$ ]] && ((DURATION>0)) || { echo 'Error: duration must be a positive integer in minutes' >&2; exit 2; }
command -v java >/dev/null || { echo 'Error: Java is required. Install a JDK and ensure java is on PATH.' >&2; exit 2; }
command -v mvn >/dev/null || { echo 'Error: Maven is required. Install Maven and ensure mvn is on PATH.' >&2; exit 2; }
command -v python3 >/dev/null || { echo 'Error: Python 3 is required. Install Python 3 and ensure python3 is on PATH.' >&2; exit 2; }
command -v git >/dev/null || { echo 'Error: Git is required to initialize the simulator submodule.' >&2; exit 2; }
SIM="$ROOT/simulator/PureEdgeSim"
if [[ ! -f "$SIM/pom.xml" ]]; then
  echo 'PureEdgeSim source is not populated; initializing pinned Git submodule...'
  if ! git -C "$ROOT" submodule update --init --recursive -- simulator/PureEdgeSim; then
    echo 'Error: could not fetch PureEdgeSim submodule. Check network access and retry: git submodule update --init --recursive' >&2; exit 1
  fi
fi
[[ -f "$SIM/pom.xml" ]] || { echo 'Error: PureEdgeSim source is still missing after submodule initialization.' >&2; exit 1; }
PINNED=$(git -C "$SIM" rev-parse HEAD 2>/dev/null || true)
[[ -n "$PINNED" ]] || { echo 'Error: simulator path is not a valid Git submodule checkout.' >&2; exit 1; }
PATCH="$ROOT/patches/pureedgesim-maven-source-root.patch"
if git -C "$SIM" apply --check "$PATCH" >/dev/null 2>&1; then
  git -C "$SIM" apply "$PATCH"
elif ! grep -Fq '<sourceDirectory>${project.basedir}/PureEdgeSim</sourceDirectory>' "$SIM/pom.xml"; then
  echo 'Error: upstream build patch does not apply cleanly; refusing to modify source.' >&2; exit 1
fi
printf '====================================================\n TASK OFFLOADING EXPERIMENT\n====================================================\n Simulator: PureEdgeSim (%s) | Method: %s | Devices: %s\n Duration: %s simulated minutes | Architecture: %s\n' "$PINNED" "$METHOD" "$DEVICES" "$DURATION" "$ARCH"
printf 'Java: '; java -version 2>&1 | head -n 1
printf 'Maven: '; mvn -version 2>&1 | head -n 1
printf 'Build: '
if ! (cd "$SIM" && mvn -q -DskipTests -Dmaven.javadoc.skip=true package); then
  echo 'Error: PureEdgeSim Maven build failed; see Maven diagnostics above.' >&2; exit 1
fi
echo 'OK (compiled PureEdgeSim source)'
if [[ "$METHOD" == all ]]; then METHODS=(trade-off round-robin); else METHODS=("$METHOD"); fi
for m in "${METHODS[@]}"; do
 ID="$(date -u +%Y%m%dT%H%M%S%N)_${m}_${DEVICES}devices"
 OUT="$ROOT/results/runs/$ID"; mkdir -p "$OUT/raw"
 ALGO=TRADE_OFF; [[ "$m" == round-robin ]] && ALGO=ROUND_ROBIN
 echo "Simulation: $m — running (no misleading progress estimate)"
 cp -a "$ROOT/configs/baseline/." "$OUT/config/"
 python3 - "$OUT/config/simulation_parameters.properties" "$DEVICES" "$DURATION" "$ARCH" "$ALGO" <<'PY'
from pathlib import Path
import sys
p,n,d,arch,a=sys.argv[1:]; x=Path(p); values={'min_number_of_edge_devices':n,'max_number_of_edge_devices':n,'edge_device_counter_size':'1','simulation_time':d,'orchestration_architectures':arch,'orchestration_algorithms':a,'display_real_time_charts':'false','save_charts':'false','clear_output_folder':'false','parallel_simulation':'false'}; out=[]
for line in x.read_text().splitlines():
 k=line.split('=',1)[0].strip() if '=' in line else ''; out.append(f'{k}={values[k]}' if k in values else line)
x.write_text('\n'.join(out)+'\n')
PY
 if ! python3 "$ROOT/scripts/execute_run.py" "$OUT" "$m" "$DEVICES" "$DURATION" "$ARCH" "$ALGO"; then
   echo "Error: $m simulation failed; inspect $OUT/raw/simulator-console.log and $OUT/manifest.json" >&2; exit 1
 fi
done
python3 "$ROOT/scripts/analyze.py" --latest
