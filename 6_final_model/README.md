# Step 6: Final Model Training

XGBoost + CatBoost ensemble training per `n_event_bin` and per age band, with Optuna hyperparameter optimization.

## TODO
- [ ] Copy `run_final_model.py` from `pgx-analysis/6_final_model/`
- [ ] Copy `build_final_cohort_model_features.py`
- [ ] Copy `build_model_data.py`, `remove_target_leakage.py`
- [ ] Update target variable: `falls_event` (separate models from `ed_event`)
- [ ] Update S3 output paths:
  - Falls: `gold/final_model/falls/{age_band}/bin_models/{bin_name}/`
  - ED: `gold/final_model/ed/{age_band}/bin_models/{bin_name}/`
- [ ] Recalculate `n_event_bin` thresholds for falls population (different event density than opioid-ED)
- [ ] Save `n_event_bin_thresholds.json` per cohort/age band
- [ ] Run Optuna (n_trials=100) per bin per age band

## n_event_bin Architecture
Same as pgx-analysis:
- Bins: `low`, `medium`, `high`, `extreme`
- Thresholds saved to: `6_final_model/outputs/{cohort}/{age_band}/n_event_bin_thresholds.json`
- Separate model per bin: `bin_models/{bin_name}/{model_type}.joblib`

## S3 Output Structure
```
gold/final_model/falls/{age_band}/
  bin_models/{bin_name}/
    xgboost.joblib
    catboost.joblib
    calibration_xgboost.joblib
    calibration_catboost.joblib
    falls_{age_band}_xgboost_feature_importance.csv
    falls_{age_band}_catboost_feature_importance.csv
  n_event_bin_thresholds.json
```
