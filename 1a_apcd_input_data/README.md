# Step 1a: APCD Input Data

Raw APCD text files → Parquet → Bronze layer → Global imputation → Cleaning.

## TODO
- [ ] Copy `0_txt_to_parquet.py` from `pgx-analysis/1a_apcd_input_data/`
- [ ] Copy `1b_merge_part_files_to_bronze.py`
- [ ] Copy `2_global_imputation.py`
- [ ] Copy `3_apcd_clean.py`, `3a_clean_pharmacy.py`, `3b_clean_medical.py`
- [ ] Copy `6_target_frequency_analysis.py` and update for falls ICD codes
- [ ] Update S3 bucket/prefix constants in `py_helpers/constants.py`
- [ ] Update `7_update_codes.py` for falls-specific code mappings

## S3 Input
- Bronze medical: `s3://<bucket>/bronze/medical/`
- Bronze pharmacy: `s3://<bucket>/bronze/pharmacy/`

## Notes
- Same APCD source data as pgx-analysis (Virginia APCD via VCHI DUA)
- Only the target frequency analysis and code mappings differ
