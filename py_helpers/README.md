# py_helpers — Shared Python Utilities

Adapted from `pgx-analysis/py_helpers/`. Copy and update the following:

## TODO
- [ ] Copy all files from `pgx-analysis/py_helpers/` as baseline
- [ ] **`constants.py`** — Update: S3 bucket/prefix, cohort names (`falls`, `ed`), target variable names
- [ ] **`event_density_utils.py`** — Recalculate `n_event_bin` thresholds for falls population
- [ ] **`cohort_utils.py`** — Update target column names: `falls_event`, `ed_event`
- [ ] **`data_utils.py`** — Any outcome-specific feature transformations
- [ ] Keep unchanged: `aws_utils.py`, `s3_utils.py`, `logging_utils.py`, `checkpoint_utils.py`, `pipeline_utils.py`

## Key Constants to Update (constants.py)
```python
COHORT_NAMES = ["falls", "ed"]
TARGET_COLUMN_MAP = {
    "falls": "falls_event",
    "ed": "ed_event",
}
S3_GOLD_PREFIX = "gold/cpic_falls/final_model/"
```
