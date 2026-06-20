#!/usr/bin/env python3
"""
Create model_events.parquet for control cohort (BupaR analysis).

This script creates model_events.parquet for the control cohort used in BupaR analysis.
For each cohort (falls or ed), the control cohort consists of patients who:
- Are in the same age band as the target cohort
- Do NOT appear in the target cohort parquet (not a case patient)
- Have medical or pharmacy events in the analysis period

This is a simplified version that only creates control events (target=0).
"""

import os
import sys
from pathlib import Path
from typing import List, Optional

import duckdb

# Add project root and 4_model_data to path (for get_important_items from create_model_data)
PROJECT_ROOT = Path(__file__).parent.parent
MODEL_DATA_DIR = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(MODEL_DATA_DIR) not in sys.path:
    sys.path.insert(0, str(MODEL_DATA_DIR))

from py_helpers.constants import (
    ALL_ICD_DIAGNOSIS_COLUMNS,
    get_cohort_slug_by_cohort,
    get_physical_age_bands_for_medical_pharmacy,
    age_band_partition_candidates,
)
from py_helpers.env_utils import get_data_root, get_model_data_root
from py_helpers.feature_importance_eda_utils import load_administrative_codes

# get_important_items from create_model_data (same as target cohort filter)
from create_model_data import get_important_items


def resolve_local_medical_root() -> Path:
    """
    Resolve the root directory containing gold medical parquet files.
    
    Priority:
      1. LOCAL_MEDICAL_PATH environment variable
      2. get_data_root()/gold/medical (Linux/EC2: /mnt/nvme/gold/medical)
      3. get_data_root()/data/gold_medical (Alternative Linux path)
      4. PROJECT_ROOT/data/gold_medical (Windows/local dev)
    """
    env_path = os.getenv("LOCAL_MEDICAL_PATH")
    if env_path:
        root = Path(env_path)
        if root.exists():
            return root
    
    # OS-aware path resolution
    data_root = get_data_root()
    candidates = [
        data_root / "gold" / "medical",  # Linux/EC2: /mnt/nvme/gold/medical
        data_root / "data" / "gold_medical",  # Alternative Linux path
        PROJECT_ROOT / "data" / "gold_medical",  # Windows/local dev
    ]
    
    # Return first existing path, or default to project root if none exists
    for path in candidates:
        if path.exists():
            return path
    
    return candidates[2]  # Default to project root


def resolve_local_pharmacy_root() -> Path:
    """
    Resolve the root directory containing gold pharmacy parquet files.
    
    Priority:
      1. LOCAL_PHARMACY_PATH environment variable
      2. get_data_root()/gold/pharmacy (Linux/EC2: /mnt/nvme/gold/pharmacy)
      3. get_data_root()/data/gold_pharmacy (Alternative Linux path)
      4. PROJECT_ROOT/data/gold_pharmacy (Windows/local dev)
    """
    env_path = os.getenv("LOCAL_PHARMACY_PATH")
    if env_path:
        root = Path(env_path)
        if root.exists():
            return root
    
    # OS-aware path resolution
    data_root = get_data_root()
    candidates = [
        data_root / "gold" / "pharmacy",  # Linux/EC2: /mnt/nvme/gold/pharmacy
        data_root / "data" / "gold_pharmacy",  # Alternative Linux path
        PROJECT_ROOT / "data" / "gold_pharmacy",  # Windows/local dev
    ]
    
    # Return first existing path, or default to project root if none exists
    for path in candidates:
        if path.exists():
            return path
    
    return candidates[2]  # Default to project root


def _item_filter_condition_sql(important_items: List[str]) -> str:
    """Build SQL WHERE condition for event-level filter (drug_name, ICD cols, procedure_code). Same logic as create_model_data.filter_cohort_events_for_items."""
    if not important_items:
        return "TRUE"
    item_list_literal = ", ".join(f"'{v}'" for v in important_items)
    icd_conditions = " OR ".join(
        f"{col} IN ({item_list_literal})" for col in ALL_ICD_DIAGNOSIS_COLUMNS
    )
    if not icd_conditions:
        icd_conditions = "FALSE"
    return f"""(
        drug_name IN ({item_list_literal}) OR
        {icd_conditions} OR
        procedure_code IN ({item_list_literal})
    )"""


def create_control_cohort_model_data(
    age_band: str,
    cohort_name: str = "falls",
    years: List[int] = [2016, 2017, 2018],
    sample_size: int = 10000,
    output_root: Path = None,
    target_cohort_path: Path = None,
    aggregated_fi_csv: Optional[Path] = None,
) -> None:
    """
    Create model_events.parquet for control cohort (BupaR analysis).

    Controls are patients in the same age band who are NOT in the target cohort case set.

    Optionally filter control events to the same feature set as target (3a aggregated FI
    minus admin codes) to reduce noise in BupaR analysis.

    Args:
        age_band: Age band (e.g., "65-74")
        cohort_name: Cohort name ("falls" or "ed")
        years: List of years to include
        sample_size: Number of control patients to sample
        output_root: Root directory for output (default: get_model_data_root())
        target_cohort_path: Optional path to target cohort parquet for case exclusion
        aggregated_fi_csv: Path to 3a aggregated feature importance CSV; control events are filtered
            to the same items (with admin codes removed) as target. Required when output_root is set (Step 3b).
    """
    if output_root is None:
        output_root = get_model_data_root()
    
    important_items: List[str] = []
    if aggregated_fi_csv and aggregated_fi_csv.exists():
        important_items = get_important_items(aggregated_fi_csv)
        admin_codes = load_administrative_codes(PROJECT_ROOT)
        if admin_codes:
            n_before = len(important_items)
            important_items = [x for x in important_items if x not in admin_codes]
            if n_before > len(important_items):
                print(f"[INFO] Filtering control events by 3a FI (admin removed): {len(important_items)} items")
        if not important_items:
            important_items = []
    item_filter_sql = _item_filter_condition_sql(important_items)
    
    local_medical_root = resolve_local_medical_root()
    local_pharmacy_root = resolve_local_pharmacy_root()
    
    cohort_name = cohort_name or "falls"
    
    # Build paths to medical and pharmacy parquet files.
    medical_parquet_paths = []
    pharmacy_parquet_paths = []
    medical_pharmacy_bands = get_physical_age_bands_for_medical_pharmacy(age_band)

    for year in years:
        for physical in medical_pharmacy_bands:
            for part in age_band_partition_candidates(physical):
                medical_parent = local_medical_root / f"age_band={part}" / f"event_year={year}"
                pharmacy_parent = local_pharmacy_root / f"age_band={part}" / f"event_year={year}"
                if medical_parent.exists():
                    medical_parquet_paths.extend(medical_parent.glob("*.parquet"))
                if pharmacy_parent.exists():
                    pharmacy_parquet_paths.extend(pharmacy_parent.glob("*.parquet"))
    
    if not medical_parquet_paths and not pharmacy_parquet_paths:
        print(f"[ERROR] No medical or pharmacy files found for age_band={age_band}")
        print(f"  Medical root: {local_medical_root}")
        print(f"  Pharmacy root: {local_pharmacy_root}")
        return
    
    print(f"[INFO] Found {len(medical_parquet_paths)} medical files and {len(pharmacy_parquet_paths)} pharmacy files")
    
    control_slug = get_cohort_slug_by_cohort(cohort_name)

    # When writing under 3b/outputs use flat layout (cohort_name=.../age_band=...) so R finds it first
    if "3b_feature_importance_eda" in str(output_root) and "outputs" in str(output_root):
        out_dir = output_root / f"cohort_name={control_slug}" / f"age_band={age_band}"
    else:
        out_dir = (
            output_root
            / "cohorts"
            / "input_model_data"
            / f"cohort_name={control_slug}"
            / f"age_band={age_band}"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "model_events.parquet"
    
    # Check if already exists; validate integrity before skipping (guards against partial writes)
    if out_path.exists():
        try:
            _chk = duckdb.connect()
            n_rows = _chk.execute(f"SELECT COUNT(*) FROM read_parquet('{str(out_path).replace(chr(92), '/')}')").fetchone()[0]
            _chk.close()
            if n_rows > 0:
                print(f"[INFO] Control cohort model_events.parquet already exists ({n_rows:,} rows): {out_path}")
                return
            else:
                print(f"[WARN] Existing control model_events.parquet has 0 rows - treating as corrupt, rebuilding.")
                out_path.unlink()
        except Exception as _e:
            print(f"[WARN] Existing control model_events.parquet failed integrity check ({_e}) - rebuilding.")
            try:
                out_path.unlink()
            except Exception:
                pass
    
    con = duckdb.connect()

    # Build query to:
    # 1. Load all medical and pharmacy events
    # 2. Exclude patients already in the target cohort case set
    # 3. Sample control patients
    # 4. Extract all events for sampled controls
    
    medical_paths_literal = ", ".join(f"'{p}'" for p in medical_parquet_paths) if medical_parquet_paths else ""
    pharmacy_paths_literal = ", ".join(f"'{p}'" for p in pharmacy_parquet_paths) if pharmacy_parquet_paths else ""
    
    if not medical_paths_literal or not pharmacy_paths_literal:
        print(f"[ERROR] Both medical and pharmacy files are required")
        return
    
    query = f"""
    WITH     medical_events AS (
        SELECT
            mi_person_key,
            CASE 
                WHEN LENGTH(CAST(incurred_date AS VARCHAR)) = 8 THEN 
                    CAST(SUBSTR(CAST(incurred_date AS VARCHAR), 1, 4) || '-' || 
                         SUBSTR(CAST(incurred_date AS VARCHAR), 5, 2) || '-' || 
                         SUBSTR(CAST(incurred_date AS VARCHAR), 7, 2) AS DATE)
                ELSE CAST(incurred_date AS DATE)
            END AS event_date,  -- Parse YYYYMMDD format to YYYY-MM-DD
            event_year,
            NULL AS drug_name,  -- Medical files don't have drug_name
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
            age_band
        FROM read_parquet([{medical_paths_literal}])
    ),
    pharmacy_events AS (
        SELECT
            mi_person_key,
            CASE 
                WHEN LENGTH(CAST(incurred_date AS VARCHAR)) = 8 THEN 
                    CAST(SUBSTR(CAST(incurred_date AS VARCHAR), 1, 4) || '-' || 
                         SUBSTR(CAST(incurred_date AS VARCHAR), 5, 2) || '-' || 
                         SUBSTR(CAST(incurred_date AS VARCHAR), 7, 2) AS DATE)
                ELSE CAST(incurred_date AS DATE)
            END AS event_date,  -- Parse YYYYMMDD format to YYYY-MM-DD
            event_year,
            drug_name,  -- Pharmacy files have drug_name
            NULL AS primary_icd_diagnosis_code,
            NULL AS two_icd_diagnosis_code,
            NULL AS three_icd_diagnosis_code,
            NULL AS four_icd_diagnosis_code,
            NULL AS five_icd_diagnosis_code,
            NULL AS six_icd_diagnosis_code,
            NULL AS seven_icd_diagnosis_code,
            NULL AS eight_icd_diagnosis_code,
            NULL AS nine_icd_diagnosis_code,
            NULL AS ten_icd_diagnosis_code,
            NULL AS procedure_code,
            age_band
        FROM read_parquet([{pharmacy_paths_literal}])
    ),
    patients_with_drug_events AS (
        -- POLYPHARMACY COHORT: Controls must have drug events (pharmacy events)
        -- This ensures controls have drug events, matching the polypharmacy cohort's focus on drug sequences
        SELECT DISTINCT mi_person_key
        FROM pharmacy_events
    ),
    case_patients AS (
        -- Patients already in the target cohort case set (to exclude from controls)
        SELECT DISTINCT mi_person_key
        FROM read_parquet([{cohort_paths_literal}])
        WHERE is_target_case = 1
    ),
    all_patients AS (
        SELECT DISTINCT mi_person_key FROM patients_with_drug_events
    ),
    control_candidates AS (
        -- Exclude case patients; remaining are eligible controls
        SELECT ap.mi_person_key
        FROM all_patients ap
        LEFT JOIN case_patients cp ON ap.mi_person_key = cp.mi_person_key
        WHERE cp.mi_person_key IS NULL
    ),
    sampled_controls AS (
        SELECT mi_person_key
        FROM control_candidates
        ORDER BY random()
        LIMIT {sample_size}
    ),
    final_unified_events AS (
        -- Get ALL events (medical + pharmacy) for sampled controls
        -- Medical events: Include all medical events for sampled controls (if they have any)
        SELECT
            me.*
        FROM sampled_controls sc
        INNER JOIN medical_events me ON sc.mi_person_key = me.mi_person_key
        UNION ALL
        -- Pharmacy events: Include all pharmacy events for sampled controls
        SELECT
            pe.*
        FROM sampled_controls sc
        INNER JOIN pharmacy_events pe ON sc.mi_person_key = pe.mi_person_key
    )
    SELECT
        fue.*,
        0 AS target
    FROM final_unified_events fue
    WHERE {item_filter_sql}
    """
    
    try:
        cohort_slug = get_cohort_slug_by_cohort(cohort_name)
        print(f"[INFO] Creating control cohort model_events.parquet for {cohort_slug}/{age_band}...")
        print(f"[INFO] Control definition (time window: {time_window_days} days):")
        print(f"[INFO]   - Patients with drug events (pharmacy events)")
        print(f"[INFO]   - Exclude case patients from target cohort")
        print(f"[INFO] Sampling {sample_size} control patients")
        
        # Diagnostic queries to understand where data is being filtered
        print(f"\n[DEBUG] Running diagnostic queries...")
        
        # Check medical events count
        diag_medical = con.execute(f"SELECT COUNT(*) as n FROM read_parquet([{medical_paths_literal}])").fetchone()[0]
        print(f"[DEBUG] Medical events: {diag_medical:,}")
        
        # Check pharmacy events count
        diag_pharmacy = con.execute(f"SELECT COUNT(*) as n FROM read_parquet([{pharmacy_paths_literal}])").fetchone()[0]
        print(f"[DEBUG] Pharmacy events: {diag_pharmacy:,}")
        
        # Check patients with drug events (pharmacy events)
        diag_drug_query = f"""
        SELECT COUNT(DISTINCT mi_person_key) as n
        FROM read_parquet([{pharmacy_paths_literal}])
        """
        diag_drug = con.execute(diag_drug_query).fetchone()[0]
        print(f"[DEBUG] Patients with drug events (pharmacy): {diag_drug:,}")
        
        # Check control candidates count - use same structure as main query (parquet has incurred_date, derive event_date)
        _event_date_sql = """CASE 
                WHEN LENGTH(CAST(incurred_date AS VARCHAR)) = 8 THEN 
                    CAST(SUBSTR(CAST(incurred_date AS VARCHAR), 1, 4) || '-' || SUBSTR(CAST(incurred_date AS VARCHAR), 5, 2) || '-' || SUBSTR(CAST(incurred_date AS VARCHAR), 7, 2) AS DATE)
                ELSE CAST(incurred_date AS DATE)
            END"""
        diag_candidates_simple = f"""
        WITH medical_events AS (
            SELECT mi_person_key, {_event_date_sql} AS event_date, primary_icd_diagnosis_code, two_icd_diagnosis_code,
                   three_icd_diagnosis_code, four_icd_diagnosis_code, five_icd_diagnosis_code,
                   six_icd_diagnosis_code, seven_icd_diagnosis_code, eight_icd_diagnosis_code,
                   nine_icd_diagnosis_code, ten_icd_diagnosis_code, hcg_line
            FROM read_parquet([{medical_paths_literal}])
        ),
        pharmacy_events AS (
            SELECT mi_person_key, {_event_date_sql} AS event_date
            FROM read_parquet([{pharmacy_paths_literal}])
        ),
        patients_with_drug_events AS (
            -- Controls must have drug events (pharmacy events)
            SELECT DISTINCT mi_person_key
            FROM pharmacy_events
        ),
        case_patients_diag AS (
            SELECT DISTINCT mi_person_key
            FROM read_parquet([{cohort_paths_literal}])
            WHERE is_target_case = 1
        ),
        control_candidates AS (
            -- Exclude case patients; remaining with drug events are eligible controls
            SELECT pde.mi_person_key
            FROM patients_with_drug_events pde
            LEFT JOIN case_patients_diag cp ON pde.mi_person_key = cp.mi_person_key
            WHERE cp.mi_person_key IS NULL
        )
        SELECT COUNT(*) as n FROM control_candidates
        """
        try:
            diag_candidates = con.execute(diag_candidates_simple).fetchone()[0]
            print(f"[DEBUG] Control candidates (have drug events, not in case set): {diag_candidates:,}")
            
            # Check if we're trying to sample more than available
            if sample_size > diag_candidates:
                print(f"[WARN] Requested sample size ({sample_size:,}) exceeds available candidates ({diag_candidates:,})")
                print(f"[WARN] Will sample all available candidates ({diag_candidates:,})")
                # Note: SQL LIMIT will automatically cap at available rows, but we log this for visibility
        except Exception as e:
            print(f"[DEBUG] Could not count control candidates: {e}")
        
        print(f"[DEBUG] Diagnostic queries complete.\n")
        
        con.execute(f"COPY ({query}) TO '{out_path}' (FORMAT PARQUET)")
        
        # Validate the created file
        if not out_path.exists():
            raise FileNotFoundError(f"Parquet file was not created: {out_path}")
        
        file_size = out_path.stat().st_size
        if file_size < 1000:  # Parquet files should be at least 1KB
            raise ValueError(f"Created parquet file is too small ({file_size} bytes), likely empty or corrupted")
        
        # Check result by reading the file
        try:
            result_count = con.execute(f"SELECT COUNT(*) FROM read_parquet('{out_path}')").fetchone()[0]
            if result_count == 0:
                raise ValueError(f"Created parquet file contains 0 rows")
            
            # Count distinct patients to verify no duplicates
            distinct_controls = con.execute(f"SELECT COUNT(DISTINCT mi_person_key) FROM read_parquet('{out_path}')").fetchone()[0]
            print(f"[OK] Created control cohort model_events.parquet: {out_path}")
            print(f"[OK] File size: {file_size:,} bytes")
            print(f"[OK] Total events: {result_count:,}")
            print(f"[OK] Distinct controls: {distinct_controls:,}")
            
            # Log ratio if target cohort path is provided
            if target_cohort_path and target_cohort_path.exists():
                years_list = ','.join(map(str, years))
                try:
                    distinct_targets = con.execute(
                        f"SELECT COUNT(DISTINCT mi_person_key) FROM read_parquet('{target_cohort_path}') "
                        f"WHERE event_year IN ({years_list}) AND target = 1"
                    ).fetchone()[0]
                    if distinct_targets > 0:
                        actual_ratio = distinct_controls / distinct_targets
                        print(f"[OK] Distinct targets: {distinct_targets:,}")
                        print(f"[OK] Actual ratio: {actual_ratio:.2f}:1 (controls:targets)")
                    else:
                        print(f"[WARN] No distinct targets found in target cohort")
                except Exception as e:
                    print(f"[WARN] Could not calculate ratio: {e}")
            
            # Warn if we got fewer patients than requested (due to limited candidates)
            if diag_candidates is not None and distinct_controls < sample_size:
                print(f"[WARN] Sampled {distinct_controls:,} patients (requested {sample_size:,})")
                print(f"[WARN] Limited by available control candidates ({diag_candidates:,})")
                print(f"[WARN] This is expected when target cohort is large relative to available controls")
        except Exception as validation_error:
            # If validation fails, remove the corrupted file
            if out_path.exists():
                out_path.unlink()
            raise ValueError(f"Created parquet file is invalid: {validation_error}") from validation_error
        
    except Exception as e:
        print(f"[ERROR] Failed to create control cohort model_events.parquet: {e}")
        # Remove any partially created file
        if out_path.exists():
            try:
                out_path.unlink()
                print(f"[INFO] Removed partially created file: {out_path}")
            except:
                pass
        import traceback
        traceback.print_exc()
        raise  # Re-raise to signal failure
    finally:
        con.close()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Create model_events.parquet for control cohort (patients without target event)"
    )
    parser.add_argument(
        "--age-band",
        type=str,
        required=True,
        help="Age band (e.g., 65-74)",
    )
    parser.add_argument(
        "--years",
        type=int,
        nargs="+",
        default=[2016, 2017, 2018],
        help="Years to include (default: 2016 2017 2018)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=10000,
        help="Number of control patients to sample (default: 10000)",
    )
    parser.add_argument(
        "--output-root",
        type=str,
        default=None,
        help="Root directory for output (default: 4_model_data). Use 3b_feature_importance_eda/outputs for Step 3b so control is not written to 4_model_data.",
    )
    parser.add_argument(
        "--aggregated-fi-csv",
        type=str,
        default=None,
        help="Path to 3a aggregated feature importance CSV; control events are filtered to same items (admin removed). Required when --output-root is set (Step 3b).",
    )
    args = parser.parse_args()
    
    output_root = Path(args.output_root) if args.output_root else None
    aggregated_fi_csv = Path(args.aggregated_fi_csv) if args.aggregated_fi_csv else None
    if output_root is not None and (aggregated_fi_csv is None or not aggregated_fi_csv.exists()):
        raise SystemExit("When --output-root is set (Step 3b), --aggregated-fi-csv is required and must point to an existing 3a aggregated feature importance CSV.")
    create_control_cohort_model_data(
        age_band=args.age_band,
        years=args.years,
        sample_size=args.sample_size,
        output_root=output_root,
        aggregated_fi_csv=aggregated_fi_csv,
    )


if __name__ == "__main__":
    main()
