#!/usr/bin/env python3
"""
Runner: DTW Trajectory Analysis for cpic_time_to_event_analysis.

Runs the 3-step DTW pipeline for all configured cohorts/age bands:
  1. create_dtw_trajectories.py  - extract patient trajectories from model_events
  2. create_dtw_features.py      - compute DTW distances to prototype trajectories
  3. create_dtw_visuals.py       - build chart_data.json + plots and upload to S3

S3 outputs: s3://pgxdatalake/gold/{PROJECT_SLUG}/dtw_analysis/{cohort}/{age_band}/

Usage (from repo root):
    python 9_dtw_analysis/run_dtw_analysis.py
    python 9_dtw_analysis/run_dtw_analysis.py --cohorts falls --age-bands 65-74 75-84
    python 9_dtw_analysis/run_dtw_analysis.py --force
"""

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

try:
    from py_helpers.constants import COHORT_NAMES, AGE_BANDS, PROJECT_SLUG
except ImportError:
    COHORT_NAMES = ["falls", "ed"]
    AGE_BANDS = ["65-74", "75-84"]
    PROJECT_SLUG = "cpic_time_to_event"

PYTHON = sys.executable
DTW_DIR = Path(__file__).resolve().parent

STEPS = [
    ("create_dtw_trajectories.py", ["--cohort", "{cohort}", "--age-band", "{age_band}"]),
    ("create_dtw_features.py",     ["--cohort", "{cohort}", "--age-band", "{age_band}"]),
    ("create_dtw_visuals.py",      ["--cohort-name", "{cohort}", "--age-band", "{age_band}"]),
]


def run_step(script: str, cohort: str, age_band: str, extra_args: list) -> bool:
    cmd_args = [a.format(cohort=cohort, age_band=age_band) for a in extra_args]
    cmd = [PYTHON, str(DTW_DIR / script)] + cmd_args
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(REPO_ROOT))
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Run full DTW pipeline for cpic_time_to_event_analysis")
    parser.add_argument("--cohorts", nargs="+", default=COHORT_NAMES, help="Cohorts to run")
    parser.add_argument("--age-bands", nargs="+", default=AGE_BANDS, help="Age bands to run")
    parser.add_argument("--force", action="store_true", help="Pass --force to each step")
    parser.add_argument("--fail-fast", action="store_true", default=True, help="Stop on first failure")
    args = parser.parse_args()

    combinations = [(c, ab) for c in args.cohorts for ab in args.age_bands]
    print(f"DTW pipeline: {len(combinations)} cohort/age-band combinations")
    print(f"S3 output: s3://pgxdatalake/gold/{PROJECT_SLUG}/dtw_analysis/")
    print("=" * 70)

    for cohort, age_band in combinations:
        print(f"\n[DTW] {cohort} / {age_band}")
        print("-" * 50)
        for script, step_args in STEPS:
            extra = step_args + (["--force"] if args.force else [])
            ok = run_step(script, cohort, age_band, extra)
            if not ok:
                msg = f"[X] {script} for {cohort}/{age_band}"
                print(msg)
                if args.fail_fast:
                    sys.exit(1)
                break
        else:
            print(f"[OK] {cohort} / {age_band}")

    print("\n" + "=" * 70)
    print("DTW pipeline complete.")


if __name__ == "__main__":
    main()
