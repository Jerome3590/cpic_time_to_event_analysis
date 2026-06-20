#!/usr/bin/env python3
"""
Post-target leakage analysis for the falls and ED cohorts.

This compatibility entrypoint runs the Python/DuckDB analysis that creates:
    *_post_target_leakage_analysis.csv

The current workflow reads Step 2 cohort parquet directly.

The project no longer uses opioid-era process-mining scripts for this required
leakage artifact.
"""

import argparse
import platform
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"

if IS_WINDOWS:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
elif IS_LINUX:
    PROJECT_ROOT = Path("/home/pgx3874/cpic_time_to_event_analysis")
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

sys.path.insert(0, str(PROJECT_ROOT))

from py_helpers.env_utils import get_workflow_python_bin


def run_post_target_leakage_analysis(cohort: str, age_band: str, project_root: Path) -> bool:
    """Run post-target leakage analysis from Step 2 cohort parquet."""
    if cohort not in {"falls", "ed"}:
        print(f"[ERROR] Unknown cohort: {cohort}")
        print("        Valid cohorts: falls, ed")
        return False

    print(f"\n{'=' * 80}")
    print(f"Post-Target Leakage Analysis: {cohort} / {age_band}")
    print(f"{'=' * 80}")

    analysis_script = (
        project_root
        / "3b_feature_importance_eda"
        / "1_post_target_leakage"
        / "create_post_target_leakage_analysis.py"
    )
    if not analysis_script.exists():
        print(f"[ERROR] Post-target analysis script not found: {analysis_script}")
        return False

    result = subprocess.run(
        [str(get_workflow_python_bin()), str(analysis_script), "--cohort", cohort, "--age-band", age_band],
        cwd=str(project_root),
    )
    if result.returncode != 0:
        print(f"[ERROR] Post-target leakage analysis failed with exit code {result.returncode}")
        return False

    print("[OK] Post-target leakage analysis completed")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create post-target leakage analysis CSV for falls or ED"
    )
    parser.add_argument("--cohort", required=True, choices=["falls", "ed"], help="Cohort name")
    parser.add_argument("--age-band", required=True, help="Age band")
    parser.add_argument(
        "--project-root",
        type=str,
        default=None,
        help="Project root directory (default: auto-detect)",
    )

    args = parser.parse_args()
    project_root = Path(args.project_root).resolve() if args.project_root else PROJECT_ROOT

    success = run_post_target_leakage_analysis(
        cohort=args.cohort,
        age_band=args.age_band,
        project_root=project_root,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
