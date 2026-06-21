#!/usr/bin/env python3
"""
Sync final results review artifacts and visualizations to project-scoped S3.

Uploads:
- 10_analysis_results/visualizations/scenario/
- 10_analysis_results/visualizations/results_review/
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from py_helpers.constants import PROJECT_SLUG, S3_BUCKET  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _iter_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return (path for path in root.rglob("*") if path.is_file())


def _sync_tree(local_root: Path, s3_prefix: str, dry_run: bool = False) -> List[str]:
    uploaded: List[str] = []
    try:
        from py_helpers.checkpoint_utils import upload_file_to_s3
    except Exception as exc:
        raise RuntimeError(f"Could not import upload_file_to_s3: {exc}") from exc

    if not local_root.exists():
        logger.warning("Local results root does not exist; skipping: %s", local_root)
        return uploaded

    for local_path in _iter_files(local_root):
        rel = local_path.relative_to(local_root).as_posix()
        s3_uri = f"{s3_prefix.rstrip('/')}/{rel}"
        if dry_run:
            logger.info("[dry-run] %s -> %s", local_path, s3_uri)
            uploaded.append(s3_uri)
            continue
        if upload_file_to_s3(local_path, s3_uri, logger=logger):
            uploaded.append(s3_uri)
    return uploaded


def sync_results_artifacts(dry_run: bool = False) -> List[str]:
    mappings: List[Tuple[Path, str]] = [
        (
            PROJECT_ROOT / "10_analysis_results" / "visualizations" / "scenario",
            f"s3://{S3_BUCKET}/gold/{PROJECT_SLUG}/analysis_visuals/scenario",
        ),
        (
            PROJECT_ROOT / "10_analysis_results" / "visualizations" / "results_review",
            f"s3://{S3_BUCKET}/gold/{PROJECT_SLUG}/analysis_visuals/results_review",
        ),
    ]
    uploaded: List[str] = []
    for local_root, s3_prefix in mappings:
        uploaded.extend(_sync_tree(local_root, s3_prefix, dry_run=dry_run))

    if uploaded and not dry_run:
        try:
            from py_helpers.checkpoint_utils import save_step_checkpoint

            save_step_checkpoint(
                step_name="4_results_review",
                cohort="all",
                age_band="all",
                metadata={"n_outputs": len(uploaded)},
                output_paths=uploaded,
            )
        except Exception as exc:
            logger.warning("Could not save results-review checkpoint: %s", exc)
    return uploaded


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync final results artifacts to project-scoped S3")
    parser.add_argument("--dry-run", action="store_true", help="Print uploads without writing to S3")
    args = parser.parse_args()
    uploaded = sync_results_artifacts(dry_run=args.dry_run)
    action = "Would upload" if args.dry_run else "Uploaded"
    logger.info("%s %d results artifact(s).", action, len(uploaded))


if __name__ == "__main__":
    main()
