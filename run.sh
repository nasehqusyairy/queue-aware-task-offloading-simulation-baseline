#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE=technical-baseline
METHOD=trade-off
DEVICES=10
DURATION_SECONDS=60
TARGET=EDGE_AND_CLOUD
ARCH=EDGE_AND_CLOUD

usage() {
  printf 'Usage: ./run.sh [--profile technical-baseline|paper-aligned-baseline] [--method trade-off|round-robin|all] [--devices N] [--duration-seconds N | --duration-minutes N] [--destination-config NAME] [--architecture NAME]\n'
  printf 'Paper targets: ALL_DEVICES, EDGE_AND_EDGE_DC, EDGE_AND_CLOUD, EDGE_DC_AND_CLOUD, EDGE_ONLY, EDGE_DC_ONLY\n'
  printf 'Paper profile defaults to 200s when --duration-seconds is omitted. Legacy technical profile defaults to 1 minute.\n'
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then usage; exit 0; fi
DURATION_EXPLICIT=false
ARCH_EXPLICIT=false
while (($#)); do
  case "$1" in
    --profile) PROFILE="${2:?Missing profile}"; shift 2;;
    --method) METHOD="${2:?Missing method}"; shift 2;;
    --all-baselines) METHOD=all; shift;;
    --devices) DEVICES="${2:?Missing device count}"; shift 2;;
    --duration-seconds) DURATION_SECONDS="${2:?Missing duration}"; DURATION_EXPLICIT=true; shift 2;;
    --duration-minutes) DURATION_SECONDS=$((${2:?Missing duration} * 60)); DURATION_EXPLICIT=true; shift 2;;
    --destination-config) TARGET="${2:?Missing destination config}"; shift 2;;
    --architecture) ARCH="${2:?Missing architecture}"; ARCH_EXPLICIT=true; shift 2;;
    *) echo "Error: unknown argument $1 (use --help)" >&2; exit 2;;
  esac
done
[[ "$PROFILE" == technical-baseline || "$PROFILE" == paper-aligned-baseline ]] || { echo 'Error: unknown profile' >&2; exit 2; }
[[ "$METHOD" == trade-off || "$METHOD" == round-robin || "$METHOD" == all ]] || { echo 'Error: method must be trade-off, round-robin, or all' >&2; exit 2; }
[[ "$DEVICES" =~ ^[0-9]+$ ]] && ((DEVICES>0)) || { echo 'Error: devices must be a positive integer' >&2; exit 2; }
[[ "$DURATION_SECONDS" =~ ^[0-9]+$ ]] && ((DURATION_SECONDS>0)) || { echo 'Error: duration must be a positive integer number of seconds' >&2; exit 2; }
if [[ "$PROFILE" == paper-aligned-baseline && "$DURATION_EXPLICIT" == false ]]; then DURATION_SECONDS=200; fi
if [[ "$PROFILE" == paper-aligned-baseline && "$ARCH_EXPLICIT" == true ]]; then
  case "${ARCH^^}" in
    ALL) TARGET=ALL_DEVICES;;
    MIST_AND_EDGE) TARGET=EDGE_AND_EDGE_DC;;
    MIST_AND_CLOUD) TARGET=EDGE_AND_CLOUD;;
    EDGE_AND_CLOUD) TARGET=EDGE_DC_AND_CLOUD;;
    MIST_ONLY) TARGET=EDGE_ONLY;;
    EDGE_ONLY) TARGET=EDGE_DC_ONLY;;
    *) TARGET="${ARCH^^}";;
  esac
fi
command -v java >/dev/null || { echo 'Error: Java is required (install a JDK). ' >&2; exit 2; }
command -v mvn >/dev/null || { echo 'Error: Maven is required.' >&2; exit 2; }
command -v python3 >/dev/null || { echo 'Error: Python 3 is required.' >&2; exit 2; }
SIM="$ROOT/simulator/PureEdgeSim"
[[ -f "$SIM/pom.xml" && -f "$SIM/LICENSE" ]] || { echo 'Error: vendored PureEdgeSim source or GPL-3.0 license is missing.' >&2; exit 1; }
if [[ "$PROFILE" == paper-aligned-baseline ]]; then
  if ! ARCH="$(PYTHONPATH="$ROOT/scripts" python3 -c 'import sys; from paper_experiment import target_architecture; print(target_architecture(sys.argv[1]))' "$TARGET")"; then
    echo "Error: unsupported paper destination config '$TARGET'." >&2; exit 2
  fi
  CONFIG_SOURCE="$ROOT/configs/paper-aligned"
else
  ARCH="${ARCH^^}"
  CONFIG_SOURCE="$ROOT/configs/baseline"
fi
[[ -d "$CONFIG_SOURCE" ]] || { echo "Error: missing configuration directory $CONFIG_SOURCE" >&2; exit 1; }
python3 - "$SIM/pom.xml" <<'PY'
from pathlib import Path
import sys
text=Path(sys.argv[1]).read_text()
if '<sourceDirectory>${project.basedir}/PureEdgeSim</sourceDirectory>' not in text:
    raise SystemExit('Error: PureEdgeSim Maven source-root patch is absent; review patches/pureedgesim-maven-source-root.patch')
PY
printf 'PureEdgeSim build: '
if ! (cd "$SIM" && mvn -q -DskipTests -Dmaven.javadoc.skip=true package); then
  echo 'FAILED' >&2; exit 1
fi
[[ -f "$SIM/target/classes/com/mechalikh/pureedgesim/MainApplication.class" ]] || { echo 'Error: Maven exited without compiling PureEdgeSim classes.' >&2; exit 1; }
echo 'OK (compiled classes verified)'
if [[ "$METHOD" == all ]]; then METHODS=(trade-off round-robin); else METHODS=("$METHOD"); fi
for m in "${METHODS[@]}"; do
  RUN_ID="$(date -u +%Y%m%dT%H%M%S%N)_${PROFILE}_${m}_${DEVICES}ue_${TARGET}"
  OUT="$ROOT/results/runs/$RUN_ID"
  mkdir -p "$OUT/config" "$OUT/raw"
  cp -a "$CONFIG_SOURCE/." "$OUT/config/"
  if [[ "$m" == round-robin ]]; then ALGO=ROUND_ROBIN; else ALGO=TRADE_OFF; fi
  python3 - "$OUT/config/simulation_parameters.properties" "$DEVICES" "$DURATION_SECONDS" "$ARCH" "$ALGO" "$PROFILE" <<'PY'
from pathlib import Path
import sys
path, devices, seconds, architecture, algorithm, profile = sys.argv[1:]
values = {
    'min_number_of_edge_devices': devices,
    'max_number_of_edge_devices': devices,
    'edge_device_counter_size': '1',
    'simulation_time': format(int(seconds) / 60, '.17g'),
    'orchestration_architectures': architecture,
    'orchestration_algorithms': algorithm,
    'display_real_time_charts': 'false',
    'save_charts': 'false',
    'clear_output_folder': 'false',
    'parallel_simulation': 'false',
    'wait_for_all_tasks': 'false' if profile == 'paper-aligned-baseline' else 'true',
}
file = Path(path)
lines = []
for line in file.read_text().splitlines():
    key = line.split('=', 1)[0].strip() if '=' in line else ''
    lines.append(f'{key}={values[key]}' if key in values else line)
file.write_text('\n'.join(lines) + '\n')
PY
  printf 'Running %s: profile=%s devices=%s simulated_seconds=%s target=%s architecture=%s\n' "$m" "$PROFILE" "$DEVICES" "$DURATION_SECONDS" "$TARGET" "$ARCH"
  set +e
  python3 "$ROOT/scripts/execute_run.py" "$OUT" "$PROFILE" "$m" "$DEVICES" "$DURATION_SECONDS" "$TARGET" "$ARCH" "$ALGO"
  run_status=$?
  python3 "$ROOT/scripts/analyze.py" --run "$OUT"
  analysis_status=$?
  set -e
  printf 'RUN_DIR=%s\n' "$OUT"
  if ((run_status != 0 || analysis_status != 0)); then
    echo "Error: run or per-run analysis failed; artifacts preserved in $OUT" >&2
    exit 1
  fi
done
