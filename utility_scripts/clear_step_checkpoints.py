"""
Clear S3 pipeline checkpoints so a step runs again (e.g. after fixing code or re-running 3b).

Usage:
  # Clear Step 3b for falls cohort, all age bands
  python utility_scripts/clear_step_checkpoints.py --step 3b_feature_importance_eda --cohort falls

  # Clear specific age bands
  python utility_scripts/clear_step_checkpoints.py --step 3b_feature_importance_eda --cohort falls --age-band 65-74 --age-band 75-84

  # Dry run (show what would be deleted)
  python utility_scripts/clear_step_checkpoints.py --step 3b_feature_importance_eda --cohort falls --dry-run

  # Clear dashboard visuals (pipeline step 10) for one cohort/age_band
  python utility_scripts/clear_step_checkpoints.py --step 9_dashboard_visuals --cohort falls --age-band 65-74
"""

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from py_helpers.checkpoint_utils import (  # noqa: E402
    check_step_checkpoint_exists,
    clear_step_checkpoints,
)
from py_helpers.constants import AGE_BANDS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Clear S3 pipeline checkpoints so a step will run again."
    )
    parser.add_argument(
        "--step",
        type=str,
        required=True,
        help="Step name (e.g. 3b_feature_importance_eda)",
    )
    parser.add_argument(
        "--cohort",
        type=str,
        required=True,
        help="Cohort name (e.g. falls, ed)",
    )
    parser.add_argument(
        "--age-band",
        type=str,
        action="append",
        default=None,
        dest="age_bands",
        help="Age band(s) to clear (e.g. 65-74). If not set, uses all active AGE_BANDS.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print which checkpoints would be deleted.",
    )
    args = parser.parse_args()

    if args.age_bands:
        age_bands = args.age_bands
    else:
        age_bands = AGE_BANDS
        logger.info("Using all age bands: %s", age_bands)

    if args.dry_run:
        logger.info("Dry run: checking which checkpoints exist")
        for ab in age_bands:
            exists = check_step_checkpoint_exists(args.step, args.cohort, ab, logger)
            logger.info("  %s/%s: %s", args.cohort, ab, "exists (would delete)" if exists else "missing")
        return 0

    n = clear_step_checkpoints(args.step, args.cohort, age_bands, logger)
    logger.info("Cleared %d checkpoint(s) for %s/%s", n, args.step, args.cohort)
    return 0


if __name__ == "__main__":
    sys.exit(main())
