#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
METHOD=trade-off; DEVICES=10; DURATION=1; ARCH=EDGE_AND_CLOUD
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  printf 'Usage: ./run.sh [--method trade-off|round-robin|all] [--all-baselines] [--devices 10|20|30] [--duration-minutes N] [--architecture EDGE_AND_CLOUD]\\n'; exit 0
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
command -v java >/dev/null || { echo 'Error: Java is required' >&2; exit 2; }
command -v mvn >/dev/null || { echo 'Error: Maven is required' >&2; exit 2; }
command -v python3 >/dev/null || { echo 'Error: Python 3 is required' >&2; exit 2; }
SIM="$ROOT/simulator/PureEdgeSim"
[[ -f "$SIM/pom.xml" ]] || { echo 'Error: simulator source missing' >&2; exit 2; }
python3 -c 'import matplotlib' 2>/dev/null || true
printf '====================================================\n TASK OFFLOADING EXPERIMENT\n====================================================\n Simulator: PureEdgeSim | Method: %s | Devices: %s\n Duration: %s simulated minutes | Architecture: %s\n' "$METHOD" "$DEVICES" "$DURATION" "$ARCH"
printf 'Build: '
(cd "$SIM" && mvn -q -DskipTests -Dmaven.javadoc.skip=true package)
echo 'OK (Maven package)' 
if [[ "$METHOD" == all ]]; then METHODS=(trade-off round-robin); else METHODS=("$METHOD"); fi
for m in "${METHODS[@]}"; do
 ID="$(date -u +%Y%m%dT%H%M%S%N)_${m}_${DEVICES}devices"
 OUT="$ROOT/results/runs/$ID"; mkdir -p "$OUT/raw"
 ALGO=TRADE_OFF; [[ "$m" == round-robin ]] && ALGO=ROUND_ROBIN
 echo "Simulation: $m — running (no misleading progress estimate)"
 # Every run gets independent properties, and upstream output cleanup stays disabled.
 cp -a "$ROOT/configs/baseline/." "$OUT/config/"
 python3 - "$OUT/config/simulation_parameters.properties" "$DEVICES" "$DURATION" "$ARCH" "$ALGO" <<'PY'
from pathlib import Path
import sys
p,n,d,arch,a=sys.argv[1:]; x=Path(p); values={'min_number_of_edge_devices':n,'max_number_of_edge_devices':n,'edge_device_counter_size':'1','simulation_time':d,'orchestration_architectures':arch,'orchestration_algorithms':a,'display_real_time_charts':'false','save_charts':'false','clear_output_folder':'false','parallel_simulation':'false'}; out=[]
for line in x.read_text().splitlines():
 k=line.split('=',1)[0].strip() if '=' in line else ''; out.append(f'{k}={values[k]}' if k in values else line)
x.write_text('\n'.join(out)+'\n')
PY
 # Run through the isolated wrapper against PureEdgeSim's built classes.
 python3 "$ROOT/scripts/execute_run.py" "$OUT" "$m" "$DEVICES" "$DURATION" "$ARCH" "$ALGO"
done
python3 "$ROOT/scripts/analyze.py" --latest
