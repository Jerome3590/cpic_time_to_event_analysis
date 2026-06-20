"""
Phase 4: Complete Pipeline with DuckDB optimizations.

Final QA validation and save outputs to S3.
Optionally trigger a separate QA notebook via papermill for additional validations.
"""

from .common import (
    datetime,
    SYMBOLS,
    cleanup_duckdb_temp_files,
    enable_query_profiling,
    disable_query_profiling,
    force_checkpoint,
    monitor_disk_space,
    ensure_gold_views,
    ensure_unified_views,
    ensure_cohort_views,
)
from py_helpers.constants import get_falls_target_icd_sql_condition
import os
import subprocess
import shutil
from pathlib import Path
from py_helpers.env_utils import get_project_data_root, is_linux


CANONICAL_COHORT_COLUMNS = [
    ("mi_person_key", "VARCHAR"),
    ("event_date", "TIMESTAMP"),
    ("event_type", "VARCHAR"),
    ("data_source", "VARCHAR"),
    ("age_imputed", "INTEGER"),
    ("member_gender", "VARCHAR"),
    ("member_race", "VARCHAR"),
    ("zip_imputed", "VARCHAR"),
    ("county_imputed", "VARCHAR"),
    ("payer_imputed", "VARCHAR"),
    ("primary_icd_diagnosis_code", "VARCHAR"),
    ("two_icd_diagnosis_code", "VARCHAR"),
    ("three_icd_diagnosis_code", "VARCHAR"),
    ("four_icd_diagnosis_code", "VARCHAR"),
    ("five_icd_diagnosis_code", "VARCHAR"),
    ("six_icd_diagnosis_code", "VARCHAR"),
    ("seven_icd_diagnosis_code", "VARCHAR"),
    ("eight_icd_diagnosis_code", "VARCHAR"),
    ("nine_icd_diagnosis_code", "VARCHAR"),
    ("ten_icd_diagnosis_code", "VARCHAR"),
    ("two_icd_procedure_code", "VARCHAR"),
    ("three_icd_procedure_code", "VARCHAR"),
    ("four_icd_procedure_code", "VARCHAR"),
    ("five_icd_procedure_code", "VARCHAR"),
    ("six_icd_procedure_code", "VARCHAR"),
    ("seven_icd_procedure_code", "VARCHAR"),
    ("eight_icd_procedure_code", "VARCHAR"),
    ("nine_icd_procedure_code", "VARCHAR"),
    ("ten_icd_procedure_code", "VARCHAR"),
    ("drug_name", "VARCHAR"),
    ("therapeutic_class_1", "VARCHAR"),
    ("procedure_code", "VARCHAR"),
    ("cpt_mod_1_code", "VARCHAR"),
    ("cpt_mod_2_code", "VARCHAR"),
    ("hcg_setting", "VARCHAR"),
    ("hcg_line", "VARCHAR"),
    ("hcg_detail", "VARCHAR"),
    ("event_classification", "VARCHAR"),
    ("event_sequence", "BIGINT"),
    ("target", "INTEGER"),
    ("cohort_name", "VARCHAR"),
    ("cohort", "VARCHAR"),
    ("is_target_case", "INTEGER"),
    ("first_falls_date", "TIMESTAMP"),
    ("first_ed_date", "TIMESTAMP"),
    ("days_to_target_event", "BIGINT"),
]


def _cast_column_or_null(column_names: set[str], column_name: str, sql_type: str) -> str:
    if column_name in column_names:
        return f"CAST({column_name} AS {sql_type}) AS {column_name}"
    return f"CAST(NULL AS {sql_type}) AS {column_name}"


def _normalize_cohort_table_schema(cohort_conn_duckdb, logger, table_name: str, cohort_name: str) -> None:
    """Normalize a cohort table to a stable parquet schema before S3 write."""
    schema_df = cohort_conn_duckdb.sql(f"""
    SELECT column_name
    FROM information_schema.columns
    WHERE table_schema = 'main'
      AND table_name = '{table_name}'
    """).fetchdf()
    column_names = set(schema_df["column_name"].tolist()) if not schema_df.empty else set()
    if not column_names:
        raise Exception(f"Cannot normalize missing cohort table: {table_name}")

    select_exprs = []
    for column_name, sql_type in CANONICAL_COHORT_COLUMNS:
        if column_name == "target":
            if "is_target_case" in column_names:
                select_exprs.append("CAST(is_target_case AS INTEGER) AS target")
            else:
                select_exprs.append(_cast_column_or_null(column_names, column_name, sql_type))
        elif column_name == "cohort_name":
            select_exprs.append(f"'{cohort_name}' AS cohort_name")
        elif column_name == "first_ed_date":
            if "first_ed_date_1" in column_names:
                select_exprs.append("CAST(first_ed_date_1 AS TIMESTAMP) AS first_ed_date")
            else:
                select_exprs.append(_cast_column_or_null(column_names, column_name, sql_type))
        else:
            select_exprs.append(_cast_column_or_null(column_names, column_name, sql_type))

    normalized_table = f"{table_name}__normalized"
    select_sql = ",\n        ".join(select_exprs)
    cohort_conn_duckdb.sql(f"""
    CREATE OR REPLACE TABLE {normalized_table} AS
    SELECT
        {select_sql}
    FROM {table_name}
    """)
    cohort_conn_duckdb.sql(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM {normalized_table}")
    cohort_conn_duckdb.sql(f"DROP TABLE IF EXISTS {normalized_table}")
    logger.info(
        f"--> [PHASE 4] Normalized {table_name} schema "
        f"({len(CANONICAL_COHORT_COLUMNS)} columns, target=is_target_case)"
    )


def run_phase4_complete_pipeline(context):
    """Phase 4: Complete Pipeline with DuckDB optimizations."""
    logger = context["logger"]
    cohort_conn_duckdb = context["cohort_conn_duckdb"]
    age_band = context["age_band"]
    event_year = context["event_year"]
    requested_cohort = context.get("cohort", "both")
    pipeline_state = context.get("pipeline_state")
    
    step_name = "phase4_complete_pipeline"
    
    # Check if step already completed
    if pipeline_state and pipeline_state.is_step_completed(step_name):
        logger.info(f"{SYMBOLS['success']} [PHASE 4] Already completed - skipping")
        return
    
    logger.info(f"{SYMBOLS['arrow']} [PHASE 4] Starting optimized complete pipeline execution...")
    
    try:
        # Ensure required views exist if earlier phases were skipped
        ensure_gold_views(cohort_conn_duckdb, logger, age_band, event_year)
        ensure_unified_views(cohort_conn_duckdb, logger)
        if requested_cohort == "both":
            ensure_cohort_views(cohort_conn_duckdb, logger)
        
        # Note: We now write to local NVMe first, then use aws s3 sync
        # This is faster and more reliable than DuckDB's direct S3 COPY
        logger.info("--> [PHASE 4] Using local staging + aws s3 sync for cohort uploads (faster and more reliable)")
        
        # Enable query profiling with partition-safe filename (prevents overwrite in parallel runs)
        import time
        profile_filename = f"/tmp/duckdb_profiling_phase4_{age_band.replace('-', '_')}_{event_year}_{int(time.time())}.json"
        enable_query_profiling(cohort_conn_duckdb, logger, "json", profile_filename)
        
        # Cache AWS CLI discovery once (micro-optimization: avoid repeated PATH lookups)
        # Use full path to AWS CLI on EC2
        aws_cli = "/usr/local/bin/aws"
        if not Path(aws_cli).exists():
            # Fallback to PATH lookup if full path doesn't exist
            aws_cli = shutil.which("aws")
            if not aws_cli:
                logger.error("[X] [PHASE 4] AWS CLI not found, cannot sync to S3")
                raise Exception("AWS CLI not available")
        
        # Monitor disk space BEFORE writing Parquet (early warning for NVMe exhaustion)
        monitor_disk_space(logger)
        
        # Final QA validation
        logger.info("--> [PHASE 4] Performing final QA validation...")
        
        # HIGH-IMPACT FIX #1: Check cohort views exist (not just row counts)
        # This prevents silent partial pipeline success if views are missing
        # Use fetchdf() for consistency (though these counts are small)
        required_views = []
        if requested_cohort in ("falls", "both"):
            required_views.append("falls_cohort")
        if requested_cohort in ("ed", "both"):
            required_views.append("ed_cohort")

        missing_views = []
        view_exists_sql = {
            "falls_cohort": "SELECT COUNT(*) AS count FROM information_schema.tables WHERE table_schema = 'main' AND table_name = 'falls_cohort'",
            "ed_cohort": "SELECT COUNT(*) AS count FROM information_schema.tables WHERE table_schema = 'main' AND table_name = 'ed_cohort'",
        }
        for view_name in required_views:
            check_df = cohort_conn_duckdb.sql(view_exists_sql[view_name]).fetchdf()
            view_count = int(check_df.iloc[0]['count']) if not check_df.empty else 0
            if view_count == 0:
                missing_views.append(view_name)

        if missing_views:
            logger.error(f"[X] [PHASE 4] Missing cohort views: {missing_views}")
            raise Exception(f"Cohort views missing: {missing_views}. Phase 3 may have failed silently.")

        if requested_cohort in ("falls", "both"):
            _normalize_cohort_table_schema(cohort_conn_duckdb, logger, "falls_cohort", "falls")
        if requested_cohort in ("ed", "both"):
            _normalize_cohort_table_schema(cohort_conn_duckdb, logger, "ed_cohort", "ed")
        
        # Check both cohorts exist and get patient counts
        # CRITICAL: Use COUNT(DISTINCT mi_person_key) instead of COUNT(*) to avoid row explosion issues
        # Event-level COUNT(*) can explode to billions of rows due to multiple time windows
        # Patient-level counts are stable and prevent INT32 overflow
        # Use fetchdf() to avoid Python connector's INT32 casting issue
        if requested_cohort in ("falls", "both"):
            falls_count_df = cohort_conn_duckdb.sql("SELECT CAST(COUNT(DISTINCT mi_person_key) AS BIGINT) AS count FROM falls_cohort").fetchdf()
            falls_count = int(falls_count_df.iloc[0]['count']) if not falls_count_df.empty else 0
        else:
            falls_count = 0
        
        if requested_cohort in ("ed", "both"):
            ed_count_df = cohort_conn_duckdb.sql("SELECT CAST(COUNT(DISTINCT mi_person_key) AS BIGINT) AS count FROM ed_cohort").fetchdf()
            ed_count = int(ed_count_df.iloc[0]['count']) if not ed_count_df.empty else 0
        else:
            ed_count = 0
        
        if requested_cohort in ("falls", "both"):
            logger.info(f"--> [PHASE 4] QA: FALLS cohort patients: {falls_count:,}")
        else:
            logger.info("--> [PHASE 4] Skipping FALLS QA/write for ed-only run")
            cohort_conn_duckdb.sql("CREATE OR REPLACE TEMP VIEW falls_cohort AS SELECT * FROM ed_cohort WHERE 1=0")
        if requested_cohort in ("ed", "both"):
            logger.info(f"--> [PHASE 4] QA: ED cohort patients: {ed_count:,}")
        else:
            logger.info("--> [PHASE 4] Skipping ED QA/write for falls-only run")
            cohort_conn_duckdb.sql("CREATE OR REPLACE TEMP VIEW ed_cohort AS SELECT * FROM falls_cohort WHERE 1=0")
        
        # Cohort-specific QA checks
        # FALLS cohort: Check falls target ICD condition - all 10 ICD columns
        # ED cohort: Check HCG target events (ed cohort target)
        opioid_icd_condition = get_falls_target_icd_sql_condition()
        
        # FALLS: target ICD check (all 10 ICD diagnosis columns)
        # Use fetchdf() to avoid INT32 overflow in COUNT queries
        f1120_opioid_final_df = cohort_conn_duckdb.sql(f"""
        SELECT 
            CAST(COUNT(*) AS BIGINT) as total_f1120_records,
            CAST(COUNT(DISTINCT mi_person_key) AS BIGINT) as distinct_f1120_patients
        FROM falls_cohort
        WHERE {opioid_icd_condition}
        """).fetchdf()
        f1120_opioid_final = (
            int(f1120_opioid_final_df.iloc[0]['total_f1120_records']) if not f1120_opioid_final_df.empty and f1120_opioid_final_df.iloc[0]['total_f1120_records'] is not None else 0,
            int(f1120_opioid_final_df.iloc[0]['distinct_f1120_patients']) if not f1120_opioid_final_df.empty and f1120_opioid_final_df.iloc[0]['distinct_f1120_patients'] is not None else 0
        )
        
        # ED: HCG target events check (ed cohort)
        # Check for HCG line codes and details used to identify ED visits
        # Use hcg_detail for precision: P51b = ED Visits (exclude P51a = Observation Care)
        # Also check that target cases have drug events (pharmacy events) - matches Phase 3 logic
        hcg_condition = """
            (hcg_line = 'P51 - ER Visits and Observation Care' AND hcg_detail = 'P51b - PHY ED Visits and Observation Care - ED Visits')
            OR hcg_line = 'O11 - Emergency Room'
            OR hcg_line = 'P33 - Urgent Care Visits'
        """
        
        # Use fetchdf() to avoid INT32 overflow in COUNT queries
        hcg_ed_final_df = cohort_conn_duckdb.sql(f"""
        SELECT 
            CAST(COUNT(*) AS BIGINT) as total_hcg_records,
            CAST(COUNT(DISTINCT mi_person_key) AS BIGINT) as distinct_hcg_patients,
            CAST(COUNT(DISTINCT CASE WHEN is_target_case = 1 THEN mi_person_key END) AS BIGINT) as hcg_target_patients,
            CAST(COUNT(DISTINCT CASE WHEN event_type = 'pharmacy' AND is_target_case = 1 THEN mi_person_key END) AS BIGINT) as hcg_target_patients_with_drugs
        FROM ed_cohort
        WHERE {hcg_condition}
        """).fetchdf()
        hcg_ed_final = (
            int(hcg_ed_final_df.iloc[0]['total_hcg_records']) if not hcg_ed_final_df.empty and hcg_ed_final_df.iloc[0]['total_hcg_records'] is not None else 0,
            int(hcg_ed_final_df.iloc[0]['distinct_hcg_patients']) if not hcg_ed_final_df.empty and hcg_ed_final_df.iloc[0]['distinct_hcg_patients'] is not None else 0,
            int(hcg_ed_final_df.iloc[0]['hcg_target_patients']) if not hcg_ed_final_df.empty and hcg_ed_final_df.iloc[0]['hcg_target_patients'] is not None else 0,
            int(hcg_ed_final_df.iloc[0]['hcg_target_patients_with_drugs']) if not hcg_ed_final_df.empty and hcg_ed_final_df.iloc[0]['hcg_target_patients_with_drugs'] is not None else 0
        )
        
        logger.info(f"--> [PHASE 4] FALLS COHORT QA (target ICD - all ICD columns):")
        logger.info(f"  Total target ICD records: {f1120_opioid_final[0]:,}")
        logger.info(f"  Distinct target ICD patients: {f1120_opioid_final[1]:,}")
        
        logger.info(f"--> [PHASE 4] ED COHORT QA (HCG target events - ed cohort):")
        logger.info(f"  Total HCG records: {hcg_ed_final[0]:,}")
        logger.info(f"  Distinct HCG patients: {hcg_ed_final[1]:,}")
        logger.info(f"  HCG target patients: {hcg_ed_final[2]:,}")
        logger.info(f"  HCG target patients with drug events: {hcg_ed_final[3]:,}")
        
        # Verify is_target_case column exists in ED cohort
        logger.info("--> [PHASE 4] ED COHORT QA (Schema validation - target case column):")
        schema_check_df = cohort_conn_duckdb.sql("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'ed_cohort'
        ORDER BY column_name
        """).fetchdf()
        schema_columns = schema_check_df['column_name'].tolist() if not schema_check_df.empty else []
        
        required_column = 'is_target_case'
        if required_column not in schema_columns:
            logger.error(f"[X] [PHASE 4] ED cohort missing required column: {required_column}")
            logger.error(f"   All available columns: {schema_columns}")
            raise Exception(f"ED cohort table missing required target case column: {required_column}. Phase 3 may have failed to create this column.")
        else:
            logger.info(f"[1] Required target case column present: {required_column}")
            
            # Log counts for target case column to verify it's populated
            try:
                target_counts_df = cohort_conn_duckdb.sql("""
                SELECT 
                    CAST(COUNT(CASE WHEN is_target_case = 1 THEN 1 END) AS BIGINT) as target_cases,
                    CAST(COUNT(CASE WHEN is_target_case = 0 THEN 1 END) AS BIGINT) as control_cases,
                    CAST(COUNT(*) AS BIGINT) as total_cases
                FROM ed_cohort
                """).fetchdf()
                if not target_counts_df.empty:
                    counts = target_counts_df.iloc[0]
                    logger.info(f"  Target case distribution (21-day window):")
                    logger.info(f"    Target cases: {int(counts['target_cases']):,}")
                    logger.info(f"    Control cases: {int(counts['control_cases']):,}")
                    logger.info(f"    Total: {int(counts['total_cases']):,}")
            except Exception as e:
                logger.warning(f"[WARN] Could not calculate target case counts: {e}")
        
        # Warn if cohorts are empty
        if requested_cohort in ("falls", "both") and falls_count == 0:
            logger.warning(f"[WARN] [PHASE 4] WARNING: FALLS cohort is empty for {age_band}/{event_year}")
        if requested_cohort in ("ed", "both") and ed_count == 0:
            logger.warning(f"[WARN] [PHASE 4] WARNING: ED cohort is empty for {age_band}/{event_year}")
        
        # Save cohorts: Write to local NVMe first, then sync to S3
        from py_helpers.s3_utils import get_cohort_parquet_path
        # Determine local staging directory (prefer NVMe on Linux)
        if is_linux():
            local_staging = get_project_data_root() / "cohorts_staging"
        else:
            # Windows fallback
            local_staging = Path(os.path.join(os.path.expanduser("~"), "cpic_time_to_event", "cohorts_staging"))
        local_staging.mkdir(parents=True, exist_ok=True)
        
        # Save FALLS cohort (always save, even if control-only)
        falls_s3_path = get_cohort_parquet_path("falls", age_band, event_year)
        falls_local = None
        if requested_cohort not in ("falls", "both"):
            logger.info("--> [PHASE 4] Skipping FALLS cohort save because requested cohort is ed")
        elif falls_count > 0:
            # Write to local NVMe first (much faster)
            falls_local = local_staging / f"falls_{age_band}_{event_year}.parquet"
            logger.info(f"--> [PHASE 4] Writing FALLS cohort ({falls_count:,} patients) to local: {falls_local}")
            cohort_conn_duckdb.sql(f"""
            COPY falls_cohort TO '{falls_local}'
            (FORMAT PARQUET, COMPRESSION SNAPPY)
            """)
            
            # Log file size before upload (helps diagnose timeouts vs IAM/network failures)
            file_size_gb = falls_local.stat().st_size / 1e9
            logger.info(f"--> [PHASE 4] FALLS cohort written to local ({file_size_gb:.2f} GB)")
            
            # Sync to S3 using aws s3 cp (more reliable for large files)
            logger.info(f"--> [PHASE 4] Syncing FALLS cohort to S3: {falls_s3_path}")
            local_file = str(falls_local)
            
            # Use cached AWS CLI (resolved once at top of phase)
            try:
                result = subprocess.run(
                    [aws_cli, "s3", "cp", local_file, falls_s3_path, "--no-progress"],
                    capture_output=True,
                    text=True,
                    timeout=3600  # 1 hour timeout
                )
                if result.returncode == 0:
                    logger.info(f"--> [PHASE 4] FALLS cohort synced to S3 successfully")
                    # Clean up local file after successful sync
                    try:
                        falls_local.unlink()
                        logger.info(f"--> [PHASE 4] Cleaned up local FALLS cohort file")
                        falls_local = None  # Mark as cleaned
                    except Exception as e:
                        logger.warning(f"[WARN] [PHASE 4] Could not clean up local file: {e}")
                else:
                    logger.error(f"[X] [PHASE 4] Failed to sync FALLS cohort to S3: {result.stderr}")
                    # Keep local file for retry/debugging
                    logger.warning(f"[WARN] [PHASE 4] Keeping local file for retry: {falls_local}")
                    raise Exception(f"S3 sync failed: {result.stderr}")
            except subprocess.TimeoutExpired:
                logger.error(f"[X] [PHASE 4] S3 sync timeout for FALLS cohort (exceeded 1 hour)")
                # Keep local file for retry
                logger.warning(f"[WARN] [PHASE 4] Keeping local file for retry: {falls_local}")
                raise
            except FileNotFoundError:
                logger.error(f"[X] [PHASE 4] AWS CLI not found at {aws_cli}, cannot sync to S3")
                raise Exception("AWS CLI not available")
            
            # Check if it's control-only
            # NOTE: 'target' column is legacy and not used in Phase 4 logic
            # Use 'is_target_case' for actual target/control distinction
            # Use patient-level count to avoid row explosion issues
            target_count_check_df = cohort_conn_duckdb.sql("SELECT CAST(COUNT(DISTINCT mi_person_key) AS BIGINT) AS count FROM falls_cohort WHERE is_target_case = 1").fetchdf()
            target_count_check = int(target_count_check_df.iloc[0]['count']) if not target_count_check_df.empty else 0
            if target_count_check == 0:
                logger.info(f"--> [PHASE 4] FALLS cohort saved (CONTROL-ONLY) to S3: {falls_s3_path}")
            else:
                logger.info(f"--> [PHASE 4] FALLS cohort saved to S3: {falls_s3_path}")
        else:
            logger.warning(f"[WARN] [PHASE 4] Skipping save of empty FALLS cohort to {falls_s3_path}")

        # Optional: run QA notebook for falls cohort if configured
        qa_nb = os.environ.get("PGX_QA_NOTEBOOK")
        if qa_nb and requested_cohort in ("falls", "both"):
            try:
                out_nb = f"/tmp/Cohort_QA_falls_{age_band}_{event_year}.ipynb"
                cmd = [
                    "papermill", qa_nb, out_nb,
                    "-p", "cohort_name", "falls",
                    "-p", "cohort_parquet_path", falls_s3_path,
                    "-p", "age_band", str(age_band),
                    "-p", "event_year", str(event_year),
                ]
                logger.info(f"--> [PHASE 4] Running QA notebook: {' '.join(cmd)}")
                subprocess.run(cmd, check=True)
                logger.info(f"[1] QA notebook completed: {out_nb}")
            except Exception as nb_e:
                logger.warning(f"[WARN] QA notebook failed for falls: {nb_e}")
        
        # Save ED cohort (always save, even if control-only)
        ed_s3_path = get_cohort_parquet_path("ed", age_band, event_year)
        ed_local = None
        if requested_cohort not in ("ed", "both"):
            logger.info("--> [PHASE 4] Skipping ED cohort save because requested cohort is falls")
        elif ed_count > 0:
            # Write to local NVMe first (much faster, especially for large cohorts)
            ed_local = local_staging / f"ed_{age_band}_{event_year}.parquet"
            logger.info(f"--> [PHASE 4] Writing ED cohort ({ed_count:,} patients) to local: {ed_local}")
            cohort_conn_duckdb.sql(f"""
            COPY ed_cohort TO '{ed_local}'
            (FORMAT PARQUET, COMPRESSION SNAPPY)
            """)
            
            # Log file size before upload (helps diagnose timeouts vs IAM/network failures)
            file_size_gb = ed_local.stat().st_size / 1e9
            logger.info(f"--> [PHASE 4] ED cohort written to local ({file_size_gb:.2f} GB)")
            
            # Sync to S3 using aws s3 cp (more reliable for large files, can resume on failure)
            logger.info(f"--> [PHASE 4] Syncing ED cohort to S3: {ed_s3_path}")
            local_file = str(ed_local)
            
            # Use cached AWS CLI (resolved once at top of phase)
            try:
                result = subprocess.run(
                    [aws_cli, "s3", "cp", local_file, ed_s3_path, "--no-progress"],
                    capture_output=True,
                    text=True,
                    timeout=7200  # 2 hour timeout for very large cohorts
                )
                if result.returncode == 0:
                    logger.info(f"--> [PHASE 4] ED cohort synced to S3 successfully")
                    # Clean up local file after successful sync
                    try:
                        ed_local.unlink()
                        logger.info(f"--> [PHASE 4] Cleaned up local ED cohort file")
                        ed_local = None  # Mark as cleaned
                    except Exception as e:
                        logger.warning(f"[WARN] [PHASE 4] Could not clean up local file: {e}")
                else:
                    logger.error(f"[X] [PHASE 4] Failed to sync ED cohort to S3: {result.stderr}")
                    # Keep local file for retry/debugging
                    logger.warning(f"[WARN] [PHASE 4] Keeping local file for retry: {ed_local}")
                    raise Exception(f"S3 sync failed: {result.stderr}")
            except subprocess.TimeoutExpired:
                logger.error(f"[X] [PHASE 4] S3 sync timeout for ED cohort (exceeded 2 hours)")
                # Keep local file for retry
                logger.warning(f"[WARN] [PHASE 4] Keeping local file for retry: {ed_local}")
                raise
            except FileNotFoundError:
                logger.error(f"[X] [PHASE 4] AWS CLI not found at {aws_cli}, cannot sync to S3")
                raise Exception("AWS CLI not available")
            
            # Check if it's control-only
            # NOTE: 'target' column is legacy and not used in Phase 4 logic
            # Use 'is_target_case' for actual target/control distinction
            # Use patient-level count to avoid row explosion issues
            target_count_check_df = cohort_conn_duckdb.sql("SELECT CAST(COUNT(DISTINCT mi_person_key) AS BIGINT) AS count FROM ed_cohort WHERE is_target_case = 1").fetchdf()
            target_count_check = int(target_count_check_df.iloc[0]['count']) if not target_count_check_df.empty else 0
            if target_count_check == 0:
                logger.info(f"--> [PHASE 4] ED cohort saved (CONTROL-ONLY) to S3: {ed_s3_path}")
            else:
                logger.info(f"--> [PHASE 4] ED cohort saved to S3: {ed_s3_path}")
        else:
            logger.warning(f"[WARN] [PHASE 4] Skipping save of empty ED cohort to {ed_s3_path}")

        # Optional: run QA notebook for ed cohort if configured
        qa_nb = os.environ.get("PGX_QA_NOTEBOOK")
        if qa_nb and requested_cohort in ("ed", "both"):
            try:
                out_nb = f"/tmp/Cohort_QA_ed_{age_band}_{event_year}.ipynb"
                cmd = [
                    "papermill", qa_nb, out_nb,
                    "-p", "cohort_name", "ed",
                    "-p", "cohort_parquet_path", ed_s3_path,
                    "-p", "age_band", str(age_band),
                    "-p", "event_year", str(event_year),
                ]
                logger.info(f"--> [PHASE 4] Running QA notebook: {' '.join(cmd)}")
                subprocess.run(cmd, check=True)
                logger.info(f"[1] QA notebook completed: {out_nb}")
            except Exception as nb_e:
                logger.warning(f"[WARN] QA notebook failed for ed: {nb_e}")
        
        # Final cleanup
        cleanup_duckdb_temp_files(logger)
        
        # Clean up staging directory if empty (all files successfully uploaded and removed)
        try:
            if local_staging.exists():
                # Check if staging directory is empty
                remaining_files = list(local_staging.glob("*.parquet"))
                if not remaining_files:
                    # Directory is empty, but keep it for future use (no need to remove)
                    logger.debug(f"--> [PHASE 4] Staging directory is empty: {local_staging}")
                else:
                    logger.warning(f"[WARN] [PHASE 4] Staging directory still contains {len(remaining_files)} file(s): {[f.name for f in remaining_files]}")
        except Exception as e:
            logger.warning(f"[WARN] [PHASE 4] Could not check staging directory: {e}")
        
        # Monitor disk space at end (already monitored before writes)
        monitor_disk_space(logger)
        
        # Force checkpoint
        force_checkpoint(cohort_conn_duckdb, logger)
        
        # Disable query profiling
        disable_query_profiling(cohort_conn_duckdb, logger)
        
        # Save checkpoint
        if pipeline_state:
            pipeline_state.mark_step_completed(step_name, {
                'falls_count': falls_count,
                'ed_count': ed_count,
                'timestamp': datetime.now().isoformat()
            })
        
        logger.info(f"{SYMBOLS['success']} [PHASE 4] Optimized complete pipeline execution finished")
        
    except Exception as e:
        logger.error(f"{SYMBOLS['fail']} [PHASE 4] Complete pipeline execution failed: {str(e)}")
        
        # Clean up any remaining local files on error (optional - comment out to keep for debugging)
        # Note: Files are kept by default for retry/debugging, but can be cleaned up if desired
        try:
            if 'falls_local' in locals() and falls_local and falls_local.exists():
                logger.warning(f"[WARN] [PHASE 4] Local FALLS file remains: {falls_local} (kept for retry/debugging)")
            if 'ed_local' in locals() and ed_local and ed_local.exists():
                logger.warning(f"[WARN] [PHASE 4] Local ED file remains: {ed_local} (kept for retry/debugging)")
        except Exception:
            pass
        
        if pipeline_state:
            pipeline_state.mark_step_failed(step_name, str(e))
        cleanup_duckdb_temp_files(logger)
        raise

