#!/usr/bin/env python3
"""
Run cohort creation for the `falls` cohort (fall_injury_any = 1) across
all configured age bands (65-74, 75-84) and event years.

Requires Step 1b event filter to have run first:
  python 1b_apcd_event_filter/filter_protocol_events.py --age-band <band> --event-year <year>

Usage:
    python run_series_falls.py [--skip-existing] [--concurrent-workers N]
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from py_helpers.cohort_utils import check_existing_cohorts
from py_helpers.env_utils import get_workflow_python_bin

AGE_BANDS_ORDERED = ["65-74", "75-84"]
EVENT_YEARS = [2016, 2017, 2018, 2019]
COHORT = "falls"


def main():
    parser = argparse.ArgumentParser(
        description="Run falls cohort creation for all age bands and event years"
    )
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip partitions that already exist in S3")
    parser.add_argument("--concurrent-workers", type=int, default=1,
                        help="Number of concurrent workers (default: 1)")
    parser.add_argument("--python-bin", default=None,
                        help="Python executable path (default: current interpreter)")
    args = parser.parse_args()

    if args.python_bin is None:
        args.python_bin = str(get_workflow_python_bin())

    script_path = Path(__file__).parent / "0_create_cohort.py"
    if not script_path.exists():
        print(f"ERROR: {script_path} not found")
        sys.exit(1)

    if args.skip_existing:
        print("Checking for existing cohorts in S3...")
        all_jobs = check_existing_cohorts(age_bands=AGE_BANDS_ORDERED, event_years=EVENT_YEARS)
        jobs_to_process = [j for j in all_jobs if j.get("cohort") == COHORT]
        print(f"Found {len(jobs_to_process)} partitions that need processing")
    else:
        jobs_to_process = [
            {"age_band": band, "event_year": year}
            for band in AGE_BANDS_ORDERED
            for year in EVENT_YEARS
        ]
        print(f"Will process {len(jobs_to_process)} partitions (all)")

    if not jobs_to_process:
        print("All partitions already exist. Nothing to do.")
        return

    print(f"\nStarting {COHORT} cohort creation")
    print(f"  Age bands: {AGE_BANDS_ORDERED}")
    print(f"  Event years: {EVENT_YEARS}\n")

    success_count = failed_count = 0

    for i, job in enumerate(jobs_to_process, 1):
        age_band = job["age_band"]
        event_year = job["event_year"]
        job_id = f"{age_band}/{event_year}"

        print(f"\n{'='*70}")
        print(f"[{i}/{len(jobs_to_process)}] {COHORT}: {job_id}")
        print(f"{'='*70}")

        cmd = [
            args.python_bin,
            str(script_path),
            "--cohort", COHORT,
            "--age-band", age_band,
            "--event-year", str(event_year),
            "--starting-step", "phase1_data_preparation",
            "--operation-type", "concurrent_processing",
            "--log-level", "INFO",
            "--concurrent-workers", str(args.concurrent_workers),
        ]

        try:
            result = subprocess.run(cmd, check=True)
            success_count += 1
            print(f"OK: {job_id}")
        except subprocess.CalledProcessError as e:
            failed_count += 1
            print(f"FAILED: {job_id} — {e}")
        except KeyboardInterrupt:
            print(f"\nInterrupted. Processed {i-1}/{len(jobs_to_process)}.")
            sys.exit(1)

    print(f"\n{'='*70}")
    print(f"SUMMARY — {COHORT}")
    print(f"  Success: {success_count}  Failed: {failed_count}  Total: {len(jobs_to_process)}")
    print(f"{'='*70}")

    if failed_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
