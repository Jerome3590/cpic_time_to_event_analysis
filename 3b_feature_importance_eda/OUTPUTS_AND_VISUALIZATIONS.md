# Feature Importance EDA Outputs

Step 3b produces target-leakage evidence and a refined feature list for downstream model-data creation.

## Output Directory Structure

```text
3b_feature_importance_eda/outputs/
└── {cohort}/
    └── {age_band_fname}/
        ├── {cohort}_{age_band_fname}_post_target_leakage_analysis.csv
        ├── {cohort}_{age_band_fname}_safe_feature_filter.json
        ├── {cohort}_{age_band_fname}_cohort_feature_importance.csv
        └── {cohort}_{age_band_fname}_feature_filtering_summary.json
```

## Files

- `{cohort}_{age_band_fname}_post_target_leakage_analysis.csv`: Python/DuckDB pre/post target timing evidence from Step 2 cohort parquet.
- `{cohort}_{age_band_fname}_safe_feature_filter.json`: Features to keep/exclude based on post-target leakage rules.
- `{cohort}_{age_band_fname}_cohort_feature_importance.csv`: Canonical refined feature list consumed by downstream model-data and final-model steps.
- `{cohort}_{age_band_fname}_feature_filtering_summary.json`: Counts and metadata describing filtering decisions.

## S3 Locations

- `s3://pgxdatalake/gold/{project_slug}/feature_importance/{cohort}/{age_band}/{cohort}_{age_band_fname}_post_target_leakage_analysis.csv`
- `s3://pgxdatalake/gold/{project_slug}/feature_importance/{cohort}/{age_band}/{cohort}_{age_band_fname}_cohort_feature_importance.csv`
- `s3://pgxdatalake/gold/{project_slug}/feature_importance/{cohort}/{age_band}/{cohort}_{age_band_fname}_feature_filtering_summary.json`

## Regeneration

Run the full Step 3b workflow:

```bash
python 3b_feature_importance_eda/run_feature_importance_eda.py --cohort falls --age-band 65-74
```

Or run the target-leakage step directly:

```bash
python 3b_feature_importance_eda/1_post_target_leakage/create_post_target_leakage_analysis.py --cohort falls --age-band 65-74
```
