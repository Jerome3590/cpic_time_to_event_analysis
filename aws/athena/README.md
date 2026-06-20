# Athena Cohort and Model-Events QA

Athena QA artifacts for the project-scoped cohort and Step 4 model-events parquet outputs in:

`s3://pgxdatalake/gold/cpic_time_to_event/cohorts/`

`s3://pgxdatalake/gold/cpic_time_to_event/cohorts_model_data/`

The QA setup uses separate external tables for falls and ED. New cohort writes normalize both outputs to the same canonical schema, including `first_falls_date`, `first_ed_date`, and `days_to_target_event`.

## Tables

- `cohorts.cpic_tte_falls_cohort_qa`
- `cohorts.cpic_tte_ed_cohort_qa`
- `cohorts.cpic_tte_model_events_qa`

The cohort tables are partitioned by:

- `event_year`
- `age_band`

The model-events table is partitioned by:

- `cohort_name`
- `age_band`

## Athena Query Editor

1. Open Athena in `us-east-1`.
2. Use the `AwsDataCatalog` data source and `cohorts` database.
3. Run `sql/create_cohort_qa_tables.sql` and `sql/create_model_events_qa_tables.sql` to create or refresh QA tables and partitions.
4. Run the cohort/model-events SQL files:
   - `sql/qa_falls_cohort.sql`
   - `sql/qa_ed_cohort.sql`
   - `sql/qa_combined_cohort_coverage.sql`
   - `sql/qa_model_events_coverage.sql`

The default QA result location used by the Python runner is:

`s3://aws-athena-query-results-us-east-1-535362115856/cpic_time_to_event_qa/`

## Python Runner

Run the same QA from the repo root:

```bash
python aws/athena/scripts/run_cohort_qa.py
```

Useful options:

```bash
python aws/athena/scripts/run_cohort_qa.py --skip-ddl
python aws/athena/scripts/run_cohort_qa.py --workgroup APCD
python aws/athena/scripts/run_cohort_qa.py --output-location s3://aws-athena-query-results-us-east-1-535362115856/cpic_time_to_event_qa/
```

## Expected Quick QA

- Exactly `8` falls cohort partitions and `8` ED cohort partitions for `2016-2019` across `65-74` and `75-84`.
- Exactly `4` model-events partitions: falls/ED across `65-74` and `75-84`.
- `mi_person_key`, `event_date`, `event_type`, and `is_target_case` should be populated and valid.
- Use `is_target_case` for target/control QA. New cohort writes also normalize the legacy `target` column to match `is_target_case`.
- ED target pharmacy rows should fall within the `1-21` day window.
- Falls outputs use patient-level falls materialization; do not require `event_classification = 'falls'` in the final event rows.
- Step 4 model-events should have both `target = 1` cases and `target = 0` controls for every cohort/age-band.
- Step 4 case rows should be strictly before `first_fall_date` or `first_ed_date` after target-leakage removal.
