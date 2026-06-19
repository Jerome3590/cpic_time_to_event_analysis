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

## Remaining EC2 validation steps

1. Re-run `falls/65-74/2016` from Phase 2 Step 1 after the latest code is deployed.
2. Confirm logs are saved under production `s3://pgxdatalake/gold/cpic_time_to_event/logs/create_cohort/falls/65-74/2016/`; legacy notebook logs may appear under `s3://mushin-solutions-project-metadata/notebooks/create_cohort/falls/65-74/2016/`.
3. Inspect the Phase 3 debug block for:
   - `Falls target mode: True`
   - `same_patient_any_date_patients`
   - `same_patient_same_date_patients`
   - `same_patient_within_7d_patients`
   - `same_patient_within_30d_patients`
   - `selected_window_target_patients`
   - `Materialized ... target patients`
4. Confirm ED cohort counts remain reasonable and target patients are excluded from ED controls.

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
- `2_create_cohort/README.md`
  - Documented falls definition now uses the configured window.
- Active workflow notebooks
  - Only directly used notebooks remain outside `archive/` and `logs/`: `0_config_and_pipeline.ipynb`, `1_cohort_workflow.ipynb`, `3a_feature_importance/feature_importance_cohort_runner.ipynb`, and `3_model_train_shap_ffa.ipynb`.
  - Superseded standalone notebooks were moved under `archive/inactive_notebooks/` and active references were updated.

## Validation checklist

- `python -m py_compile py_helpers/constants.py 2_create_cohort/phases/phase2_event_processing.py 2_create_cohort/phases/common.py 2_create_cohort/phases/phase3_cohort_creation.py`
- Re-run Phase 2 Step 1 through Phase 3 Step 3 on EC2 for `falls/65-74/2016`.
- Confirm `Falls target mode: True` in Phase 3 logs.
- Confirm `selected_window_target_patients` and `Materialized ... target patients` are non-zero or document why the dataset does not support mechanism-confirmed falls.
- Confirm ED cohort counts remain reasonable and target patients are excluded from ED controls.
