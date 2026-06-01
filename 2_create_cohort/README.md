# Step 2: Cohort Creation

Creates the final analysis cohort with falls and ED visit targets.

## TODO
- [ ] Copy `0_create_cohort.py` from `pgx-analysis/2_create_cohort/`
- [ ] Update target column: `falls_event` (binary) + `ed_event` (binary)
- [ ] Copy `2_step2_data_quality_qa.py` and update outcome references
- [ ] Copy `3_cohort_final_metrics.py`
- [ ] Update `final_cohort_schema.json` with new target columns
- [ ] Review and update age band parameters for falls-risk population
  - Falls risk is highest in elderly (65+) — consider adjusting age band granularity
- [ ] Run on EC2 (32-core/1TB instance for full Virginia APCD)

## Cohort Definition
- **Index date**: First qualifying falls event OR ED visit per patient per age band
- **Lookback**: 12 months of prior claims for feature engineering
- **Exclusions**: Patients with < 90 days of enrollment prior to index date

## Target Columns (update from pgx-analysis)
| Old (pgx-analysis) | New (cpic) |
|---|---|
| `opioid_ed_event` | `falls_event` |
| `polypharmacy_ed_event` | `ed_event` |
