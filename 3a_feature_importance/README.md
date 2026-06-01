# Step 3a: Feature Importance (Monte Carlo Cross-Validation)

Monte Carlo CV feature importance screening to identify top predictors for falls and ED outcomes.

## TODO
- [ ] Copy `run_mc_feature_importance.py` from `pgx-analysis/3a_feature_importance/`
- [ ] Copy cohort runner scripts (`run_cohort_*.py`) — update target variable and S3 paths
- [ ] Update target variable: `falls_event` / `ed_event`
- [ ] Validate top feature sets — expect high overlap with pgx-analysis for ED outcome
- [ ] Falls-specific features to watch: CNS depressants, antihypertensives, benzodiazepines, psychotropics
- [ ] Run per age band on EC2

## Expected Key Features (Falls)
Based on clinical literature:
- Benzodiazepines / sedative-hypnotics
- Antihypertensives (orthostatic hypotension)
- Antidepressants / antipsychotics
- Anticonvulsants
- Opioids (overlapping with pgx-analysis cohort)
- `r29_6_flag` — R29.6 (tendency to fall / repeated falls) — **feature input from Step 1b**
- `z91_81_flag` — Z91.81 (history of falling) — **feature input from Step 1b**
- Polypharmacy count (≥5 medications)
