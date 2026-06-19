---
title: Falls cohort troubleshooting TODO
---

# Falls cohort troubleshooting TODO

## Current issue

Phase 3 is materializing zero falls target patients for `falls/65-74/2016` under the current strict falls definition.

Observed diagnostic counts from the EC2 run:

- **Injury-prefix patients:** `98,352`
- **External fall-cause-prefix patients:** `122`
- **Same-row falls patients:** `0`
- **Target-condition patients:** `0`

The strict target condition currently requires injury-prefix evidence and W00-W19 external fall-cause evidence on the same `unified_event_fact_table` row.

## Working hypothesis

The W00-W19 external fall-cause code may be present on a different claim row from the injury diagnosis, possibly on the same service date or nearby service dates. A simple injury OR external-cause definition is too permissive because it would classify broad injury codes as falls without fall-mechanism evidence.

## Immediate validation steps

1. Re-run `falls/65-74/2016` from Phase 2 Step 1 after the latest code is deployed.
2. Confirm logs are saved under `s3://mushin-solutions-project-metadata/notebooks/create_cohort/falls/65-74/2016/`.
3. Inspect the new Phase 3 debug block for:
   - `same_patient_any_date_patients`
   - `same_patient_same_date_patients`
   - `same_patient_within_7d_patients`
   - `same_patient_within_30d_patients`
   - `sample external fall-cause ICD rows`
4. Use those counts to choose the cohort definition.

## Candidate correction logic

Preferred decision order:

1. If same-date overlap is meaningful, define falls as same patient with injury-prefix and W00-W19 evidence on the same `event_date`.
2. If same-date overlap is too sparse but 7-day overlap is meaningful, define falls as same patient with injury-prefix and W00-W19 evidence within +/- 7 days.
3. If W00-W19 overlap remains near zero, decide whether the dataset cannot support mechanism-confirmed falls and document any injury-only proxy separately.

Avoid changing to a simple OR unless the cohort is explicitly redefined as a broad injury proxy rather than falls.

## Code areas to update after definition decision

- `py_helpers/constants.py`
  - Update `get_opioid_icd_sql_condition()` or add a new helper if cross-row/date-window logic is required.
- `2_create_cohort/phases/phase2_event_processing.py`
  - Keep event classification aligned with the authoritative target logic.
- `2_create_cohort/phases/common.py`
  - Keep fallback unified view classification aligned with Phase 2.
- `2_create_cohort/phases/phase3_cohort_creation.py`
  - Update `target_patients_materialized` if target logic requires patient-level cross-row matching.
- `2_create_cohort/README.md`
  - Update the documented falls definition after final logic is chosen.

## Validation checklist

- `python -m py_compile py_helpers/constants.py 2_create_cohort/phases/phase2_event_processing.py 2_create_cohort/phases/common.py 2_create_cohort/phases/phase3_cohort_creation.py`
- Re-run Phase 2 Step 1 through Phase 3 Step 3 on EC2 for `falls/65-74/2016`.
- Confirm non-zero falls target patients or document why the dataset does not support mechanism-confirmed falls.
- Confirm ED cohort counts remain reasonable and target patients are excluded from ED controls.
- Commit and push all final logic/doc changes.
