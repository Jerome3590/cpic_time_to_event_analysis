# EC2 Runbook: CPIC Falls/ED Cohort Pipeline

Optimized for a **32 vCPU / 1TB RAM EC2 instance** with **NVMe**.

## Scope

| Cohort | Target | Age bands | Partitions (band × year) |
|--------|--------|-----------|--------------------------|
| `falls` | `fall_injury_any` | 65–74, 75–84 | 2 × 4 = **8** |
| `ed`    | `ed_event`        | 65–74, 75–84 | 2 × 4 = **8** |

Both cohorts run **concurrently** (one process each). Within each job, partitions run **sequentially** in heavy-first order (`65-74` before `75-84`). Total: 16 partitions.

> **Much lighter than the original pgx-analysis run** (8 age bands × 2 cohorts = 128 partitions). Expect the full run to complete in a fraction of the original time.

## 0) Summary of the required updates

### Update A — DuckDB threads must be configurable (not hard-coded to 1)

In `duckdb_utils.py`, `create_simple_duckdb_connection()` currently forces:

* `PRAGMA threads=1`

Change it to use an env var (default safe):

```python
threads = int(os.getenv("CPIC_DUCKDB_THREADS", "1"))
conn.sql(f"PRAGMA threads={threads}")
```

Source: `py_helpers/duckdb_utils.py`

### Update B — Memory limit clamp must allow large RAM instances

`calculate_memory_limit_per_worker()` clamps per-worker memory to max **4GB**. Change to:

```python
# old: per_worker_gb = max(0.5, min(4.0, per_worker_gb))
per_worker_gb = max(4.0, min(256.0, per_worker_gb))
```

Set total workers to **2**:

```bash
export CPIC_TOTAL_WORKERS=2
```

Source: `py_helpers/duckdb_utils.py`

---

## 1) CPU & memory allocation (32-core / 1TB)

Reserve ~4 cores for OS/network. Two concurrent processes, equal weight:

| Process | Cohort | `CPIC_DUCKDB_THREADS` | `CPIC_DUCKDB_MEMORY_LIMIT` | `--concurrent-workers` |
|---------|--------|-----------------------|----------------------------|------------------------|
| 1 | `falls` | 14 | 384GB | 1 |
| 2 | `ed`    | 14 | 384GB | 1 |

Total: 28 threads — leaves 4 cores for OS + S3 uploads.

> **Note**: Both cohorts have identical age bands (65-74, 75-84), so workload is symmetric.

---

## 2) EC2 setup (same instance as pgx-analysis)

This project runs on the **same EC2 instance** used for pgx-analysis. The existing
`jupyter-env`, NVMe mounts, AWS credentials, and user (`pgx3874`) carry over.

```bash
# Clone repo alongside pgx-analysis
git clone https://github.com/Jerome3590/cpic_time_to_event_analysis.git /home/pgx3874/cpic_time_to_event_analysis
cd /home/pgx3874/cpic_time_to_event_analysis

# Reuse existing venv — install any new deps
/home/pgx3874/jupyter-env/bin/pip install -r requirements.txt

# Add project env vars to ~/.bashrc (NVMe + S3 already configured)
export CPIC_S3_BUCKET=pgxdatalake
export CPIC_TOTAL_WORKERS=2
```

> NVMe (`/mnt/nvme/duckdb_tmp`, `/mnt/nvme/cohorts`) and AWS credentials are already configured from the pgx-analysis run. No changes needed.

---

## 3) Job ordering

Within each cohort: `65-74` first (heavier), then `75-84`.
Years: 2016 → 2017 → 2018 → 2019.

---

## 4) Notebook run cells (Jupyter on EC2)

### Cell 1 — Environment setup

```python
import os
from pathlib import Path

PROJECT_ROOT = Path("/home/pgx3874/cpic_time_to_event_analysis")
PYTHON_BIN   = "/home/pgx3874/jupyter-env/bin/python3.11"

os.environ["CPIC_S3_BUCKET"]          = "pgxdatalake"
os.environ["DUCKDB_TMP_DIRECTORY"]    = "/mnt/nvme/duckdb_tmp"
os.environ["LOCAL_DATA_PATH"]          = "/mnt/nvme/cohorts"
os.environ["CPIC_TOTAL_WORKERS"]       = "2"
```

### Cell 2 — Launch `falls` cohort

```bash
%%bash
set -euo pipefail
export CPIC_DUCKDB_THREADS=14
export CPIC_DUCKDB_MEMORY_LIMIT=384GB
export CPIC_TOTAL_WORKERS=2
export CPIC_S3_BUCKET=pgxdatalake
export DUCKDB_TMP_DIRECTORY=/mnt/nvme/duckdb_tmp
export LOCAL_DATA_PATH=/mnt/nvme/cohorts

cd /home/pgx3874/cpic_time_to_event_analysis
mkdir -p logs

nohup /home/pgx3874/jupyter-env/bin/python3.11 2_create_cohort/run_series_falls.py \
  --skip-existing \
  --concurrent-workers 1 \
  --python-bin /home/pgx3874/jupyter-env/bin/python3.11 \
  > logs/falls_run.log 2>&1 &
echo "falls PID: $!"
```

**Processing order**: `65-74` → `75-84`, years 2016–2019

### Cell 3 — Launch `ed` cohort

```bash
%%bash
set -euo pipefail
export CPIC_DUCKDB_THREADS=14
export CPIC_DUCKDB_MEMORY_LIMIT=384GB
export CPIC_TOTAL_WORKERS=2
export CPIC_S3_BUCKET=pgxdatalake
export DUCKDB_TMP_DIRECTORY=/mnt/nvme/duckdb_tmp
export LOCAL_DATA_PATH=/mnt/nvme/cohorts

cd /home/pgx3874/cpic_time_to_event_analysis

nohup /home/pgx3874/jupyter-env/bin/python3.11 2_create_cohort/run_series_ed.py \
  --skip-existing \
  --concurrent-workers 1 \
  --python-bin /home/pgx3874/jupyter-env/bin/python3.11 \
  > logs/ed_run.log 2>&1 &
echo "ed PID: $!"
```

### Cell 4 — Monitor logs

```bash
%%bash
echo "=== FALLS ==="
tail -n 30 logs/falls_run.log
echo "=== ED ==="
tail -n 30 logs/ed_run.log
```

### Cell 5 — Live follow

```bash
%%bash
tail -f /home/pgx3874/cpic_time_to_event_analysis/logs/falls_run.log
```

---

## 5) Wrapper scripts

| Script | Cohort | Bands processed |
|--------|--------|-----------------|
| `2_create_cohort/run_series_falls.py` | `falls` | 65-74 → 75-84 |
| `2_create_cohort/run_series_ed.py`    | `ed`    | 65-74 → 75-84 |

```bash
# Dry run — check what needs processing
python 2_create_cohort/run_series_falls.py --skip-existing

# Force rerun all
python 2_create_cohort/run_series_falls.py
```

---

## 6) Check existing cohorts before running

```python
from py_helpers.cohort_utils import check_existing_cohorts

jobs = check_existing_cohorts(
    age_bands=["65-74", "75-84"],
    event_years=[2016, 2017, 2018, 2019]
)
print(f"{len(jobs)} partitions need processing")
for j in jobs:
    print(f"  {j['cohort']} / {j['age_band']} / {j['event_year']}")
```

---

## 7) Recommended defaults

| Setting | Value |
|---------|-------|
| Concurrent jobs | 2 (falls + ed) |
| `CPIC_DUCKDB_THREADS` | 14 per job |
| `CPIC_DUCKDB_MEMORY_LIMIT` | 384GB per job |
| `--concurrent-workers` | 1 |
| NVMe spill | `/mnt/nvme/duckdb_tmp` |
| Age band order | 65-74 → 75-84 |

---

## 8) Why this works

* DuckDB uses threads internally for the big joins/aggregations.
* By keeping **one process per cohort** and processing partitions sequentially, you avoid:

  * multi-process temp directory contention
  * S3 request storms
  * Python-worker oversubscription
* Large per-job memory caps prevent repeated spills / thrash on heavy age bands.

---

## 9) Verification

```bash
# Check running processes
ps aux | grep "0_create_cohort.py" | grep -v grep

# Memory per process
ps aux | grep "0_create_cohort.py" | grep -v grep | awk '{print $2, $6/1024 "MB"}'

# Errors
grep -i error logs/*.log | tail -20

# S3 output check
aws s3 ls s3://pgxdatalake/gold/cohorts/cohort_name=falls/ --recursive | head -20
aws s3 ls s3://pgxdatalake/gold/cohorts/cohort_name=ed/ --recursive | head -20
```

---

## 10) Troubleshooting

### Issue: Jobs not starting

* Check Python path: `which python` or `which python3`
* Check script path: `ls -la 2_create_cohort/0_create_cohort.py`
* Check permissions: `chmod +x 2_create_cohort/0_create_cohort.py`

### Issue: Memory errors

* Verify `PGX_TOTAL_WORKERS=2` is set
* Check actual memory limits in logs: `grep "memory limit" logs/*.log`
* Reduce `PGX_DUCKDB_THREADS` if still having issues

### Issue: Too slow

* Check CPU usage: `top` or `htop`
* Verify NVMe is being used: `df -h /mnt/nvme`
* Check for S3 throttling in logs
* Consider increasing `PGX_DUCKDB_THREADS` (but stay under 28 total)

### Issue: Duplicate processing

* Check for lock files: `aws s3 ls s3://pgxdatalake/gold/cohorts/locks/`
* Verify `check_existing_cohorts()` is working correctly
* Check logs for "already exists" messages

---

## 11) Full pipeline order after cohort creation

```
Step 2  (this runbook)     → 2_create_cohort/    falls + ed × 65-74, 75-84
Step 3a (EC2)              → 3a_feature_importance/  run_mc_feature_importance.py
Step 3b (EC2)              → 3b_feature_importance_eda/  BupaR + filter
Step 4  (EC2)              → 4_model_data/  create_model_data.py
Step 5  (EC2)              → 5_pgx_analysis/  run_analysis.py
Step 6  (EC2)              → 6_final_model/  run_final_model.py
Step 7  (EC2)              → 7_shap_analysis/  run_shap_analysis.py
Step 8  (EC2)              → 8_ffa_analysis/  ffa_analysis.py
```

All steps use `--cohort falls --age_band 65-74` etc. and are S3-backed + idempotent.
