# Feature Importance EDA and Refinement

## Overview

Feature Importance EDA performs additional exploratory data analysis on **already processed aggregated feature importances** from Step 3, using:
1. **Post-target leakage analysis** to identify pre/post target ICD/CPT/drug events (target leakage detection; target = `fall_injury_any` for falls, `ed_event` for ed)
2. **Code research and validation** (identify and validate non-informative ICD/CPT codes from lookup table - actual event-level filtering happens in Step 4b)
3. **Interactive code review and filtering** to refine feature selection (filters post-target leakage features from feature importance list)

**Note**: This is NOT a DTW filter. Feature Importance EDA uses Python/DuckDB post-target timing analysis and code research to filter already-processed aggregated feature importances, not raw event data. DTW is used separately in Step 4b (protocol filtering) and Step 9 (dashboard visualizations).

Based on this EDA, we filter and update the aggregated feature importances to produce refined `cohort_feature_importance` files. Step 4 uses the refined output to create model data.

## Purpose

- **Identify post-target leakage**: Use Python/DuckDB timing analysis to analyze feature occurrence before and after the target event (`fall_injury_any` for falls, `ed_event` for ed)
- **Research and validate codes**: Identify and validate administrative, scheduling, and non-medical codes through code research (actual event-level filtering happens in Step 4b)
- **Apply safe feature filtering**: Exclude post-target leakage features from aggregated feature importance list while keeping all pre-target features to maximize information available to the algorithm
- **Refine feature importances**: Update already-processed aggregated feature importances based on post-target leakage and code research findings
- **Output refined features**: Generate `cohort_feature_importance` files before Step 4

**Key Point**: Feature Importance EDA filters **aggregated feature importances** (already processed from Step 3), not raw event data. It uses post-target timing analysis and code research, not DTW.

## Inputs

- **Aggregated feature importances from Step 3 (required, not optional):**
  - Path: `3a_feature_importance/outputs/{cohort}/{age_band}/{cohort}_{age_band}_aggregated_feature_importance.csv`
- **Step 2 cohort parquet** (for post-target leakage analysis):
  - Path: `gold/cohorts/cohort_name={cohort}/event_year={year}/age_band={age_band}/cohort.parquet`
  - Step 3b reads these cohort rows directly, using `is_target_case` plus `first_falls_date` or `first_ed_date` to calculate pre-target and post-target feature ratios.

## Outputs

### Local Files

**Primary Output:**
- `outputs/{cohort}/{age_band_fname}/{cohort}_{age_band_fname}_cohort_feature_importance.csv` - Refined feature importances for Step 4a

**Analysis Reports:**
- `outputs/{cohort}/{age_band_fname}/{cohort}_{age_band_fname}_post_target_leakage_analysis.csv` - Post-target leakage analysis
- `outputs/{cohort}/{age_band_fname}/{cohort}_{age_band_fname}_feature_filtering_summary.json` - Filtering summary statistics

**Feature Filter Files:**
- `outputs/{cohort}/{age_band_fname}/{cohort}_{age_band_fname}_safe_feature_filter.json` - Safe feature filter (whitelist/blacklist)
- `outputs/{cohort}/{age_band_fname}/{cohort}_{age_band_fname}_post_target_filter.json` - Post-target leakage filter
- `outputs/{cohort}/{age_band_fname}/{cohort}_{age_band_fname}_pre_target_predictive_features.json` - Pre-target predictive features

### S3 Checkpoints

All outputs are automatically uploaded to S3 for checkpointing and downstream consumption:
- `s3://pgxdatalake/gold/cpic_time_to_event/feature_importance/{cohort}/{age_band}/{cohort}_{age_band}_cohort_feature_importance.csv`
- `s3://pgxdatalake/gold/cpic_time_to_event/feature_importance/{cohort}/{age_band}/{cohort}_{age_band}_post_target_leakage_analysis.csv`

**Note**: Uploads are idempotent - files are only uploaded if they don't already exist in S3.

## Workflow

1. **Load aggregated feature importances** from Step 3 (already processed feature importance scores)
2. **Post-Target Leakage Analysis** (`1_post_target_leakage/`):
   - Read Step 2 cohort parquet directly
   - Analyze feature timing before and after target event (`fall_injury_any` for falls, `ed_event` for ed)
   - Calculate pre-target and post-target ratios for each feature
   - Identify features that appear primarily post-target (>=80% post-target ratio = potential leakage)
   - Output: `{cohort}_{age_band}_post_target_leakage_analysis.csv`
   - See `1_post_target_leakage/README_post_target_leakage.md`
3. **Code Research and Validation** (`0_icd_cpt_check/`):
   - Load administrative codes from `4b_event_filter/administrative_codes_lookup.json` (codes identified in 0_icd_cpt_check)
   - Research and validate ICD/CPT codes by groups (ICD by chapter, CPT by range)
   - Identify non-informative ICD/CPT codes (administrative, scheduling, protocol codes)
   - **Note**: This step only validates and identifies codes - actual event-level filtering happens in Step 4b
   - See `0_icd_cpt_check/README_icd_cpt_check.md` for detailed validation process
4. **Create Safe Feature Filter**:
   - Exclude features with >=80% post-target ratio (pure post-target leakage)
   - Keep ALL features with ANY pre-target presence (maximize information)
   - For falls: exclude target-defining ICD codes (injury S/T + W00–W19) post-target; for ed: exclude `ed_event` encounter codes post-target
   - Output: `{cohort}_{age_band}_safe_feature_filter.json`
5. **Filter and Update Feature Importances**:
   - Apply safe feature filter (whitelist for cases, blacklist for controls)
   - Filter post-target leakage features from aggregated feature importance list
   - **Note**: Administrative codes are identified through code research but filtered at event level in Step 4b
   - Adjust importance scores based on post-target leakage and code research findings
   - Generate refined `cohort_feature_importance` files
6. **Save outputs locally and upload to S3**:
   - Save all outputs to local filesystem
   - Upload to S3 for checkpointing and Step 4a consumption
   - Save checkpoint metadata to S3

## Prerequisites

**⚠️ Important: Python/Jupyter Environment Path**

All scripts require the **full path to the Python jupyter environment** to ensure they use the correct Python interpreter and installed packages. This is especially important when:
- Running scripts from different directories
- Using cron jobs or automated workflows
- Running on EC2 instances with multiple Python environments

**Example (EC2 Environment):**
```bash
# EC2 Python jupyter environment path
/home/pgx3874/jupyter-env/bin/python3.11

# Use full path when running scripts
/home/pgx3874/jupyter-env/bin/python3.11 3b_feature_importance_eda/run_feature_importance_eda.py --cohort falls --age-band 65-74

# Or set as environment variable
export PYTHON_ENV="/home/pgx3874/jupyter-env/bin/python3.11"
$PYTHON_ENV 3b_feature_importance_eda/run_feature_importance_eda.py --cohort falls --age-band 65-74

# To find your Python path (if different):
which python  # or: which python3
```

**For Jupyter notebooks (EC2 Environment):**
```bash
# Use full path to jupyter (EC2)
/home/pgx3874/jupyter-env/bin/jupyter notebook --no-browser --port=8888

# Or if jupyter is in PATH:
jupyter notebook --no-browser --port=8888
```

## Memory when running multiple age bands

- **CLI (`run_feature_importance_eda.py --all-cohorts` or loop over age bands):** The script runs each age band in subprocesses and calls `gc.collect()` after each, so the main process does not accumulate large in-memory data. No extra cleanup is required.
- **Notebooks / interactive workflow:** If you run multiple age bands in the same kernel (e.g. loop over age bands in `feature_importance_eda_workflow` or a step3b notebook), large objects (aggregated_fi, post_target_results, refined_fi, etc.) can accumulate. To avoid memory growth:
  - After each age band, delete large variables you no longer need: `del aggregated_fi, post_target_results, refined_fi` (and any other large DataFrames).
  - Then run garbage collection: `from 3b_feature_importance_eda.run_feature_importance_eda import clear_age_band_memory; clear_age_band_memory()` or `import gc; gc.collect()`.

## Scripts

### Main Orchestration
- `run_feature_importance_eda.py` - Orchestration script to run all analyses in order
- `feature_importance_eda_workflow.py` - Interactive workflow script (can be run as notebook or script)
- `feature_importance_eda_interactive_analysis_cohort*.ipynb` - Cohort-specific interactive notebooks

### Analysis Scripts
- `run_post_target_leakage_analysis.py` - Post-target leakage analysis wrapper
- `create_post_target_leakage_analysis.py` - Creates post-target analysis CSV from Step 2 cohort parquet
- `filter_and_refine_features.py` - Main script to filter and refine feature importances

### Feature Filtering Scripts
- `create_safe_feature_filter_json.py` - Creates safe feature filter JSON (exclude leakage, keep pre-target)

### Validation Scripts
- `0_icd_cpt_check/analyze_code_groups.py` - Analyzes ICD/CPT codes by groups
- `0_icd_cpt_check/validate_icd_cpt_codes.py` - Interactive validation workflow

### Target-Leakage Analysis Scripts
- `1_post_target_leakage/run_post_target_leakage_analysis.py` - Wrapper for post-target leakage analysis
- `1_post_target_leakage/create_post_target_leakage_analysis.py` - Python/DuckDB pre/post target analysis for falls and ED
- `2_filtering/create_safe_feature_filter_json.py` - Builds the safe feature filter from post-target analysis

## Usage

### Script-Based Execution

```bash
# Run for a single cohort/age_band
python 3b_feature_importance_eda/run_feature_importance_eda.py --cohort falls --age-band 65-74

# Run for all cohorts
python 3b_feature_importance_eda/run_feature_importance_eda.py --all-cohorts

# Run multiple cohorts sequentially using shell script
bash 3b_feature_importance_eda/run_multiple_cohorts.sh
```

### Interactive Notebook Execution

You can run multiple Jupyter notebooks interactively at the same time! Each notebook runs in its own kernel, so they operate independently.

#### Quick Start

1. **Start Jupyter** (if not already running):
   ```bash
   cd /home/pgx3874/cpic_time_to_event_analysis
   /home/pgx3874/jupyter-env/bin/jupyter notebook --no-browser --port=8888
   
   # Or if jupyter is in PATH:
   jupyter notebook --no-browser --port=8888
   ```

2. **Open multiple notebooks** in separate browser tabs:
   - `feature_importance_eda_interactive_analysis_falls_65_74.ipynb` (falls / 65-74)
   - `feature_importance_eda_interactive_analysis_falls_75_84.ipynb` (falls / 75-84)
   - `feature_importance_eda_interactive_analysis_ed_65_74.ipynb` (ed / 65-74)
   - `feature_importance_eda_interactive_analysis_ed_75_84.ipynb` (ed / 75-84)

3. **Run cells independently** - Each notebook has its own kernel and can run cells independently.

#### Important Considerations

**Resource Usage:**
- Each notebook uses memory and CPU
- Running 3 notebooks simultaneously will use ~3x the resources
- Monitor with `htop` or `nvidia-smi` (if using GPU)

**File Conflicts:**
- **Output files**: Each notebook writes to cohort-specific directories:
  - `outputs/falls/65_74/`
  - `outputs/falls/75_84/`
  - `outputs/ed/65_74/`
  - `outputs/ed/75_84/`
- **No conflicts**: Different output directories prevent file conflicts
- **S3 uploads**: May happen simultaneously, but AWS handles this

**Output Files:**
- No conflicts: each cohort and age band writes to a separate output directory.
- Safe to run in parallel: different cohorts and age bands do not share output files.

#### Best Practices

**Option 1: Parallel Execution (Recommended)**
Safe to run all cohort/age-band analyses in parallel. Each reads its own Step 2 cohort partitions and writes to its own Step 3b output directory.

**Option 2: Sequential Execution (If Resource Constrained)**
If you have limited resources (memory/CPU), run sequentially:
1. Run cohort 5 first
2. Once complete, run cohort 6
3. Then run cohort 7

This ensures:
- Easier to monitor progress
- Less resource contention

**Option 3: Use tmux/screen for Multiple Sessions**
```bash
# Start tmux session
tmux new -s cohort5
# In tmux, start Jupyter (use full path to jupyter environment - EC2)
/home/pgx3874/jupyter-env/bin/jupyter notebook --no-browser --port=8888

# Create new tmux window for cohort 6
tmux new-window -t cohort5:1
/home/pgx3874/jupyter-env/bin/jupyter notebook --no-browser --port=8889

# Create new tmux window for cohort 7
tmux new-window -t cohort5:2
/home/pgx3874/jupyter-env/bin/jupyter notebook --no-browser --port=8890
```

Then access:
- Cohort 5: `http://your-ec2-ip:8888`
- Cohort 6: `http://your-ec2-ip:8889`
- Cohort 7: `http://your-ec2-ip:8890`

#### Monitoring

**Check Running Notebooks:**
```bash
# List all Jupyter processes
ps aux | grep jupyter

# Check which Python environment is being used
which python
which jupyter

# Check notebook kernels
jupyter kernelspec list
```

**Monitor Resources:**
```bash
# CPU and memory
htop

# Disk I/O
iostat -x 1

# Check output directories
ls -lh /home/pgx3874/cpic_time_to_event_analysis/3b_feature_importance_eda/outputs/ed/
```

#### Troubleshooting

**Issue: Out of memory**
**Solution**: 
- Run notebooks sequentially instead of parallel
- Close other applications
- Consider using the script-based approach (`run_feature_importance_eda.py`) which is more memory-efficient

## Feature Filtering Strategy

We use a **safe feature filter** approach that:
1. **Excludes** post-target leakage features (>=80% post-target ratio)
2. **Keeps** ALL features with ANY pre-target presence (maximize information)
3. **Applies** different filtering for cases vs controls:
   - **Cases (target=1)**: Whitelist approach (only features from `all_features_to_keep`)
   - **Controls (target=0)**: Blacklist approach (exclude only post-target leakage features)

See `FEATURE_FILTERING_APPROACH.md` for detailed documentation.

## Directory Structure

```
3b_feature_importance_eda/
├── 0_icd_cpt_check/              # ICD/CPT code validation
│   ├── analyze_code_groups.py
│   ├── validate_icd_cpt_codes.py
│   ├── administrative_codes_lookup.json
│   └── README_icd_cpt_check.md   # Code validation documentation
├── 1_post_target_leakage/        # Target-leakage analysis
│   ├── run_post_target_leakage_analysis.py
│   ├── create_post_target_leakage_analysis.py
│   └── README_post_target_leakage.md
├── outputs/                      # All outputs organized by cohort/age_band
│   ├── {cohort}/
│   │   └── {age_band_fname}/
│   │       └── *.csv, *.json     # Analysis results
├── feature_importance_eda_workflow.py            # Main interactive workflow
├── feature_importance_eda_interactive_analysis_cohort*.ipynb  # Cohort-specific notebooks
├── run_feature_importance_eda.py                # Orchestration script
├── filter_and_refine_features.py  # Feature filtering and refinement
└── README_feature_importance_eda.md              # This file
```

## Integration with Pipeline

- **Input**: Step 3 aggregated feature importances
  - `3a_feature_importance/outputs/{cohort}/{age_band}/{cohort}_{age_band}_aggregated_feature_importance.csv`
- **Output**: Refined `cohort_feature_importance` files
  - `outputs/{cohort}/{age_band_fname}/{cohort}_{age_band_fname}_cohort_feature_importance.csv`
- **Consumed by**: Step 4a model data creation
  - Step 4a uses the refined feature importance to filter events and create model-ready data

## Additional Documentation

- **`EXECUTION_ORDER.md`**: Detailed execution order and rationale
- **`FEATURE_FILTERING_APPROACH.md`**: Safe feature filtering strategy
- **`OUTPUTS_AND_VISUALIZATIONS.md`**: Complete output file manifest and visualization documentation
- **`LEAKAGE_ANALYSIS_SUMMARY.md`**: Summary of identified leakage features
- **`0_icd_cpt_check/README_icd_cpt_check.md`**: ICD/CPT code validation process
- **`1_post_target_leakage/README_post_target_leakage.md`**: Post-target leakage analysis documentation