# Runtime Environment

This project runs on the **same EC2 instance** used for the original pgx-analysis.
All paths, virtual environments, and NVMe mounts are pre-configured.

---

## EC2 Instance

| Property | Value |
|----------|-------|
| Instance type | 32 vCPU / 1TB RAM |
| OS user | `pgx3874` |
| NVMe mount | `/mnt/nvme/` |
| Project root | `/home/pgx3874/cpic_time_to_event_analysis` |

---

## Python Environment

| Property | Value |
|----------|-------|
| Binary | `/home/pgx3874/jupyter-env/bin/python3.11` |
| Version | Python 3.11 |
| Virtual env | `/home/pgx3874/jupyter-env/` (shared with pgx-analysis) |
| Install deps | `pip install -r requirements.txt` |

### Python Libraries (`requirements.txt`)

| Package | Version | Used in |
|---------|---------|---------|
| `duckdb` | ≥1.4.0 | Steps 1a–6: memory-efficient parquet/S3 joins |
| `pandas` | ≥3.0.0 | All steps: dataframe operations |
| `numpy` | ≥2.0.0 | All steps: numerical computing |
| `pyarrow` | ≥23.0.0 | All steps: parquet I/O |
| `openpyxl` | ≥3.1.0 | Reporting: Excel output |
| `boto3` | ≥1.28.0 | All steps: S3 / AWS API |
| `scikit-learn` | ≥1.8.0 | Step 3a, 6: model utilities, CV |
| `joblib` | ≥1.3.0 | Step 3a, 6: parallel jobs |
| `catboost` | ≥1.2.0 | Step 6, 8: final model + FFA |
| `xgboost` | ≥2.0.0 | Step 6, 8: final model + FFA |
| `optuna` | ≥3.0.0 | Step 6: hyperparameter optimization |
| `matplotlib` | ≥3.6.0 | Steps 3a, 7, 8: plots |
| `seaborn` | ≥0.12.0 | Steps 3a, 7, 8: plots |
| `plotly` | ≥5.18.0 | Step 8: interactive visualizations |
| `networkx` | ≥3.0 | Step 8: FP-Growth network graphs |
| `beautifulsoup4` | ≥4.12.0 | Step 5: PubMed drug-gene search |
| `dtaidistance` | ≥2.3.0 | Step 8: DTW trajectory clustering |
| `tenacity` | ≥8.0.0 | All steps: S3 retry logic |
| `certifi` | ≥2023.0.0 | All steps: SSL certificates |
| `psutil` | ≥5.9.0 | `duckdb_utils.py`: memory detection |

### Key `py_helpers` env vars on EC2

```bash
export CPIC_S3_BUCKET=pgxdatalake
export CPIC_DUCKDB_THREADS=14          # per job (2 jobs = 28 total)
export CPIC_DUCKDB_MEMORY_LIMIT=384GB  # per job
export CPIC_TOTAL_WORKERS=2
export DUCKDB_TMP_DIRECTORY=/mnt/nvme/duckdb_tmp
export LOCAL_DATA_PATH=/mnt/nvme/cohorts
```

---

## R Environment

| Property | Value |
|----------|-------|
| Binary | `/usr/local/bin/Rscript` (EC2 default) |
| Version | R 4.x |
| Path resolution | `py_helpers/rscript_utils.py` → `find_rscript()` checks `PATH` then `/usr/local/bin/Rscript` |

### R Libraries

Install all R packages once on EC2:

```r
install.packages(c(
  "dplyr", "readr", "tidyr", "tibble", "purrr",  # tidyverse core
  "tidyverse", "ggplot2", "here",                  # visualization
  "catboost",                                       # CatBoost R binding
  "randomForest",                                   # Random Forest MC-CV
  "rsample",                                        # MC-CV splitting
  "furrr", "future",                               # parallel execution
  "progressr",                                      # progress bars
  "duckdb", "DBI"                                  # parquet loading
))
```

| Package | Used in |
|---------|---------|
| `dplyr`, `readr`, `tidyr`, `tibble`, `purrr` | Step 3a: feature importance MC-CV |
| `tidyverse`, `ggplot2`, `here` | Step 3a: visualizations, heatmaps |
| `catboost` | Step 3a: CatBoost feature importance |
| `randomForest` | Step 3a: RF feature importance |
| `rsample` | Step 3a: Monte Carlo CV splits |
| `furrr`, `future` | Step 3a: parallel MC-CV workers |
| `progressr` | Step 3a: progress reporting |
| `duckdb`, `DBI` | Step 3a: load cohort parquet from NVMe |

### R env vars on EC2

```bash
export LOCAL_DATA_PATH=/mnt/nvme/cohorts   # read by run_cohort_analysis.R
```

---

## Input File Paths (EC2 NVMe)

Data synced from S3 to NVMe before analysis runs:

```
/mnt/nvme/cohorts/
  cohort_name=falls/
    event_year=2016/age_band=65-74/cohort.parquet
    event_year=2016/age_band=75-84/cohort.parquet
    event_year=2017/...
    event_year=2018/...
    event_year=2019/...
  cohort_name=ed/
    event_year=2016/age_band=65-74/cohort.parquet
    ...

/mnt/nvme/duckdb_tmp/   ← DuckDB spill directory
```

## S3 Output Paths

```
s3://pgxdatalake/gold/cohorts/cohort_name=falls/...
s3://pgxdatalake/gold/cohorts/cohort_name=ed/...
s3://pgxdatalake/gold/feature_importance/...
s3://pgxdatalake/gold/final_model/falls/...
s3://pgxdatalake/gold/final_model/ed/...
```

---

## Python Binary Resolution (scripts)

All runner scripts resolve the Python binary in this priority order
(implemented in `py_helpers/env_utils.py:get_workflow_python_bin()`):

1. `PGX_PYTHON` env var (if set)
2. `/home/pgx3874/jupyter-env/bin/python3.11` (if exists — EC2)
3. `sys.executable` (fallback — local dev)

## Rscript Resolution

Implemented in `py_helpers/rscript_utils.py:find_rscript()`:

1. `configured` argument (if passed)
2. `which Rscript` (PATH lookup)
3. `/usr/local/bin/Rscript` ← **EC2 default**
4. `/usr/bin/Rscript`
5. Windows paths (local dev)
