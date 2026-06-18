# cpic_time_to_event_analysis

## Stack
Python 3.11, pandas, DuckDB, PyArrow, scikit-learn, XGBoost, CatBoost, SHAP, Plotly, AWS S3, R/BupaR, DTW, FP-Growth.

## Purpose
End-to-end CPIC time-to-event pipeline for fall-related and ED visit risk prediction from APCD claims data. The repo builds cohorts, screens features, enriches CPIC/PGx drug features, trains final models, runs SHAP/FFA/FP-Growth/DTW analyses, and writes S3-backed pipeline artifacts.

## Key Locations
| Path | Description |
|------|-------------|
| `py_helpers/` | Shared helpers for constants, S3, paths, checkpoints, logging, modeling, and visualization. |
| `utility_scripts/` | Operational scripts for cleanup, status checks, logs, and S3 artifact sync. |
| `1a_apcd_input_data/` | Raw APCD preparation. |
| `1b_apcd_event_filter/` | Fall and ED event filtering logic. |
| `2_create_cohort/` | Cohort creation and QA. |
| `3a_feature_importance/` | Monte Carlo feature importance screening. |
| `3b_feature_importance_eda/` | Post-target BupaR and feature filtering. |
| `4_model_data/` | Model-ready dataset construction. |
| `5_pgx_analysis/` | CPIC/PGx feature enrichment. |
| `6_final_model/` | Final model training and evaluation. |
| `7_shap_analysis/` | SHAP analysis. |
| `8_ffa_analysis/` | Formal Feature Attribution and FP-Growth analysis. |
| `9_dtw_analysis/` | DTW feature, trajectory, and visual generation. |

## Corpus-First Rules
- Search local helpers and `utility_scripts/` before adding new utilities.
- Prefer existing S3, cohort, age-band, checkpoint, and logging conventions.
- Keep notebook JSON out of automatic context; use Python scripts and docs first.

## Project Metadata
- Project slug: `cpic-time-to-event-analysis`
- Notebook metadata bucket: `s3://mushin-solutions-project-metadata/notebooks/`
- Notebook output pointers resolve under: `s3://mushin-solutions-project-metadata/notebooks/cpic-time-to-event-analysis/`

## Notebook Outputs
Use project utility commands for notebook output sync when S3 output pointers are available:

```bash
python cursor_setup.py status
python cursor_setup.py push-outputs 5_pgx_analysis/pgx_cohort_runner.ipynb
python cursor_setup.py fetch-outputs 5_pgx_analysis/pgx_cohort_runner.ipynb
```

## Known Patterns
- Pipeline scripts generally use cohort and age-band parameters, with S3 checkpointing for long EC2 runs.
- Main cohorts are fall and ED outcomes, with older adult age bands emphasized in current docs.
- CPIC/PGx enrichment lives in `5_pgx_analysis/` and feeds downstream final model/SHAP/FFA steps.
