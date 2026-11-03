#!/usr/bin/env python3
"""Run the paired Trade-Off/Round-Robin/Queue-Aware offered-load matrix."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from paper_experiment import queue_aware_matrix

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload-level", choices=("low", "medium", "high", "all"), default="all")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--queue-weight", type=float, default=1.0)
    parser.add_argument("--duration-seconds", type=int, default=200)
    parser.add_argument("--dry-run", action="store_true", help="print commands without running simulations")
    args = parser.parse_args(argv)
    if args.duration_seconds <= 0:
        parser.error("duration must be positive")

    matrix = queue_aware_matrix(args.seed, args.queue_weight)
    if args.workload_level != "all":
        matrix = [row for row in matrix if row["workload_level"] == args.workload_level]
    for row in matrix:
        command = [
            str(ROOT / "run.sh"), "--profile", "paper-aligned-baseline",
            "--method", str(row["method"]), "--workload-level", str(row["workload_level"]),
            "--destination-config", "EDGE_DC_ONLY", "--duration-seconds", str(args.duration_seconds),
            "--seed", str(args.seed), "--queue-weight", str(args.queue_weight),
        ]
        print("COMMAND=" + " ".join(command), flush=True)
        if not args.dry_run:
            result = subprocess.run(command, cwd=ROOT, check=False)
            if result.returncode:
                print(f"Matrix stopped after failed run: method={row['method']} workload={row['workload_level']}")
                return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
