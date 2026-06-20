#!/usr/bin/env python3
"""
Create Post-Target Analysis CSV

Analyzes Step 2 cohort event rows to identify which features (ICD/CPT codes, drugs)
appear primarily after the target event, indicating post-target leakage.

Target is determined by cohort:
- falls cohort: fall_injury_any = 1 (injury + external cause W00-W19 on same encounter; first_falls_date in Step 2)
- ed cohort:    ed_event = 1     (POS=23 or revenue code 045x/0981; first_ed_date)

This script:
1. Loads Step 2 cohort parquet with target dates
2. Compares feature timing before and after target dates
3. Creates a summary CSV with feature names and is_post_target_leakage flag
"""

import argparse
import sys
import os
import platform
import pandas as pd
from pathlib import Path

# Detect operating system and set project root
IS_WINDOWS = platform.system() == 'Windows'
IS_LINUX = platform.system() == 'Linux'

if IS_WINDOWS:
    # Windows: Use current workspace directory (go up 2 levels: 1_post_target_leakage -> 3b_feature_importance_eda -> project root)
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
elif IS_LINUX:
    # Linux/EC2: Use EC2 path
    PROJECT_ROOT = Path('/home/pgx3874/cpic_time_to_event_analysis')
else:
    # Fallback: Use current file's parent directory (go up 2 levels)
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

sys.path.insert(0, str(PROJECT_ROOT))

from py_helpers.constants import (
    age_band_to_fname,
    age_band_partition_candidates,
    get_physical_age_bands_for_gold,
    get_target_name_by_cohort,
)
from py_helpers.env_utils import get_project_data_root, get_refined_feature_importance_root


def analyze_post_target_leakage_from_events(
    cohort: str,
    age_band: str,
    project_root: Path,
    post_target_threshold: float = 0.8,
    min_events: int = 5
) -> pd.DataFrame:
    """
    Analyze event-level data to identify post-target leakage features.
    
    For falls cohort: Analyzes all features (ICD codes, CPT codes, drugs)
    For ed cohort: Analyzes only drugs
    
    For each feature, calculates:
    - Total occurrences in target cases
    - Occurrences BEFORE target event (first_falls_date for falls, first_ed_date for ed)
    - Occurrences AFTER target event
    - Post-target ratio (post / total)
    
    A feature is flagged as leakage if:
    - post_target_ratio > threshold (default 0.8 = 80% of occurrences are post-target)
    - AND has minimum number of events (default 5) for statistical significance
    
    Args:
        cohort: Cohort name (falls or ed)
        age_band: Age band
        project_root: Project root directory
        post_target_threshold: Threshold for post-target ratio (0.0-1.0)
        min_events: Minimum number of events required for analysis
    
    Returns:
        DataFrame with columns: feature, is_post_target_leakage, is_pre_target_predictive,
        pre_target_ratio, post_target_ratio, pre_count, post_count, total_count, unique_patients
    """
    import duckdb
    
    age_band_fname = age_band_to_fname(age_band)
    
    # Step 3b only needs target-case event timing plus target date from Step 2.
    project_data_root = get_project_data_root()
    configured_data_root = Path(os.getenv("PGX_DATA_ROOT", "")) if os.getenv("PGX_DATA_ROOT") else None
    candidate_roots = [project_data_root, project_root]
    if configured_data_root is not None:
        candidate_roots.append(configured_data_root)
    # De-duplicate while preserving order.
    data_roots = []
    seen_roots = set()
    for root in candidate_roots:
        key = str(root)
        if key not in seen_roots:
            data_roots.append(root)
            seen_roots.add(key)

    cohort_parquet_paths = []
    physical_bands = get_physical_age_bands_for_gold(age_band)
    for year in [2016, 2017, 2018, 2019]:
        added_for_year = False
        for physical in physical_bands:
            for part in age_band_partition_candidates(physical):
                for base in data_roots:
                    p = (
                        base
                        / "gold"
                        / "cohorts"
                        / f"cohort_name={cohort}"
                        / f"event_year={year}"
                        / f"age_band={part}"
                        / "cohort.parquet"
                    )
                    if p.exists():
                        cohort_parquet_paths.append(str(p))
                        added_for_year = True
                        break
                if added_for_year:
                    break
            if added_for_year:
                break

    if cohort_parquet_paths:
        print("[INFO] Using Step 2 cohort parquet directly for post-target leakage analysis")
        for path in cohort_parquet_paths:
            print(f"  - {path}")
        cohort_paths_literal = ", ".join(f"'{p.replace(chr(39), chr(39) + chr(39))}'" for p in cohort_parquet_paths)
        target_name = get_target_name_by_cohort(cohort)

        con = duckdb.connect()
        schema = con.execute(
            f"DESCRIBE SELECT * FROM read_parquet([{cohort_paths_literal}], union_by_name=True)"
        ).fetchall()
        available_cols = {row[0] for row in schema}
        target_date_candidates = (
            ["first_falls_date", "first_fall_date"] if cohort == "falls" else ["first_ed_date"]
        )
        target_date_col = next((col for col in target_date_candidates if col in available_cols), None)
        if target_date_col is None:
            print(
                "[ERROR] Step 2 cohort parquet is missing a target-date column. "
                f"Expected one of {target_date_candidates}; found columns: {sorted(available_cols)[:40]}"
            )
            con.close()
            return pd.DataFrame()
        print(f"[INFO] Using target-date column: {target_date_col}")

        if cohort == "ed":
            query = f"""
            WITH target_events AS (
                SELECT
                    mi_person_key,
                    TRY_CAST(event_date AS DATE) AS event_date,
                    TRY_CAST({target_date_col} AS DATE) AS target_date,
                    drug_name
                FROM read_parquet([{cohort_paths_literal}], union_by_name=True)
                WHERE is_target_case = 1
                  AND {target_date_col} IS NOT NULL
                  AND event_date IS NOT NULL
                  AND drug_name IS NOT NULL
            ),
            feature_events AS (
                SELECT
                    mi_person_key,
                    event_date,
                    target_date,
                    CASE
                        WHEN event_date < target_date THEN 'pre'
                        WHEN event_date >= target_date THEN 'post'
                        ELSE 'unknown'
                    END AS timing,
                    'item_drug_' || UPPER(REPLACE(REPLACE(drug_name, ' ', '_'), '-', '_')) AS feature
                FROM target_events
            ),
            feature_stats AS (
                SELECT
                    feature,
                    COUNT(*) AS total_count,
                    SUM(CASE WHEN timing = 'pre' THEN 1 ELSE 0 END) AS pre_count,
                    SUM(CASE WHEN timing = 'post' THEN 1 ELSE 0 END) AS post_count,
                    COUNT(DISTINCT mi_person_key) AS unique_patients,
                    CAST(SUM(CASE WHEN timing = 'pre' THEN 1 ELSE 0 END) AS FLOAT) / NULLIF(COUNT(*), 0) AS pre_target_ratio,
                    CAST(SUM(CASE WHEN timing = 'post' THEN 1 ELSE 0 END) AS FLOAT) / NULLIF(COUNT(*), 0) AS post_target_ratio
                FROM feature_events
                WHERE timing IN ('pre', 'post')
                GROUP BY feature
                HAVING COUNT(*) >= {min_events}
            )
            SELECT
                feature,
                total_count,
                pre_count,
                post_count,
                unique_patients,
                pre_target_ratio,
                post_target_ratio,
                CASE WHEN post_target_ratio >= {post_target_threshold} THEN 1 ELSE 0 END AS is_post_target_leakage,
                CASE WHEN pre_target_ratio >= 0.8 THEN 1 ELSE 0 END AS is_pre_target_predictive
            FROM feature_stats
            ORDER BY post_target_ratio DESC, total_count DESC
            """
        else:
            icd_selects = "\nUNION ALL\n".join(
                f"""
                SELECT
                    mi_person_key,
                    event_date,
                    target_date,
                    timing,
                    'item_icd_' || REPLACE(UPPER({col}), '.', '') AS feature
                FROM timed_events
                WHERE {col} IS NOT NULL
                """
                for col in [
                    "primary_icd_diagnosis_code",
                    "two_icd_diagnosis_code",
                    "three_icd_diagnosis_code",
                    "four_icd_diagnosis_code",
                    "five_icd_diagnosis_code",
                    "six_icd_diagnosis_code",
                    "seven_icd_diagnosis_code",
                    "eight_icd_diagnosis_code",
                    "nine_icd_diagnosis_code",
                    "ten_icd_diagnosis_code",
                ]
            )
            query = f"""
            WITH target_events AS (
                SELECT
                    mi_person_key,
                    TRY_CAST(event_date AS DATE) AS event_date,
                    TRY_CAST({target_date_col} AS DATE) AS target_date,
                    primary_icd_diagnosis_code,
                    two_icd_diagnosis_code,
                    three_icd_diagnosis_code,
                    four_icd_diagnosis_code,
                    five_icd_diagnosis_code,
                    six_icd_diagnosis_code,
                    seven_icd_diagnosis_code,
                    eight_icd_diagnosis_code,
                    nine_icd_diagnosis_code,
                    ten_icd_diagnosis_code,
                    procedure_code,
                    drug_name
                FROM read_parquet([{cohort_paths_literal}], union_by_name=True)
                WHERE is_target_case = 1
                  AND {target_date_col} IS NOT NULL
                  AND event_date IS NOT NULL
            ),
            timed_events AS (
                SELECT
                    *,
                    CASE
                        WHEN event_date < target_date THEN 'pre'
                        WHEN event_date >= target_date THEN 'post'
                        ELSE 'unknown'
                    END AS timing
                FROM target_events
            ),
            feature_events AS (
                {icd_selects}
                UNION ALL
                SELECT
                    mi_person_key,
                    event_date,
                    target_date,
                    timing,
                    'item_cpt_' || UPPER(REPLACE(REPLACE(procedure_code, ' ', ''), '.', '')) AS feature
                FROM timed_events
                WHERE procedure_code IS NOT NULL
                UNION ALL
                SELECT
                    mi_person_key,
                    event_date,
                    target_date,
                    timing,
                    'item_drug_' || UPPER(REPLACE(REPLACE(drug_name, ' ', '_'), '-', '_')) AS feature
                FROM timed_events
                WHERE drug_name IS NOT NULL
            ),
            feature_stats AS (
                SELECT
                    feature,
                    COUNT(*) AS total_count,
                    SUM(CASE WHEN timing = 'pre' THEN 1 ELSE 0 END) AS pre_count,
                    SUM(CASE WHEN timing = 'post' THEN 1 ELSE 0 END) AS post_count,
                    COUNT(DISTINCT mi_person_key) AS unique_patients,
                    CAST(SUM(CASE WHEN timing = 'pre' THEN 1 ELSE 0 END) AS FLOAT) / NULLIF(COUNT(*), 0) AS pre_target_ratio,
                    CAST(SUM(CASE WHEN timing = 'post' THEN 1 ELSE 0 END) AS FLOAT) / NULLIF(COUNT(*), 0) AS post_target_ratio
                FROM feature_events
                WHERE timing IN ('pre', 'post')
                GROUP BY feature
                HAVING COUNT(*) >= {min_events}
            )
            SELECT
                feature,
                total_count,
                pre_count,
                post_count,
                unique_patients,
                pre_target_ratio,
                post_target_ratio,
                CASE WHEN post_target_ratio >= {post_target_threshold} THEN 1 ELSE 0 END AS is_post_target_leakage,
                CASE WHEN pre_target_ratio >= 0.8 THEN 1 ELSE 0 END AS is_pre_target_predictive
            FROM feature_stats
            ORDER BY post_target_ratio DESC, total_count DESC
            """
        try:
            results_df = con.execute(query).df()
            con.close()
            print(f"[OK] Analyzed {len(results_df)} features from Step 2 cohort data")
            if len(results_df) > 0:
                leakage_count = results_df["is_post_target_leakage"].sum()
                predictive_count = results_df.get("is_pre_target_predictive", pd.Series([0] * len(results_df))).sum()
                print(f"   Features with post-{target_name} ratio >= {post_target_threshold:.0%} (leakage): {leakage_count}")
                print(f"   Features with pre-{target_name} ratio >= 80% (predictive): {predictive_count}")
            return results_df
        except Exception as e:
            print(f"[ERROR] Failed to analyze Step 2 cohort data: {e}")
            import traceback
            traceback.print_exc()
            con.close()
            return pd.DataFrame()

    print(f"[ERROR] Step 2 cohort parquet files not found for {cohort}/{age_band}.")
    print("        Expected under gold/cohorts/cohort_name={cohort}/event_year=*/age_band=*/cohort.parquet")
    return pd.DataFrame()


def analyze_post_target_leakage(
    cohort: str,
    age_band: str,
    project_root: Path,
    post_target_threshold: float = 0.8
) -> pd.DataFrame:
    """
    Analyze post-target leakage features from Step 2 cohort parquet.
    
    Args:
        cohort: Cohort name (falls or ed)
        age_band: Age band
        project_root: Project root directory
        post_target_threshold: Threshold for post-target ratio (0.0-1.0, default: 0.8)
    
    Returns:
        DataFrame with leakage analysis results
    """
    # Cohort-specific target terminology
    target_name = get_target_name_by_cohort(cohort)

    print(f"\n[INFO] Using Step 2 cohort parquet for post-target leakage analysis")
    print(f"       This provides accurate pre/post {target_name} ratios for each feature")
    return analyze_post_target_leakage_from_events(
        cohort=cohort,
        age_band=age_band,
        project_root=project_root,
        post_target_threshold=post_target_threshold,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Create post-target analysis CSV from Step 2 cohort parquet"
    )
    parser.add_argument("--cohort", required=True, help="Cohort name")
    parser.add_argument("--age-band", required=True, help="Age band")
    parser.add_argument(
        "--project-root",
        type=str,
        default=None,
        help="Project root directory (default: auto-detect)"
    )
    parser.add_argument(
        "--post-target-threshold",
        type=float,
        default=0.8,
        help="Threshold for post-target ratio to flag as leakage (0.0-1.0, default: 0.8 = 80%%)"
    )
    parser.add_argument(
        "--min-events",
        type=int,
        default=5,
        help="Minimum number of events required for analysis (default: 5)"
    )
    args = parser.parse_args()
    
    # Determine project root
    if args.project_root:
        project_root = Path(args.project_root)
    else:
        project_root = PROJECT_ROOT
    
    print(f"\n{'='*80}")
    print(f"Creating Post-Target Leakage Analysis: {args.cohort} / {args.age_band}")
    print(f"{'='*80}")
    
    # Analyze post-target leakage
    results_df = analyze_post_target_leakage(
        cohort=args.cohort,
        age_band=args.age_band,
        project_root=project_root,
        post_target_threshold=args.post_target_threshold
    )
    
    if results_df.empty:
        print(f"\n[ERROR] No results generated. Check that Step 2 cohort parquet is available.")
        sys.exit(1)
    
    # Save results
    age_band_fname = age_band_to_fname(args.age_band)
    output_dir = get_refined_feature_importance_root() / args.cohort / age_band_fname
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = output_dir / f"{args.cohort}_{age_band_fname}_post_target_leakage_analysis.csv"
    
    # Move from the temporary features/ subdirectory if present.
    wrong_location = output_dir / "features" / f"{args.cohort}_{age_band_fname}_post_target_leakage_analysis.csv"
    if wrong_location.exists() and not output_path.exists():
        print(f"\n[INFO] Found file in wrong location: {wrong_location}")
        print(f"       Moving to correct location: {output_path}")
        wrong_location.rename(output_path)
    elif wrong_location.exists() and output_path.exists():
        # Both exist - remove the one in wrong location
        print(f"\n[INFO] File exists in both locations. Removing wrong location: {wrong_location}")
        wrong_location.unlink()
    
    results_df.to_csv(output_path, index=False)
    
    print(f"\n[OK] Saved post-target analysis to: {output_path}")
    print(f"   Total features analyzed: {len(results_df)}")
    print(f"   Post-target leakage features: {results_df['is_post_target_leakage'].sum()}")
    
    # Show statistics (target by cohort: falls=fall_injury_any, ed=ed_event)
    target_name = get_target_name_by_cohort(args.cohort)
    ratio_col = 'post_target_ratio' if 'post_target_ratio' in results_df.columns else 'post_f1120_ratio'
    pre_ratio_col = 'pre_target_ratio' if 'pre_target_ratio' in results_df.columns else 'pre_f1120_ratio'
    
    if ratio_col in results_df.columns:
        leakage_features = results_df[results_df['is_post_target_leakage'] == 1]
        predictive_features = results_df[results_df.get('is_pre_target_predictive', pd.Series([0]*len(results_df))) == 1]
        
        if len(leakage_features) > 0:
            print(f"\n   [WARN] Post-target leakage features (post-{target_name} ratio >= {args.post_target_threshold:.0%}):")
            print(f"   {'='*80}")
            for idx, row in leakage_features.head(20).iterrows():
                post_ratio_pct = row[ratio_col] * 100
                pre_ratio_pct = row.get(pre_ratio_col, 0) * 100
                # Handle NaN/None values safely
                pre_val = row.get('pre_count', 0)
                post_val = row.get('post_count', 0)
                total_val = row.get('total_count', 0)
                pre_count = int(pre_val) if pd.notna(pre_val) else 0
                post_count = int(post_val) if pd.notna(post_val) else 0
                total_count = int(total_val) if pd.notna(total_val) else 0
                print(f"     {row['feature']:40s} | Post: {post_ratio_pct:5.1f}% | Pre: {pre_ratio_pct:5.1f}% | Pre: {pre_count:4d} | Post: {post_count:4d} | Total: {total_count:4d}")
            if len(leakage_features) > 20:
                print(f"     ... and {len(leakage_features) - 20} more")
            print(f"   {'='*80}")
        
        if len(predictive_features) > 0:
            print(f"\n   [OK] Pre-target predictive features (pre-{target_name} ratio >= 80%):")
            print(f"   {'='*80}")
            for idx, row in predictive_features.head(20).iterrows():
                post_ratio_pct = row.get(ratio_col, 0) * 100
                pre_ratio_pct = row.get(pre_ratio_col, 0) * 100
                pre_val = row.get('pre_count', 0)
                post_val = row.get('post_count', 0)
                total_val = row.get('total_count', 0)
                pre_count = int(pre_val) if pd.notna(pre_val) else 0
                post_count = int(post_val) if pd.notna(post_val) else 0
                total_count = int(total_val) if pd.notna(total_val) else 0
                print(f"     {row['feature']:40s} | Pre: {pre_ratio_pct:5.1f}% | Post: {post_ratio_pct:5.1f}% | Pre: {pre_count:4d} | Post: {post_count:4d} | Total: {total_count:4d}")
            if len(predictive_features) > 20:
                print(f"     ... and {len(predictive_features) - 20} more")
            print(f"   {'='*80}")
        
        # Show summary statistics
        print(f"\n   Summary Statistics:")
        if pre_ratio_col in results_df.columns:
            print(f"     Mean pre-{target_name} ratio: {results_df[pre_ratio_col].mean():.2%}")
            print(f"     Median pre-{target_name} ratio: {results_df[pre_ratio_col].median():.2%}")
        print(f"     Mean post-{target_name} ratio: {results_df[ratio_col].mean():.2%}")
        print(f"     Median post-{target_name} ratio: {results_df[ratio_col].median():.2%}")
        print(f"     Features with post-ratio > 50%: {(results_df[ratio_col] > 0.5).sum()}")
        print(f"     Features with post-ratio > 80%: {(results_df[ratio_col] > 0.8).sum()}")
        print(f"     Features with post-ratio > 90%: {(results_df[ratio_col] > 0.9).sum()}")
        if pre_ratio_col in results_df.columns:
            print(f"     Features with pre-ratio > 80%: {(results_df[pre_ratio_col] > 0.8).sum()}")
    else:
        # Fallback display if ratio columns are absent.
        leakage_features = results_df[results_df['is_post_target_leakage'] == 1]
        if len(leakage_features) > 0:
            print(f"\n   Sample post-target leakage features (first 10):")
            for feature in leakage_features['feature'].head(10):
                print(f"     - {feature}")
            if len(leakage_features) > 10:
                print(f"     ... and {len(leakage_features) - 10} more")


if __name__ == "__main__":
    main()
