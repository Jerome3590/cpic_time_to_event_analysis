"""
Clear Step 3a (and optionally S3) feature importance outputs so you can rerun with
new logic (e.g. after changing cohort definition or feature set).

Usage:
  # Clear local 3a outputs for ed cohort, all age bands (65-74, 75-84)
  python utility_scripts/clear_feature_importance_outputs.py --cohort ed

  # Clear specific age bands only
  python utility_scripts/clear_feature_importance_outputs.py --cohort ed --age-band 65-74 --age-band 75-84

  # Also delete from S3 (pgxdatalake) so downstream steps and other machines see the change
  python utility_scripts/clear_feature_importance_outputs.py --cohort ed --s3

  # Dry run (print what would be removed)
  python utility_scripts/clear_feature_importance_outputs.py --cohort ed --dry-run

Full rerun workflow after changing cohort definition:
  1. Re-run Step 2 (cohort creation) so cohort.parquet uses the new filter.
  2. Clear old FI: python utility_scripts/clear_feature_importance_outputs.py --cohort ed [--s3]
  3. Rerun Step 3a with --force for each age band, e.g.:
     python 3a_feature_importance/run_mc_feature_importance.py --cohort ed --age_band 65-74 --force
     (repeat for 75-84)
  4. Optionally re-run Step 3b and downstream (model data, final model) so they use the new aggregated FI.
"""

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from py_helpers.constants import (  # noqa: E402
    AGE_BANDS,
    age_band_to_fname,
    PROJECT_SLUG,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def list_local_files_to_remove(cohort: str, age_bands: list[str]) -> list[Path]:
    """All local files to delete for the given cohort/age_bands (3a outputs only)."""
    base = PROJECT_ROOT / "3a_feature_importance" / cohort
    if not base.exists():
        return []
    files = []
    for ab in age_bands:
        fname = age_band_to_fname(ab)
        # Main aggregated
        p = base / f"{cohort}_{fname}_aggregated_feature_importance.csv"
        if p.exists():
            files.append(p)
        # Baseline
        bp = base / "_baseline" / f"{cohort}_{fname}_aggregated_feature_importance.csv"
        if bp.exists():
            files.append(bp)
        # Per-run CSVs and plots (if present)
        for pattern in [
            f"{cohort}_{fname}_*_feature_importance_mc*.csv",
            f"{cohort}_{fname}_*_top*_features_mc*.png",
            f"{cohort}_{fname}_constant_features.csv",
        ]:
            for f in base.glob(pattern):
                files.append(f)
            bl = base / "_baseline"
            if bl.exists():
                for f in bl.glob(pattern):
                    files.append(f)
    return list(dict.fromkeys(files))


def delete_s3_prefix(cohort: str, age_band: str, dry_run: bool) -> int:
    """Delete objects under s3://pgxdatalake/gold/feature_importance/{cohort}/{age_band}/. Returns count deleted."""
    try:
        from py_helpers.common_imports import s3_client, S3_BUCKET
    except ImportError:
        logger.warning("S3 client not available; skipping S3 delete")
        return 0
    prefix = f"gold/{PROJECT_SLUG}/feature_importance/{cohort}/{age_band}/"
    try:
        paginator = s3_client.get_paginator("list_objects_v2")
        n = 0
        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
            for obj in page.get("Contents") or []:
                key = obj["Key"]
                if dry_run:
                    logger.info("  [S3 would delete] s3://%s/%s", S3_BUCKET, key)
                else:
                    s3_client.delete_object(Bucket=S3_BUCKET, Key=key)
                    logger.info("  [S3 deleted] s3://%s/%s", S3_BUCKET, key)
                n += 1
        # Also _baseline subprefix
        baseline_prefix = f"gold/{PROJECT_SLUG}/feature_importance/{cohort}/{age_band}/_baseline/"
        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=baseline_prefix):
            for obj in page.get("Contents") or []:
                key = obj["Key"]
                if dry_run:
                    logger.info("  [S3 would delete] s3://%s/%s", S3_BUCKET, key)
                else:
                    s3_client.delete_object(Bucket=S3_BUCKET, Key=key)
                    logger.info("  [S3 deleted] s3://%s/%s", S3_BUCKET, key)
                n += 1
        return n
    except Exception as e:
        logger.warning("S3 delete failed for %s: %s", prefix, e)
        return 0


def main():
    parser = argparse.ArgumentParser(
        description="Clear Step 3a feature importance outputs for a cohort so you can rerun."
    )
    parser.add_argument("--cohort", required=True, help="Cohort name (e.g. falls, ed)")
    parser.add_argument(
        "--age-band",
        action="append",
        dest="age_bands",
        help="Age band(s) to clear (e.g. 65-74). Default: all active age bands.",
    )
    parser.add_argument(
        "--s3",
        action="store_true",
        help="Also delete objects under s3://pgxdatalake/gold/feature_importance/{cohort}/{age_band}/",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only print what would be removed")
    args = parser.parse_args()

    if args.age_bands:
        age_bands = args.age_bands
    else:
        age_bands = AGE_BANDS
        logger.info("Using all age bands: %s", age_bands)

    # Local files
    to_remove = list_local_files_to_remove(args.cohort, age_bands)
    if not to_remove:
        logger.info("No local 3a feature importance files found for %s (age bands: %s)", args.cohort, age_bands)
    else:
        logger.info("Local files to remove: %d", len(to_remove))
        for f in to_remove:
            if args.dry_run:
                logger.info("  [would remove] %s", f)
            else:
                try:
                    f.unlink()
                    logger.info("  [removed] %s", f)
                except Exception as e:
                    logger.warning("  Failed to remove %s: %s", f, e)

    # S3
    if args.s3:
        logger.info("S3: clearing gold/feature_importance/%s/ for age bands %s", args.cohort, age_bands)
        for ab in age_bands:
            n = delete_s3_prefix(args.cohort, ab, args.dry_run)
            if n == 0 and not args.dry_run:
                logger.info("  No objects under .../%s/%s/", args.cohort, ab)

    logger.info("Done. Rerun Step 3a with --force for each age band, e.g.:")
    for ab in age_bands:
        fname = age_band_to_fname(ab)
        logger.info("  python 3a_feature_importance/run_mc_feature_importance.py --cohort %s --age_band %s --force", args.cohort, ab)
    return 0


if __name__ == "__main__":
    sys.exit(main())
