#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if (($#)); then OUT="$1"; else OUT="$(python3 - "$ROOT" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1])/'results/experiments'
items=[]
for p in root.glob('*/experiment.json'):
 try:s=json.loads(p.read_text())
 except Exception:continue
 if s.get('status')=='completed':items.append((s.get('finished_utc',''),p.parent))
if items: print(max(items)[1])
PY
)"; fi
[[ -n "$OUT" && -d "$OUT" ]] || { echo 'No completed experiment directory found. Pass an output directory or run ./run_experiment.sh first.' >&2; exit 1; }
python3 "$ROOT/scripts/aggregate_experiment.py" "$OUT"
python3 "$ROOT/scripts/visualize_experiment.py" "$OUT"
echo "Results: $(realpath "$OUT")"
echo "HTML: $(realpath "$OUT/index.html")"
