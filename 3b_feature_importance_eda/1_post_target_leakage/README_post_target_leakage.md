# Post-Target Leakage Analysis

Step 3b uses Python and DuckDB to analyze the Step 2 cohort parquet files directly.

The required script is:

```bash
python 3b_feature_importance_eda/1_post_target_leakage/create_post_target_leakage_analysis.py --cohort falls --age-band 65-74
```

For each cohort and age band, the script reads:

```text
gold/cohorts/cohort_name={cohort}/event_year={year}/age_band={age_band}/cohort.parquet
```

It uses `is_target_case` plus the cohort target date column:

- `falls`: `first_fall_date`
- `ed`: `first_ed_date`

The output is:

```text
3b_feature_importance_eda/outputs/{cohort}/{age_band_fname}/{cohort}_{age_band_fname}_post_target_leakage_analysis.csv
```

This CSV feeds `2_filtering/create_safe_feature_filter_json.py`, which builds the safe feature filter used by the refined feature importance output.
