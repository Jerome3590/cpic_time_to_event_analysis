---
title: Falls cohort troubleshooting TODO
---

# Falls cohort troubleshooting TODO

## Current issue

Phase 3 previously materialized zero falls target patients for `falls/65-74/2016` under the strict same-row falls definition.

The implementation has been updated so dynamic falls runs use the `falls` target label consistently and Phase 3 materializes target patients with the selected patient-level target-window definition.

Observed diagnostic counts from the EC2 run:

- **Injury-prefix patients:** `98,352`
- **External fall-cause-prefix patients:** `122`
- **Same-row falls patients:** `0`
- **Target-condition patients:** `0`
- **Same-patient same-date patients:** `42`
- **Same-patient within 7 days:** `60`
- **Same-patient within 30 days:** `72`

The previous strict target condition required injury-prefix evidence and W00-W19 external fall-cause evidence on the same `unified_event_fact_table` row.

## Working hypothesis

The W00-W19 external fall-cause code may be present on a different claim row from the injury diagnosis, possibly on the same service date or nearby service dates. A simple injury OR external-cause definition is too permissive because it would classify broad injury codes as falls without fall-mechanism evidence.

## Required next steps for research rerun

The current S3 cohort outputs should be treated as stale for published research because QA found two issues:

- Legacy `target` was written as `1` for all rows; downstream should use `is_target_case`, but new outputs should also normalize `target = is_target_case`.
- Some ED partitions were produced by an older combined-run path and have a different row shape/size than newer ED-only outputs.

Required sequence after pushing code to GitHub:

1. Pull latest code on EC2.
2. Run the full reset from `0_config_and_pipeline.ipynb` or directly from shell:

   ```bash
   ./utility_scripts/cleanup_cohort_data.sh --yes --clear-athena-qa
   ```

   For a full recompute beyond cohort/model artifacts, add:

   ```bash
   ./utility_scripts/cleanup_cohort_data.sh --yes --clear-athena-qa --clear-feature-importance
   ```

3. Re-run active notebook `1_cohort_workflow.ipynb`, or run from shell:

   ```bash
   python 2_create_cohort/run_series_falls.py --skip-existing --concurrent-workers 1
   python 2_create_cohort/run_series_ed.py --skip-existing --concurrent-workers 1
   ```

4. Run Athena QA:

   ```bash
   python aws/athena/scripts/run_cohort_qa.py
   ```

5. Continue downstream notebooks only after Athena QA confirms:
   - 8 falls partitions and 8 ED partitions exist.
   - `target_mismatch_rows = 0`.
   - no null `mi_person_key`, null `event_date`, invalid `event_type`, or invalid `is_target_case`.
   - ED target pharmacy rows outside 1-21 days = 0.
   - control-to-target patient ratios are documented, especially where below 5:1 due to limited controls.

## Selected correction logic

Define falls as same patient with injury-prefix and W00-W19 evidence within +/- 7 days by default (`CPIC_FALL_TARGET_WINDOW_DAYS=7`). This preserves mechanism-confirmed falls while allowing injury and external-cause codes to arrive on separate claim rows.

Avoid changing to a simple OR unless the cohort is explicitly redefined as a broad injury proxy rather than falls.

## Implemented code changes

- `py_helpers/constants.py`
  - `FALL_TARGET_WINDOW_DAYS` defaults to 7 and is overrideable with `CPIC_FALL_TARGET_WINDOW_DAYS`.
- `2_create_cohort/phases/common.py`
  - Dynamic falls detection now considers both `PGX_TARGET_ICD_CODES` and `PGX_TARGET_ICD_PREFIXES`.
  - Falls targets use `event_classification = 'falls'` consistently when detected from env configuration.
- `2_create_cohort/phases/phase3_cohort_creation.py`
  - `target_patients_materialized` uses patient-level injury/external-cause matching within the configured window.
  - Phase 3 uses explicit `is_falls_target` config for the falls materialization branch.
  - Debug output includes `selected_window_target_patients` for the configured window.
  - Falls-only runs skip ED target counts and ED cohort creation.
  - ED-only runs skip falls cohort creation and falls QA after using falls materialization only as an exclusion set.
- `2_create_cohort/phases/phase4_finalization.py`
  - Normalizes requested cohort tables to a canonical parquet schema before writing to S3.
  - Removes accidental schema drift such as duplicated `first_ed_date` fields or transient `control_reference_date`.
  - Writes `target = is_target_case` for legacy compatibility.
  - Writes only the requested cohort output for falls-only or ED-only series runs.
- `2_create_cohort/final_cohort_schema.py`
  - Documents canonical `first_falls_date`, `first_ed_date`, `days_to_target_event`, and normalized `target` behavior.
- `2_create_cohort/README.md`
  - Documented falls definition now uses the configured window.
- `utility_scripts/cleanup_cohort_data.sh`
  - Existing notebook-0 cleanup path remains the canonical reset mechanism.
  - Clears project-scoped cohort artifacts, checkpoints, logs, notebook metadata, local outputs, and project NVMe outputs.
  - Adds `--clear-athena-qa` to clear Athena QA query-result artifacts when rerunning QA from scratch.
- `aws/athena/`
  - Adds Athena README, QA table DDL, falls/ED/combined QA SQL, and `scripts/run_cohort_qa.py`.
- `aws/iam/`
  - Reorganizes IAM runbooks, policy JSON, provisioning script, and status note under a visible repo folder.
- `.gitignore`
  - No longer ignores all of `aws/`; only generated AWS caches/results are ignored.
- Active workflow notebooks
  - Only directly used notebooks remain outside `archive/` and `logs/`: `0_config_and_pipeline.ipynb`, `1_cohort_workflow.ipynb`, `3a_feature_importance/feature_importance_cohort_runner.ipynb`, and `3_model_train_shap_ffa.ipynb`.
  - Superseded standalone notebooks were moved under `archive/inactive_notebooks/` and active references were updated.
  - `0_config_and_pipeline.ipynb` remains the reset entry point through `utility_scripts/cleanup_cohort_data.sh`.
  - `1_cohort_workflow.ipynb` remains the cohort rerun entry point.

## Validation checklist

- `python -m py_compile py_helpers/constants.py 2_create_cohort/phases/phase2_event_processing.py 2_create_cohort/phases/common.py 2_create_cohort/phases/phase3_cohort_creation.py 2_create_cohort/phases/phase4_finalization.py`
- `python -m py_compile aws/athena/scripts/run_cohort_qa.py aws/iam/scripts/provision_iam_user.py`
- `python -m json.tool aws/iam/policies/cpic-time-to-event-artifact-access-policy.json`
- `python -m json.tool aws/iam/policies/cpic-time-to-event-artifact-access-policy-v2.json`
- Run `utility_scripts/cleanup_cohort_data.sh --yes --clear-athena-qa` on EC2 before rerunning cohorts.
- Re-run all falls and ED cohort partitions on EC2.
- Confirm `Falls target mode: True` in Phase 3 logs.
- Confirm `selected_window_target_patients` and `Materialized ... target patients` are non-zero or document why the dataset does not support mechanism-confirmed falls.
- Confirm ED cohort counts remain reasonable and target patients are excluded from ED controls.
- Confirm all S3 pipeline states are `completed` with zero failed steps.
- Confirm Athena QA table output has 8 falls partitions and 8 ED partitions.
- Confirm `target_mismatch_rows = 0` for all partitions.
