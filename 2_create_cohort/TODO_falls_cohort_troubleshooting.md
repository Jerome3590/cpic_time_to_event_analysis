---
title: Falls cohort troubleshooting TODO
---

# Falls cohort troubleshooting TODO

## Current issue

Phase 3 is materializing zero falls target patients for `falls/65-74/2016` under the current strict falls definition.

Latest notebook output reached the Phase 3 debug block. The current code path used the generic dynamic target label `target`; update pipeline labeling so this cohort uses `event_classification = 'falls'` consistently.

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

## Immediate validation steps

1. Re-run `falls/65-74/2016` from Phase 2 Step 1 after the latest code is deployed.
2. Confirm logs are saved under production `s3://pgxdatalake/gold/cpic_time_to_event/logs/create_cohort/falls/65-74/2016/`; legacy notebook logs may appear under `s3://mushin-solutions-project-metadata/notebooks/create_cohort/falls/65-74/2016/`.
3. Inspect the new Phase 3 debug block for:
   - `same_patient_any_date_patients`
   - `same_patient_same_date_patients`
   - `same_patient_within_7d_patients`
   - `same_patient_within_30d_patients`
   - `sample external fall-cause ICD rows`
4. Use those counts to choose the cohort definition.

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

## Validation checklist

- `python -m py_compile py_helpers/constants.py 2_create_cohort/phases/phase2_event_processing.py 2_create_cohort/phases/common.py 2_create_cohort/phases/phase3_cohort_creation.py`
- Re-run Phase 2 Step 1 through Phase 3 Step 3 on EC2 for `falls/65-74/2016`.
- Confirm `Falls target mode: True` in Phase 3 logs.
- Confirm `selected_window_target_patients` and `Materialized ... target patients` are non-zero or document why the dataset does not support mechanism-confirmed falls.
- Confirm ED cohort counts remain reasonable and target patients are excluded from ED controls.
- Commit and push all final logic/doc changes.
