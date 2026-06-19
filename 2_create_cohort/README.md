

# Cohort Creation Pipeline - Comprehensive Guide

This document provides a **complete reference** for the Cohort Creation Pipeline, combining pipeline design, modular architecture, performance improvements, checkpointing, and usage instructions.

***

## 🎯 Overview

The Cohort Pipeline builds **event-based fact tables** for analytical cohorts used in geriatric fall injury and ED visit risk prediction. It generates two main cohorts for **age bands 65–74 and 75–84 only**:

- **falls:** Patients with fall-related injury encounters (`fall_injury_any = 1`). Requires BOTH an injury ICD code (S00–S99, T07, T14, T20–T34, T79) AND an external cause fall code (W00–W19) on the same encounter. This cohort does **not** require separate ED visit evidence unless an explicit ED restriction is added in a future definition.
- **ed:** Patients with emergency department visits (`ed_event = 1`). Identified by CMS place of service code 23 or revenue codes 045x / 0981.

Each cohort includes **target cases** and **5 matching controls** per case. Age bands processed: `65-74`, `75-84`. Event years: 2016–2019.

When partitions have zero targets, the pipeline creates **control-only cohorts** using pre-computed average target counts to ensure complete coverage for model training.

***

## 🏗️ Architecture and Modular Structure

Following the October 2025 refactor, the pipeline has been fully modularized into **4 clean phases** under `2_create_cohort/phases/`.

### Directory Structure

```
2_create_cohort/
├── 0_create_cohort.py
└── phases/
    ├── __init__.py
    ├── common.py
    ├── phase1_data_preparation.py
    ├── phase2_event_processing.py
    ├── phase3_cohort_creation.py
    ├── phase4_finalization.py
    └── README.md
```


### Phase Summary

| Phase | File | Function | Description |
| :-- | :-- | :-- | :-- |
| Phase 1 | `phase1_data_preparation.py` | `run_phase1_data_preparation()` | Load and integrate medical + pharmacy data from APCD |
| Phase 2 | `phase2_event_processing.py` | `run_phase2_event_processing()` | Create unified event fact table and drug exposure |
| Phase 3 | `phase3_cohort_creation.py` | `run_phase3_step3_final_cohort_fact()` | Build final cohort fact table (target 5:1 control ratio, statistical independence, balanced temporal windows) |
| Phase 4 | `phase4_finalization.py` | `run_phase4_finalization()` | Validate QA and export to S3 |

**Key Benefits**

- Modular, testable, and maintainable
- Clear separation of concerns
- Backward-compatible imports
- No performance overhead

***

## ⚙️ Checkpoint and Resilience System

All pipeline phases now use the **centralized checkpoint system** to ensure job resilience and resumability.

### Checkpoint Features

- Step-level granularity (per-phase progress)
- Automatic resume after failure
- Metrics tracking (record counts, ratios, durations)
- Stored in S3 under `s3://pgx-repository/pgx-pipeline-status/create_cohort/{entity_id}/`

Example checkpoint JSON:

```json
{
  "pipeline_name": "create_cohort",
  "entity_id": "falls_65-74_2019",
  "status": "running",
  "steps": {
    "phase1_data_preparation": {
      "status": "completed",
      "metrics": {"medical_records": 1500000, "pharmacy_records": 850000}
    }
  }
}
```

**Classes:**

- `PipelineState` and `GlobalPipelineTracker` handle checkpoints, resuming, error logging, and status persistence.

***

## 🧩 DuckDB Configuration Enhancements

DuckDB handling has been fully aligned with the standardized system from the pharmacy pipeline:

- Uses `helpers/duckdb_utils.py`
- Corrects profiling commands (`PRAGMA disable_profiling`)
- Proper memory limit units (`16GB`, `900GB`)
- Full error propagation, no silent failures
- Configurable via command-line options or context settings

***

## 🧠 Event Fact Table Schema

### Core Identifiers

| Field | Description |
| :-- | :-- |
| `mi_person_key` | Patient ID |
| `event_date` | Event timestamp |
| `event_type` | 'medical' or 'pharmacy' |
| `data_source` | Originating data system |
| `age_band`, `event_year` | Stratification filters |

### Key Data Domains

- **Demographics:** imputed age, race, gender, payer type, and location
- **Medical Events:** ICD codes, CCS classification, provider and service metadata
- **Pharmacy Events:** drug name, therapeutic class, and exposure timing
- **Cohort Metadata:** target/control indicator (`is_target_case`), target column (`fall_injury_any` or `ed_event`), cohort label, cohort type (`falls`, `ed`, `control`), creation timestamp

### Cohort Classification Column

The `cohort` column tracks:
- **falls:** Target cases with `fall_injury_any = 1` (injury ICD + W00–W19 external cause on same encounter; ED visit evidence is not required by the current definition)
- **ed:** Target cases with `ed_event = 1` (POS=23 or revenue code 045x/0981)
- **control:** Non-target patients matched 5:1 by age/gender/race/ZIP/payer

### Temporal Fields and Drug Window Analysis

The pipeline includes temporal analysis fields that differ between cohorts:

#### Temporal Fields

| Field | Type | Description | falls | ed |
| :-- | :-- | :-- | :-- | :-- |
| `first_falls_date` | STRING | Date of first qualifying fall injury event (if any) | ✅ Populated | ❌ NULL |
| `first_ed_date` | STRING | Date of first qualifying ED event (if any) | ❌ NULL | ✅ Populated |
| `days_to_target_event` | INTEGER | Days from event to first target event | ❌ NULL* | ✅ Calculated |
| `event_date` | STRING | Date of the event | ✅ All events | ✅ All events |
| `event_sequence` | INTEGER | Sequential order of events per patient (globally ordered across medical and pharmacy) | ✅ All events | ✅ All events |

\* For falls cohort, `days_to_target_event` is NULL. Users can calculate it from `event_date` and `first_falls_date` if needed.

#### Target Case Indicators

| Field | Type | Description | falls | ed |
| :-- | :-- | :-- | :-- | :-- |
| `fall_injury_any` | INTEGER | 1 = qualifying fall injury encounter | ✅ Populated | ❌ NULL |
| `ed_event` | INTEGER | 1 = qualifying ED encounter | ❌ NULL | ✅ Populated |
| `is_target_case` | INTEGER | Target case indicator (1=target, 0=control) | ✅ Populated | ✅ Populated |
**Important Notes:**
- **`target` column is legacy** - Always set to 1 for both cohorts. Use `is_target_case` for actual target/control distinction.
- **`is_target_case` column** uses a fixed 21-day window for adverse drug event identification (excluding 0-day discharge prescriptions).
- The 21-day window captures ~90.5% of adverse drug events based on distribution analysis.

#### Cohort-Specific Temporal Behavior

**falls Cohort:**
- **Target Definition:** A target case has a qualifying fall injury event (`fall_injury_any = 1`), defined by injury ICD prefixes AND W00–W19 external fall-cause prefixes on the same encounter; the current falls cohort does not require a separate ED visit.
- **Complete Drug History:** Includes ALL drug events for target cases (no time restriction)
- **No Drug Window Filtering:** All pharmacy events are included regardless of timing
- **Temporal Analysis:** Use `event_date` and `event_sequence` for temporal analysis
- **First Target Date:** `first_falls_date` is populated for all patients with target events
- **Days Calculation:** `days_to_target_event` is NULL; calculate manually if needed:
  ```sql
  SELECT 
    event_date,
    first_falls_date,
    datediff(first_falls_date::DATE, event_date::DATE) as days_to_target
  FROM falls_cohort
  WHERE first_falls_date IS NOT NULL
  ```

**ed Cohort (Polypharmacy):**
- **Time-Windowed HCG Target Events:** Target is defined as HCG ED visits occurring within a 21-day window of drug events
- **Dual Filter System for True Adverse Drug Events:** The cohort applies two sequential filters to ensure only true adverse drug events are included:
  1. **ED Visit Frequency Filter:** Only includes patients with **<7 ED visits per year** (configurable via `ed_MAX_ED_VISITS_PER_YEAR` in `py_helpers/constants.py`)
     - Rationale: Patients with 7+ ED visits per year are likely not true adverse drug events (may indicate chronic conditions or frequent ED utilization patterns)
     - Filter applied first: Counts ED visits per patient per year, excludes patients with 7+ visits
  2. **Temporal Drug-ED Relationship Filter:** Only includes patients where **most recent drug event is within 21 days of ED event** (excluding 0-day discharge prescriptions)
     - Rationale: True adverse drug events should have a temporal relationship between drug exposure and ED visit
     - Filter applied second: For each ED event, finds most recent drug event before it, calculates days between them, includes only patients with 1-21 days (0-day gaps excluded as likely discharge prescriptions)
- **Filter Pipeline:** The filtering logic uses a linear, sequential CTE approach for clarity and maintainability:
  - Each filter step is a separate CTE that builds on the previous step
  - This makes the logic easy to follow, debug, and modify
  - See [Filter Pipeline Diagram](#ed-filter-pipeline) below for visual representation
- **21-Day Time Window:** Single window captures ~90.5% of adverse drug events (excluding 0-day discharge prescriptions) based on distribution analysis
- **Time Window Lookback:** Applied to BOTH target cases AND controls for balanced comparison
- **Target Cases:** 
  - Reference date: First ed event within 21-day window of drug event (index event per patient)
  - Includes: Medical events OR drug events within 21-day window before target
  - Target indicator: `is_target_case` (1 if drug event within 1-21 days before ED, excluding 0-day discharge prescriptions)
  - **Filtered to patients with <7 ED visits per year** (true adverse drug events only)
  - **21-day window captures ~90.5% of adverse drug events** (excluding 0-day discharge prescriptions) based on distribution analysis
- **Controls:**
  - Reference date: First non-ED medical event (fallback to first medical event if none)
  - Includes: Medical events OR drug events within 21-day window before reference date
  - Excluded if they have HCG target events within the 21-day window
  - **Balanced temporal windows** ensure fair comparison between targets and controls
- **First Target Date:** `first_ed_date` is populated for target cases only (NULL for controls)
- **Days Calculation:** `days_to_target_event` is pre-calculated for all events
  - For targets: Days to first ed event within time window
  - For controls: Days to reference date (first non-ED medical event)
  - Positive values (1-21): Event occurred before reference date (included in 21-day window for adverse drug event patterns)
  - Zero: Event occurred on reference date (excluded for adverse drug event identification - likely discharge prescriptions)
  - Negative values: Event occurred after reference date (filtered out for drug events)

#### ed Filter Pipeline {#ed-filter-pipeline}

The ed cohort uses a sequential filtering approach to identify true adverse drug events. The pipeline applies two filters in sequence:

```mermaid
flowchart TD
    A[All ed Patients<br/>N = Total Patients] --> B[Identify ED Encounters<br/>POS=23 or Revenue 045x/0981<br/>ed_events]
    B --> C{Filter 1:<br/>Visit Count<br/>< 5 per year?}
    C -->|Yes| D[Patients with<br/>< 5 ED Visits/Year<br/>N = Filtered Count 1]
    C -->|No| E[Excluded:<br/>7+ Visits/Year<br/>N = Excluded Count 1]
    D --> F[Get ED Events<br/>for Filtered Patients<br/>ed_events]
    F --> G[Get All Drug Events<br/>drug_events]
    G --> H[Match ED-Drug Pairs<br/>Find Most Recent Drug<br/>Before Each ED Event<br/>ed_drug_pairs]
    H --> I[Calculate Days<br/>From Drug to ED<br/>ed_drug_days]
    I --> J{Filter 2:<br/>Temporal Relationship<br/>1-21 days?<br/>Exclude 0-day gaps}
    J -->|Yes| K[Patients with<br/>Drug 1-21 days before ED<br/>N = Filtered Count 2<br/>Final Target Patients]
    J -->|No| L[Excluded:<br/>0-day gaps or >21 days<br/>N = Excluded Count 2]
    K --> M[Create Index ED Date<br/>First ED Event per Patient<br/>ed_index]
    M --> N[Build Cohort<br/>with 21-Day Window<br/>for Adverse Drug Events]

    style A fill:#e1f5ff
    style D fill:#c8e6c9
    style K fill:#4caf50,color:#fff
    style E fill:#ffcdd2
    style L fill:#ffcdd2
    style N fill:#81c784,color:#fff
```

**Filter Statistics Logged:**
- Total patients before filters: `N_total`
- Excluded by Filter 1 (7+ visits): `N_excluded_1`
- Remaining after Filter 1: `N_filtered_1`
- Excluded by Filter 2 (0-day gaps or no temporal relationship): `N_excluded_2`
- Final target patients: `N_final = N_filtered_1 - N_excluded_2`

**Note on 0-Day Gap Exclusion:**
- 0-day gaps (drug filled on same day as ED visit) are excluded as they likely represent discharge prescriptions rather than adverse drug events
- Only drug events occurring 1-21 days before ED visit are considered for adverse drug event identification

#### 21-Day Window Justification

The 21-day window for adverse drug event identification is based on empirical distribution analysis of drug-to-ED event gaps (excluding 0-day discharge prescriptions). Analysis of a sample cohort (age_band=65-74, event_year=2019) showed the following distribution:

| Days from Drug to ED | ED Events | Percentage* | Cumulative |
|---------------------|-----------|-------------|------------|
| 1-7 days | 2,259 | 64.6% | 64.6% |
| 8-14 days | 616 | 17.6% | 82.2% |
| 15-21 days | 293 | 8.4% | **90.5%** |
| **Total 1-21 days** | **3,168** | **90.5%** | - |
| **Total excluding 0-day** | **3,497** | **100.0%** | - |

\* Percentages calculated excluding 0-day discharge prescriptions (3,054 events excluded from denominator)

**Key Findings:**
- The 21-day window captures **~90.5% of adverse drug events** (excluding 0-day discharge prescriptions)
- The majority of events (64.6%) occur within 7 days, consistent with acute adverse drug reactions
- Events beyond 21 days represent a smaller proportion and are less likely to be causally related to the ED visit
- The 21-day window balances **clinical relevance** (captures majority of events) with **causal plausibility** (events beyond 21 days have weaker temporal association)

**Clinical Rationale:**
- Most adverse drug events manifest within 1-2 weeks of drug initiation or dose changes
- A 21-day window aligns with typical drug half-lives and clinical monitoring periods
- Events beyond 21 days are more likely to be coincidental rather than causally related

**Example Log Output:**
```
→ [PHASE 3 STEP 3] Target case counts:
  ed target patients (ed): 62,313
  ed: Excluded 15,000 patients by filters (<7 visits per year AND drug 1-21 days before ED, excluding 0-day discharge prescriptions)
  ed: Total before filters: 77,313, After filters: 62,313
  Drug-to-ED Gap Distribution (days_from_drug_to_ed, excluding 0-day discharge prescriptions):
    1-7 days: 2,259 ED events (64.6% of adverse drug events)
    8-14 days: 616 ED events (17.6% of adverse drug events)
    15-21 days: 293 ED events (8.4% of adverse drug events)
    Total 1-21 days: 3,168 ED events (90.5% of adverse drug events, excluding 0-day)
    Note: 3,054 0-day events (discharge prescriptions) excluded from calculation
```

#### Drug Window Filtering Logic

For ed cohort, the pipeline applies balanced temporal filtering to BOTH targets and controls using a **21-day window**. **0-day gaps are excluded** to focus on adverse drug event patterns (discharge prescriptions filled on ED visit day are filtered out):
```sql
-- Target cases: include medical events OR drug events within 21 days before target
-- Controls: include medical events OR drug events within 21 days before reference date
WHERE (
  (is_target_case = 1 AND (
    event_type = 'medical' 
                  OR (event_type = 'pharmacy' 
                      AND days_to_target_event IS NOT NULL 
                      AND days_to_target_event >= 0 
                      AND days_to_target_event <= 21)
  ))
  OR (is_target_case = 0 AND (
    event_type = 'medical'
                  OR (event_type = 'pharmacy' 
                      AND days_to_target_event IS NOT NULL 
                      AND days_to_target_event >= 0 
                      AND days_to_target_event <= 21)
  ))
)
```

This ensures:
- **Balanced Comparison:** Both targets and controls have the same temporal window structure
- **Causality Assessment:** Only drugs prescribed within 30 days before the reference event are considered
- **Risk Window Analysis:** Supports identification of high-risk drug exposure periods
- **Temporal Relationships:** Enables analysis of drug exposure timing relative to reference events
- **Statistical Validity:** Prevents bias from unequal temporal data between targets and controls

***

## 📈 Control Sampling: 5:1 Ratio

Control selection ensures matched demographics:

- Age, gender, and race matching
- Geographical alignment (ZIP/county)
- Payer-type consistency
- **Target cases:** No overlap (patients meeting the falls target definition are excluded from ed target/control construction; falls ICD logic is checked across ALL 10 ICD diagnosis columns)
- **Controls:** Can be reused across cohorts (same control can appear in both falls and ed)

### Statistical Independence

**Important:** Controls are sampled **without replacement WITHIN each cohort** to maintain statistical independence:
- **Within a cohort:** Each control patient appears only once (no reuse within falls or ed)
- **Across cohorts:** Same controls CAN be reused between falls and ed cohorts (they are independent studies)
- Should achieve 5:1 ratio unless partition (age_band + event_year) is genuinely small
- If fewer than 5:1 ratio is available, all available controls are used
- Warnings are logged when ratio falls below 5:1 (expected only for small partitions)
- This ensures valid statistical inference and prevents overfitting in ML models

### Control-Only Cohorts

When a partition has **zero target cases** (no qualifying fall or ED events), the pipeline creates a **control-only cohort**:
- Uses pre-computed average target count from all partitions
- Samples `avg_targets * 5` controls (maintains 5:1 structure)
- All records marked as `is_target_case = 0` and `target = 0` (legacy)
- All records marked as `is_target_case = 0` (no multiclass targets - simplified to single 21-day window)
- Ensures every partition has a cohort file for complete model training coverage
- Logs clearly indicate "CONTROL-ONLY" status

***

## 🚀 Execution Instructions

### Pre-Computation Step (Required First)

Before running the cohort pipeline, run the target frequency analysis script (which automatically pre-computes target averages):

```bash
# Analyze target codes and automatically pre-compute averages for cohort creation
python 1a_apcd_input_data/7_target_frequency_analysis.py --profile mushin
```

This creates `cohort_target_averages.json` in the project root, which Phase 3 uses for control-only cohort sizing. The pre-computation happens automatically as part of the target frequency analysis.

**Output:** `cohort_target_averages.json` containing:
- Average `fall_injury_any` targets per partition
- Average `ed_event` targets per partition
- Per-partition counts for reference

### SQL Workflow

```sql
\i phase1_data_preparation.sql
\i phase2_step1_event_fact_table.sql
\i phase2_step2_drug_exposure.sql
\i phase3_step3_final_cohort_fact.sql
\i phase4_complete_pipeline.sql
```


### Python Command-Line Interface

```bash
# Run with pre-computed averages (recommended)
python 0_create_cohort.py --age-band "65-74" --event-year 2016 --cohort both

# Fixed 21-day window for adverse drug event identification
# Note: Time window only applies to ed (polypharmacy) cohort
# falls cohort uses target event itself (no time window)
# 0-day gaps are excluded (likely discharge prescriptions)
# The --time-window-days argument is deprecated (window is fixed at 21 days)
```

### Batch Processing Scripts

**Important:** The batch processing scripts (`run_series_ed.py` and `run_series_falls.py`) are designed to process **ALL age_band/year combinations** for their respective cohort types, not just a single combination.

**Behavior:**
- These scripts process **age bands 65-74 and 75-84 only** and event years 2016–2019.
- With `--skip-existing`, they check S3 for existing cohorts and only process missing combinations
- **Note:** `check_existing_cohorts()` checks for BOTH `falls` and `ed` cohorts. If either is missing for a given age_band/year, that combination will be processed
- If you're starting fresh (no cohorts exist), all 36 combinations (9 age bands × 4 years) will be processed

**Example Usage:**
```bash
# Process all ed cohorts (skips existing ones)
python 2_create_cohort/run_series_ed.py --skip-existing --concurrent-workers 1

# Process all falls cohorts (skips existing ones)
python 2_create_cohort/run_series_falls.py --skip-existing --concurrent-workers 1
```

**Idempotent state:** If the pipeline exits after writing the cohort parquet but before saving "completed" state, the entity can stay "running" in `pgx-pipeline-status/create_cohort/`. Re-running the same cohort/age_band/year will detect existing output, update state to completed, and exit (no re-run). To fix a stuck "running" entity without re-running the pipeline, use `--repair-state`: e.g. `python 2_create_cohort/0_create_cohort.py --cohort ed --age-band 85-114 --event-year 2016 --repair-state`.

**To Process a Single Cohort:**
If you only want to process one specific age_band/year combination, use `0_create_cohort.py` directly:

```bash
# Process only one specific cohort
python 2_create_cohort/0_create_cohort.py \
  --cohort ed \
  --age-band 75-84 \
  --event-year 2019 \
  --concurrent-workers 1
```

### Advanced Usage

```bash
# With custom AWS profile
python precompute_target_averages.py --profile mushin

# Pipeline with custom settings
python 0_create_cohort.py \
  --age-band "65-74" \
  --event-year 2019 \
  --cohort both \
  # --time-window-days is deprecated (window is fixed at 21 days) \
  --concurrent-workers 3 \
  --threads 8 \
  --mem-gb 16 \
  --tmp-dir /tmp/duckdb_cohort
```

**Time Window Configuration:**
- `--time-window-days`: **DEPRECATED** - Time window is now fixed at 21 days (this argument is ignored)
- Only applies to ed (polypharmacy) cohort
- falls cohort always uses target event itself (no time window)
- Fixed 21-day window captures ~90.5% of adverse drug events (excluding 0-day discharge prescriptions)


***

## 📊 S3 Output Structure

Cohorts are organized **by cohort name first, then by year and age-band partitions**:

```
s3://pgxdatalake/gold/{PROJECT_SLUG}/cohorts/
├── cohort_name=falls/
│   ├── event_year=2019/
│   │   ├── age_band=65-74/
│   │   │   └── cohort.parquet
│   │   ├── age_band=75-84/
│   │   │   └── cohort.parquet
│   │   └── ...
│   ├── event_year=2020/
│   │   └── ...
│   └── ...
└── cohort_name=ed/
    ├── event_year=2019/
    │   ├── age_band=65-74/
    │   │   └── cohort.parquet
    │   └── ...
    └── ...
```

**Example:** `s3://pgxdatalake/gold/cpic_time_to_event/cohorts/cohort_name=falls/event_year=2019/age_band=65-74/cohort.parquet`

**Path Structure:** `gold/{PROJECT_SLUG}/cohorts/cohort_name={cohort}/event_year={year}/age_band={age_band}/cohort.parquet`

**Note:** All cohorts are saved (including control-only cohorts) to ensure complete coverage. Control-only cohorts are clearly logged with "CONTROL-ONLY" status.


***

## 🧪 QA and Validation Checks

- 100% imputed demographics
- 5:1 control ratio (or control-only cohorts when targets = 0)
- Event classification integrity
- **falls target validation:** injury ICD (S/T codes) + external cause W00–W19 on same encounter
- **ed target validation:** POS=23 or revenue code 045x/0981
- **Cohort column values:** `falls`, `ed`, `control`
- QA summary logged in checkpoints

Example QA log:

```
→ Phase 1 QA: Medical: 2.5M, Pharmacy: 5.0M
→ Phase 2 QA: Event fact table created (7.5M events)
  fall_injury_any records: 36,931 (640 distinct patients)
  ed_event records: 125,000 (8,500 distinct patients)
→ Phase 3 QA: Ratio 5.0:1 confirmed
  falls: 640 targets, 3,200 controls
  ed: 8,500 targets, 42,500 controls
→ Phase 4 QA: Pipeline complete
  falls cohort saved (CONTROL-ONLY) to S3  [if zero targets]
```


***

## ⚡ Performance Metrics

| Metric | Original | Optimized | Gain |
| :-- | :-- | :-- | :-- |
| Steps | 15 | 5 | 67% fewer |
| Execution Time | 45–60 min | 20–30 min | 50% faster |
| Memory | High | Medium | 40% less |
| Duplication | High | Low | 80% reduced |

Runs efficiently on 8–16 GB memory and supports 10M+ events per cohort.

### Recent Technical Optimizations

The pipeline has been optimized based on deep technical reviews to ensure correctness, performance, and reproducibility:

**SQL Query Optimizations:**
- **NOT EXISTS instead of NOT IN:** All subqueries use `NOT EXISTS` for safer NULL handling and better DuckDB performance
- **Hash-based deterministic sampling:** Replaced `ORDER BY RANDOM()` with hash-based sampling (`ABS(hash(mi_person_key)) % 10000`) for faster, deterministic control selection
- **Global event ordering:** `event_sequence` is now computed AFTER `UNION ALL` to ensure true chronological ordering across medical and pharmacy events
- **Materialized CTEs:** Frequently used subqueries (e.g., falls target patients) are materialized once to avoid repeated computation

**Code Quality Improvements:**
- **ICD normalization consistency:** Centralized normalization logic to prevent silent cohort drift across phases
- **Target column fix:** `target` column now correctly reflects `is_target_case` instead of hardcoded values
- **Partition-safe profiling:** Profiling filenames include `{age_band}_{event_year}` to prevent overwrites in parallel runs
- **Corrupted file detection:** Local sync checks file size > 0 to detect and handle corrupted files

**Pipeline Safety:**
- **Fallback warnings:** Clear warnings when fallback cohort logic is used (Phase 3 skipped)
- **Schema validation:** Comprehensive schema checks with dev validation mode for debugging
- **Memory management:** Dynamic memory limits based on concurrent workers to prevent OOM
- **DuckDB temp cleanup:** Automatic cleanup of DuckDB temporary files at startup and completion

### falls Cohort Sizes (65-74, 75-84 — 2016–2019)

For the falls cohort (`cohort_name=falls`), the **downstream feature-importance runtime** is influenced by event workload and distinct patient count in the cohort parquets.

Using **2016–2018 as training** and **2019 as test**:

- **Event-level row counts (workload), train = 2016–2018, test = 2019:**
  - **65–74**: train = 2,857,618, test = 1,015,348 (heavier partition)
  - **75–84**: train = 1,227,068, test = 370,364 (~43% of 65–74 workload)

- **Distinct patients:**
  - **65–74**: train = 23,356, test = 9,150
  - **75–84**: train = 8,477, test = 2,976

Taking `falls 65–74` as baseline: **75–84 ≈ 0.43×** the event workload. Both partitions run sequentially per the runbook.

### ed Cohort Sizes (65-74, 75-84 — 2016–2019)

For the ed cohort (`cohort_name=ed`), cohort parquets in `gold/{PROJECT_SLUG}/cohorts/cohort_name=ed/` are the primary input to downstream feature-importance analysis:

- **Event-level row counts (workload), train = 2016–2018, test = 2019:**
  - **65–74**: train = 135,465,040, test = 50,047,383 (heaviest partition)
  - **75–84**: train = 87,267,781, test = 32,780,611 (≈ 0.65× of 65–74)

- **Distinct patients:**
  - **65–74**: train = 919,654, test = 766,298
  - **75–84**: train = 462,222, test = 391,003

**ed 65–74 is the heaviest partition** by event workload. Process it first (per runbook).

***

## 👩‍🔬 Testing and Debugging

### Test a Sample Run

```bash
python create_cohort.py --age-band "65-74" --event-year 2019 --cohort falls
```


### Verify Checkpoints

```python
from helpers.pipeline_state import PipelineState
state = PipelineState("create_cohort", "falls_65-74_2019", logger)
print(state.get_progress())
```


***

## ✅ Best Practices

**Pre-computation:**

- Target averages are automatically computed by `7_target_frequency_analysis.py` (run this before cohort creation)
- Re-run if gold tier data changes significantly
- Check `cohort_target_averages.json` exists before batch runs

**When adding phases:**

- Create `phases/phaseN_<description>.py`
- Use `common.py` utilities
- Add to `__init__.py`
- Include checkpoint and error handling
- Document updates in `phases/README.md`

**When editing:**

- Keep each phase self-contained
- Use logging and checkpointing
- Update documentation and unit tests
- Maintain target classification logic (`fall_injury_any` and `ed_event`)

**Control-Only Cohorts:**

- Model training code should filter by `is_target_case = 1` if only targets are needed
- Control-only cohorts can be used as negative-only examples
- Consider excluding from training or weighting differently in loss function

**Target Column Usage:**

- **Use `is_target_case`** for target/control distinction (not the legacy `target` column)
- **`is_target_case`** uses a fixed 21-day window for adverse drug event identification
- 0-day gaps are excluded (likely discharge prescriptions filled on ED visit day)

***

## 📚 Related References

- **SQL Reference**: See [SQL Reference: Detailed Queries](#sql-reference-detailed-queries) section below for complete SQL reference
- `docs/README_s3_datalake.md` — S3 paths and data lake structure
- `docs/README_duckdb_dev.md` — Database performance tuning
- `docs/README_preprocessing.md` — Pre-imputation overview
- `2_create_cohort/phases/` — Phase-level logic reference
- `1a_apcd_input_data/7_target_frequency_analysis.py` — Target frequency analysis (includes automatic pre-computation of cohort target averages)
- `control_only_cohort_analysis.md` — Detailed analysis of control-only cohort strategy

***

## 🎯 Target Identification System

### Dual-Target Architecture

The pipeline uses two independent target identification methods:

1. **ICD/External Cause Targets** (falls cohort):
   - Injury ICD (S00–S99, T07, T14, T20–T34, T79) + external cause W00–W19 on same encounter
   - Configurable via environment variables (see below)
   - Codes are normalized before matching (uppercase, punctuation removed)
   - **Comprehensive checking:** All 10 ICD diagnosis columns are checked (primary through ten), not just `primary_icd_diagnosis_code`

2. **HCG-Based ED Visit Targets** (ed cohort):
   - Uses Healthcare Cost Group (HCG) line codes and **details** for precise identification:
     - `P51 - ER Visits and Observation Care` with detail `P51b - PHY ED Visits and Observation Care - ED Visits`
       - **Includes:** Only actual ED visits (P51b)
       - **Excludes:** Observation care visits (P51a) - these are not true ED visits for adverse drug event identification
     - `O11 - Emergency Room` (all details)
     - `P33 - Urgent Care Visits` (all details)
   - **Naming:** We use **O11_P** as the canonical identifier for the model_events target-date column (e.g. `first_o11_p_date` in Step 4). **O11_P includes all qualifying ED HCG codes** (P51b, O11, P33) as defined in the cohort logic above.
   - **Precision:** Uses `hcg_detail` field to distinguish actual ED visits from observation care
   - Identifies ED visits regardless of diagnosis codes
   - Always classified as `'ed'` in event classification
   - Patients who meet the falls target definition are excluded from ED cohort target/control construction to keep target populations distinct

### Classification Priority

Event classification follows this priority:
1. **Target ICD/CPT codes** → `'target'` (or `'falls'` if no dynamic targeting) - **Checks ALL 10 ICD diagnosis columns**
2. **HCG ED visits** → `'ed'`
3. **Other events** → `'non_target'` (or `'ed'` if default mode)

**Important:** The implementation uses `get_opioid_icd_sql_condition()` from `py_helpers/constants.py` for the current dynamic target condition. For falls, this means normalized prefix matching across all 10 ICD diagnosis columns, requiring injury prefixes AND W00–W19 external fall-cause prefixes on the same event row.

### Environment Variables for Dynamic Targeting

The pipeline supports dynamic target selection via environment variables:

| Variable | Description | Example |
| :-- | :-- | :-- |
| `PGX_TARGET_NAME` | Human-readable target name | `falls` |
| `PGX_TARGET_ICD_CODES` | Comma-separated exact ICD codes | `T079,T149` |
| `PGX_TARGET_CPT_CODES` | Comma-separated exact CPT codes | `99281,99282` |
| `PGX_TARGET_ICD_PREFIXES` | Comma-separated ICD prefixes | `S,T07,T14,W00,W01` |
| `PGX_TARGET_CPT_PREFIXES` | Comma-separated CPT prefixes | `9928` |

**Usage Examples:**

```bash
# Set falls as target
export PGX_TARGET_NAME="falls"
export PGX_TARGET_ICD_PREFIXES="S,T07,T14,T20,T21,T22,T23,T24,T25,T26,T27,T28,T29,T30,T31,T32,T33,T34,T79,W00,W01,W02,W03,W04,W05,W06,W07,W08,W09,W10,W11,W12,W13,W14,W15,W16,W17,W18,W19"

# Or use command-line arguments
python 0_create_cohort.py \
  --age-band "65-74" \
  --event-year 2019 \
  --target-name "falls" \
  --target-icd-prefixes "S,T07,T14,T20,T21,T22,T23,T24,T25,T26,T27,T28,T29,T30,T31,T32,T33,T34,T79,W00,W01,W02,W03,W04,W05,W06,W07,W08,W09,W10,W11,W12,W13,W14,W15,W16,W17,W18,W19"
```

**Note:** When environment variables are set, the pipeline uses generic `'target'`/`'non_target'` classification labels. When unset, it defaults to `'falls'`/`'ed'` classification.

### DuckDB Parallelization Configuration

The pipeline supports parallelization via environment variables:

| Variable | Description | Default |
| :-- | :-- | :-- |
| `PGX_THREADS_PER_WORKER` | Number of DuckDB threads for query execution | `8` |
| `PGX_S3_UPLOADER_THREAD_LIMIT` | Maximum uploader threads for S3 multi-part uploads | DuckDB default |
| `PGX_S3_UPLOADER_MAX_FILESIZE` | Max file size for part size calculation (e.g., "5368709120" for 5GB) | DuckDB default |
| `PGX_S3_UPLOADER_MAX_PARTS_PER_FILE` | Max parts per file for part size calculation | DuckDB default |

**Important:** `s3_max_connections` is **not** a valid DuckDB configuration parameter and will cause errors. S3 parallelization is handled automatically by DuckDB. Use `s3_uploader_thread_limit` if you need to tune upload performance.

### Memory Management for Parallel Workers

When running multiple cohort creation jobs in parallel (e.g., via `ThreadPoolExecutor` in a notebook), each worker needs to know the total number of concurrent workers to properly allocate memory. **This prevents memory oversubscription and OOM kills.**

**Setting Worker Count in Notebook:**

You have two options:

**Option 1: Pass as CLI argument (cleanest):**

```python
MAX_WORKERS = 3  # Your notebook variable

def run_cohort(job):
    cmd = [
        python_bin, script_path,
        "--age-band", job["age_band"],
        "--event-year", str(job["event_year"]),
        "--concurrent-workers", str(MAX_WORKERS),  # Pass directly!
        # ... other args
    ]
    # ... launch subprocess

# Now launch workers
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    # ... submit jobs
```

**Option 2: Set environment variable (if you prefer):**

```python
import os

MAX_WORKERS = 3  # Your notebook variable

# Set as environment variable (code checks for this too)
os.environ['MAX_WORKERS'] = str(MAX_WORKERS)
# OR use PGX_COHORT_WORKERS for more explicit naming

# Now launch workers
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    # ... submit jobs
```

**Recommendation:** Use Option 1 (CLI argument) - it's cleaner and doesn't require environment variable management.

**How It Works:**

- Each worker process detects `PGX_COHORT_WORKERS` from the environment
- Calculates per-worker memory limit: `(60% of total system memory) / number of workers`
- Sets DuckDB memory limit to prevent oversubscription
- Example: 3 workers on 1TB system = ~200GB per worker (600GB total + 400GB buffer)

**Environment Variable Priority:**

1. `PGX_COHORT_WORKERS` (explicit name, preferred for clarity)
2. `MAX_WORKERS` (works too - code checks for this automatically)
3. Default: `3` workers (if neither is set)

**Note:** Just set `os.environ['MAX_WORKERS'] = str(MAX_WORKERS)` in your notebook - no need for the extra `PGX_COHORT_WORKERS` step unless you prefer explicit naming.

**Logging:**

The pipeline logs the detected worker count and calculated memory limit:
```
→ [CONFIG] Detected PGX_COHORT_WORKERS=3 from environment
→ [CONFIG] DuckDB memory limit: 200GB (for 3 workers, 1000GB total system memory, 600GB available for DuckDB)
```

**Example:**
```bash
export PGX_THREADS_PER_WORKER=16
export PGX_S3_UPLOADER_THREAD_LIMIT=16
python 0_create_cohort.py --age-band "65-74" --event-year 2019 --operation-type s3_heavy
```

## 🏁 Summary

The **Cohort Creation Pipeline v4.3+** now features:
- **Modular, checkpoint-enabled architecture** with 4 clean phases
- **Dual-target system** (ICD codes + HCG ED visits) for comprehensive cohort identification
- **Precise HCG identification:** Uses `hcg_detail` to distinguish actual ED visits (P51b) from observation care (P51a)
- **Comprehensive ICD diagnosis checking** across all 10 ICD diagnosis columns (primary through ten) to ensure falls target events are not missed or misclassified
- **Control-only cohort logic** ensuring complete partition coverage for model training
- **Pre-computed averages** for efficient control-only cohort sizing
- **HCG field integration** (hcg_setting, hcg_line, hcg_detail) from gold tier
- **Cohort classification column** (falls, ed, NON_ED) for flexible filtering
- **High-performance DuckDB integration** with optimized memory and query handling

The pipeline achieves improved testability, maintainability, and resilience—while reducing runtime and resource usage by over 50%.

**Last Updated:** 2026-01-23
**Version:** 4.4 (Dual-Target + Control-Only Cohorts + HCG Integration + Comprehensive ICD Diagnosis Checking + Precise HCG Detail Matching)
**Status:** Production-Ready
**Authors:** PGx Analytics Engineering Team

---

## 📚 SQL Reference

For detailed SQL queries used in each phase of the pipeline, see the [SQL Reference Section](#sql-reference-detailed-queries) below.

---

<span style="display:none">[^1][^2][^3]</span>

<div align="center">⁂</div>

[^1]: Cohort_Pipeline_README.md

[^2]: Cohort_Modularization_README.md

[^3]: Cohort_Pipeline_Updates.md

---

# SQL Reference: Detailed Queries

This section provides a comprehensive reference for all SQL queries used in the Cohort Creation Pipeline. Each phase is documented with explanations, parameters, and example queries.

**Last Updated:** 2026-01-23  
**Version:** 5.0 (Simplified 21-Day Window - Removed Multiclass Targets)

---

## Phase 1: Data Preparation

### Overview
Loads and filters medical and pharmacy data from the APCD gold tier, creating normalized views for downstream processing.

### Medical Data Loading

**View:** `medical_base`

```sql
CREATE OR REPLACE VIEW medical_base AS
SELECT
    CAST(mi_person_key AS VARCHAR) AS mi_person_key,
    -- Map gold medical fields to normalized names used downstream
    member_age_dos AS age_imputed,
    member_gender AS gender_imputed,
    member_race AS race_imputed,
    member_zip_code_dos AS zip_imputed,
    member_county_dos AS county_imputed,
    payer_type AS payer_imputed,
    primary_icd_diagnosis_code,
    -- Carry forward CPT/procedure fields for event features
    procedure_code,
    cpt_mod_1_code,
    cpt_mod_2_code,
    -- HCG fields for ED visit identification
    hcg_setting,
    hcg_line,
    hcg_detail,
    event_date,
    CAST(event_year AS INTEGER) AS event_year
FROM read_parquet('s3://pgxdatalake/gold/medical/age_band={age_band}/event_year={event_year}/medical_data.parquet')
WHERE mi_person_key IS NOT NULL
  AND CAST(mi_person_key AS VARCHAR) <> ''
  AND event_date IS NOT NULL;
```

**Parameters:**
- `{age_band}`: Age band partition (e.g., "65-74", "75-84")
- `{event_year}`: Event year partition (e.g., 2019, 2020)

**Purpose:** Loads raw medical data from S3 and normalizes column names.

---

### Medical Data Filtering

**View:** `medical`

```sql
CREATE OR REPLACE VIEW medical AS
SELECT *
FROM medical_base
WHERE age_imputed IS NOT NULL
  AND age_imputed BETWEEN 1 AND 114
  AND event_date >= '{event_year}-01-01'
  AND event_date <= '{event_year}-12-31';
```

**Purpose:** Applies data quality filters (valid age range, date range).

---

### Pharmacy Data Loading

**View:** `pharmacy_base`

```sql
CREATE OR REPLACE VIEW pharmacy_base AS
SELECT 
    CAST(mi_person_key AS VARCHAR) AS mi_person_key,
    NULL::INTEGER AS age_imputed,
    NULL::VARCHAR AS gender_imputed,
    NULL::VARCHAR AS race_imputed,
    NULL::VARCHAR AS zip_imputed,
    NULL::VARCHAR AS county_imputed,
    NULL::VARCHAR AS payer_imputed,
    drug_name,
    NULL::VARCHAR AS therapeutic_class_1,
    -- Build event_date from incurred_date for cohort processing
    TRY_STRPTIME(CAST(incurred_date AS VARCHAR), '%Y%m%d') AS event_date,
    CAST(event_year AS INTEGER) AS event_year
FROM read_parquet('s3://pgxdatalake/gold/pharmacy/age_band={age_band}/event_year={event_year}/pharmacy_data.parquet')
WHERE mi_person_key IS NOT NULL
  AND CAST(mi_person_key AS VARCHAR) <> ''
  AND incurred_date IS NOT NULL
  AND TRY_STRPTIME(CAST(incurred_date AS VARCHAR), '%Y%m%d') IS NOT NULL;
```

**Purpose:** Loads pharmacy data and converts `incurred_date` (YYYYMMDD format) to `event_date`.

---

### Pharmacy Data Filtering

**View:** `pharmacy`

```sql
CREATE OR REPLACE VIEW pharmacy AS
SELECT *
FROM pharmacy_base
WHERE event_date IS NOT NULL
  AND event_date >= '{event_year}-01-01'
  AND event_date <= '{event_year}-12-31'
  AND drug_name IS NOT NULL
  AND drug_name <> '';
```

**Purpose:** Filters pharmacy data to valid date range and non-empty drug names.

---

## Phase 2: Event Processing

### Overview
Creates a unified event fact table that combines medical and pharmacy events with classification logic for target identification.

### Event Classification Logic

The classification logic uses a priority-based CASE statement:

**Priority Order:**
1. **Target ICD/CPT codes** → `'target'` (or `'falls'` if no dynamic targeting)
2. **HCG ED visits** → `'ed'`
3. **Other events** → `'non_target'` (or `'ed'` if default mode)

**Important:** ICD checking includes **ALL 10 ICD diagnosis columns** (primary through ten), not just `primary_icd_diagnosis_code`. For falls, matching is prefix-based after normalization and requires injury-prefix evidence AND W00–W19 external fall-cause evidence on the same event row.

**Dynamic Classification (current falls/ed setup):**

```sql
CASE 
    WHEN (
        any_diagnosis_column LIKE injury_prefix
        AND any_diagnosis_column LIKE external_fall_cause_prefix
    ) THEN 'target'
    WHEN (hcg_line = 'P51 - ER Visits and Observation Care' AND hcg_detail = 'P51b - PHY ED Visits and Observation Care - ED Visits')
         OR hcg_line = 'O11 - Emergency Room'
         OR hcg_line = 'P33 - Urgent Care Visits' THEN 'ed'
    ELSE 'non_target'
END
```

**Note:** The actual implementation uses `get_opioid_icd_sql_condition()` from `py_helpers/constants.py` to generate the comprehensive normalized SQL condition across all 10 ICD diagnosis columns.

---

### Unified Event Fact Table

**View:** `unified_event_fact_table`

```sql
CREATE OR REPLACE VIEW unified_event_fact_table AS
-- Medical events
SELECT 
    mi_person_key,
    event_date,
    'medical' as event_type,
    'medical' as data_source,
    age_imputed,
    gender_imputed as member_gender,
    race_imputed as member_race,
    zip_imputed,
    county_imputed,
    payer_imputed,
    primary_icd_diagnosis_code,
    NULL as drug_name,
    NULL as therapeutic_class_1,
    -- CPT/procedure codes (medical)
    procedure_code,
    cpt_mod_1_code,
    cpt_mod_2_code,
    -- HCG fields for ED visit identification
    hcg_setting,
    hcg_line,
    hcg_detail,
    -- Event classification (dynamic via env or default)
    {classification_sql} as event_classification,
    -- Event sequence number
    ROW_NUMBER() OVER (PARTITION BY mi_person_key ORDER BY event_date) as event_sequence
FROM medical
WHERE primary_icd_diagnosis_code IS NOT NULL

UNION ALL

-- Pharmacy events
SELECT 
    mi_person_key,
    event_date,
    'pharmacy' as event_type,
    'pharmacy' as data_source,
    age_imputed,
    gender_imputed as member_gender,
    race_imputed as member_race,
    zip_imputed,
    county_imputed,
    payer_imputed,
    NULL as primary_icd_diagnosis_code,
    drug_name,
    therapeutic_class_1,
    -- CPT/procedure codes not present in pharmacy (set NULLs)
    NULL as procedure_code,
    NULL as cpt_mod_1_code,
    NULL as cpt_mod_2_code,
    -- HCG fields not present in pharmacy (set NULLs)
    NULL as hcg_setting,
    NULL as hcg_line,
    NULL as hcg_detail,
    -- Use same classification expression to preserve target logic across union
    {classification_sql} as event_classification,
    ROW_NUMBER() OVER (PARTITION BY mi_person_key ORDER BY event_date) as event_sequence
FROM pharmacy
WHERE drug_name IS NOT NULL;
```

**Key Features:**
- Combines medical and pharmacy events into a single unified table
- Adds `event_classification` based on target codes and HCG ED visits
- Includes `event_sequence` to track chronological order per patient
- Preserves all demographic and clinical fields

---

## Phase 3: Cohort Creation

### Overview
Creates two cohorts (falls and ed) with a target 5:1 control-to-target ratio. Falls target cases are qualifying fall injury encounters and do not require separate ED visit evidence. Patients who meet the falls target definition are excluded from ED cohort target/control construction to keep target populations distinct.

**Key Features:**
- **Statistical Independence:** Controls are sampled without replacement (no reuse)
- **Temporal Fields:** Calculates `first_falls_date`, `first_ed_date`, and `days_to_target_event`
- **Balanced Windows:** ed applies the configured drug-to-ED lookback window to both targets and controls
- **Column Matching:** All columns match between target cases and controls
- **Ratio Warnings:** Logs warnings when ratio falls below 5:1

### falls Cohort (Normal Case - Has Targets)

**View:** `falls_cohort`

```sql
CREATE OR REPLACE VIEW falls_cohort AS
WITH target_cases AS (
    SELECT DISTINCT mi_person_key
    FROM unified_event_fact_table
    WHERE event_classification = 'target'  -- or 'falls' if no dynamic targeting
),
first_target_dates AS (
    -- Find first target event date per patient
    SELECT 
        mi_person_key,
        MIN(event_date) as first_falls_date
    FROM unified_event_fact_table
    WHERE event_classification = 'target'
    GROUP BY mi_person_key
),
control_candidates AS (
    SELECT DISTINCT mi_person_key
    FROM unified_event_fact_table
    WHERE event_classification != 'target'
      AND mi_person_key NOT IN (SELECT mi_person_key FROM target_cases)
),
sampled_controls AS (
    -- Sample distinct controls only (no reuse to maintain statistical independence)
    -- Use all available controls if fewer than 5:1 ratio
    WITH target_count AS (
        SELECT COUNT(*) as target_cnt FROM target_cases
    ),
    needed_count AS (
        SELECT tc.target_cnt * 5 as needed FROM target_count tc
    ),
    available_controls AS (
        SELECT COUNT(*) as available FROM control_candidates
    )
    SELECT 
        mi_person_key
    FROM control_candidates
    ORDER BY RANDOM()
    LIMIT (
        SELECT LEAST(
            (SELECT needed FROM needed_count),
            (SELECT available FROM available_controls)
        )
    )
)
SELECT 
    uef.*,
    1 as target,
    'falls' as cohort_name,
    CASE 
        WHEN tc.mi_person_key IS NOT NULL THEN 'falls'
        ELSE 'NON_ED'
    END as cohort,
    CASE WHEN tc.mi_person_key IS NOT NULL THEN 1 ELSE 0 END as is_target_case,
    -- Temporal fields: targets get first_falls_date, controls get NULL
    CASE 
        WHEN tc.mi_person_key IS NOT NULL THEN ftd.first_falls_date
        ELSE NULL
    END as first_falls_date,
    NULL as first_ed_date,
    NULL as days_to_target_event  -- Can be calculated from event_date and first_falls_date if needed
FROM unified_event_fact_table uef
LEFT JOIN target_cases tc ON uef.mi_person_key = tc.mi_person_key
LEFT JOIN sampled_controls sc ON uef.mi_person_key = sc.mi_person_key
LEFT JOIN first_target_dates ftd ON uef.mi_person_key = ftd.mi_person_key
WHERE tc.mi_person_key IS NOT NULL OR sc.mi_person_key IS NOT NULL;
```

**Logic:**
- **Target cases:** Patients with `event_classification = 'target'`, where falls target events are injury ICD prefixes AND W00–W19 external fall-cause prefixes on the same encounter; separate ED visit evidence is not required
- **Controls:** Hash-sampled controls up to 5x target count from non-target patients
- **Statistical Independence:** No control reuse - each control patient appears only once
- **Temporal Fields:** 
  - `first_falls_date`: Populated for targets only (NULL for controls)
  - `days_to_target_event`: NULL (can be calculated manually if needed)
- **Cohort column:** `'falls'` for targets, `'NON_ED'` for controls
- **All Events Included:** Complete drug history for both targets and controls (no time restriction)

---

### falls Cohort (Control-Only Case - Zero Targets)

**View:** `falls_cohort` (when `target_case_count = 0`)

```sql
CREATE OR REPLACE VIEW falls_cohort AS
WITH control_candidates AS (
    SELECT DISTINCT mi_person_key
    FROM unified_event_fact_table
    WHERE event_classification != 'target'
),
sampled_controls AS (
    SELECT mi_person_key
    FROM control_candidates
    ORDER BY RANDOM()
    LIMIT {control_limit}  -- avg_target_count * 5 or default 5000
)
SELECT 
    uef.*,
    0 as target,  -- All controls, no targets
    'falls' as cohort_name,
    'NON_ED' as cohort,  -- All controls are non-ED
    0 as is_target_case  -- All are controls
FROM unified_event_fact_table uef
INNER JOIN sampled_controls sc ON uef.mi_person_key = sc.mi_person_key;
```

**Purpose:** Creates a control-only cohort when no targets are found, using pre-computed average target count.

---

### ed Cohort (Normal Case - Has Targets)

**View:** `ed_cohort`

**Key Features: Dual Filter System**
1. **ED Visit Frequency Filter:** Only includes patients with **<7 ED visits per year**
2. **Temporal Drug-ED Relationship Filter:** Only includes patients where **most recent drug event is within 21 days of ED event** (excluding 0-day discharge prescriptions)

The filtering uses a sequential CTE approach for clarity and maintainability. Each step builds on the previous one:

```sql
CREATE OR REPLACE VIEW ed_cohort AS
WITH falls_target_patients AS (
    -- Patients meeting the falls target definition are excluded from ed entirely
    -- Actual implementation uses get_opioid_icd_sql_condition() for normalized all-diagnosis-column matching
    SELECT DISTINCT mi_person_key
    FROM unified_event_fact_table
    WHERE event_classification = 'target'
),
hcg_patients_with_visit_counts AS (
    -- Count ED visits per patient per year (for filtering)
    SELECT
        uef.mi_person_key,
        uef.event_year,
        CAST(COUNT(*) AS BIGINT) as ed_visit_count
    FROM unified_event_fact_table uef
    WHERE uef.event_classification = 'ed'
      AND NOT EXISTS (
          SELECT 1
          FROM falls_target_patients op
          WHERE op.mi_person_key = uef.mi_person_key
      )
    GROUP BY uef.mi_person_key, uef.event_year
),
hcg_index AS (
    -- First ed (index) date per patient (falls target patients excluded)
    -- FILTER: Only include patients with <7 ED visits per year (true adverse drug events)
    -- This anchors all time windows to a single index event per patient
    SELECT
        uef.mi_person_key,
        MIN(uef.event_date) AS index_hcg_date
    FROM unified_event_fact_table uef
    INNER JOIN hcg_patients_with_visit_counts vc ON uef.mi_person_key = vc.mi_person_key
        AND uef.event_year = vc.event_year
    WHERE uef.event_classification = 'ed'
      AND vc.ed_visit_count < 7
      AND NOT EXISTS (
          SELECT 1
          FROM falls_target_patients op
          WHERE op.mi_person_key = uef.mi_person_key
      )
    GROUP BY uef.mi_person_key
),
target_cases AS (
    SELECT DISTINCT mi_person_key
    FROM hcg_index  -- Uses filtered index (only <7 visits per year)
),
first_target_dates AS (
    -- Find first ed target event date per patient
    SELECT 
        mi_person_key,
        MIN(event_date) as first_ed_date
    FROM unified_event_fact_table
    WHERE event_classification = 'ed'
      AND mi_person_key NOT IN (SELECT mi_person_key FROM falls_target_patients)
    GROUP BY mi_person_key
),
control_candidates AS (
    SELECT DISTINCT mi_person_key
    FROM unified_event_fact_table
    WHERE event_classification != 'ed'
      AND mi_person_key NOT IN (SELECT mi_person_key FROM target_cases)
      AND mi_person_key NOT IN (SELECT mi_person_key FROM falls_target_patients)  -- Exclude falls target patients from controls
),
sampled_controls AS (
    -- Sample distinct controls only (no reuse to maintain statistical independence)
    -- Use all available controls if fewer than 5:1 ratio
    WITH target_count AS (
        SELECT COUNT(*) as target_cnt FROM target_cases
    ),
    needed_count AS (
        SELECT tc.target_cnt * 5 as needed FROM target_count tc
    ),
    available_controls AS (
        SELECT COUNT(*) as available FROM control_candidates
    )
    SELECT 
        mi_person_key
    FROM control_candidates
    ORDER BY RANDOM()
    LIMIT (
        SELECT LEAST(
            (SELECT needed FROM needed_count),
            (SELECT available FROM available_controls)
        )
    )
),
control_reference_dates AS (
    -- For controls, use first non-ED medical event as reference date (similar to target date for cases)
    -- This ensures balanced temporal windows between targets and controls
    -- Fallback to first medical event if no non-ED medical events exist
    WITH non_ed_reference AS (
        SELECT 
            uef.mi_person_key,
            MIN(uef.event_date) as reference_date
        FROM unified_event_fact_table uef
        INNER JOIN sampled_controls sc ON uef.mi_person_key = sc.mi_person_key
        WHERE uef.event_type = 'medical'
          AND NOT (
              (uef.hcg_line = 'P51 - ER Visits and Observation Care' AND uef.hcg_detail = 'P51b - PHY ED Visits and Observation Care - ED Visits')
              OR uef.hcg_line = 'O11 - Emergency Room'
              OR uef.hcg_line = 'P33 - Urgent Care Visits'
          )
        GROUP BY uef.mi_person_key
    ),
    fallback_reference AS (
        SELECT 
            uef.mi_person_key,
            MIN(uef.event_date) as reference_date
        FROM unified_event_fact_table uef
        INNER JOIN sampled_controls sc ON uef.mi_person_key = sc.mi_person_key
        WHERE uef.event_type = 'medical'
          AND uef.mi_person_key NOT IN (SELECT mi_person_key FROM non_ed_reference)
        GROUP BY uef.mi_person_key
    )
    SELECT * FROM non_ed_reference
    UNION ALL
    SELECT * FROM fallback_reference
),
events_with_dates AS (
    -- Calculate days_to_target_event for all events
    -- For targets: days to first ed event
    -- For controls: days to reference date (first non-ED medical event) to balance temporal windows
    SELECT 
        uef.*,
        ftd.first_ed_date,
        crd.reference_date as control_reference_date,
        -- Calculate days_to_target_event
        CASE 
            WHEN ftd.first_ed_date IS NOT NULL AND uef.event_date IS NOT NULL
            THEN CAST(datediff(ftd.first_ed_date::DATE, uef.event_date::DATE) AS INTEGER)
            WHEN crd.reference_date IS NOT NULL AND uef.event_date IS NOT NULL
            THEN CAST(datediff(crd.reference_date::DATE, uef.event_date::DATE) AS INTEGER)
            ELSE NULL
        END as days_to_target_event
    FROM unified_event_fact_table uef
    LEFT JOIN first_target_dates ftd ON uef.mi_person_key = ftd.mi_person_key
    LEFT JOIN control_reference_dates crd ON uef.mi_person_key = crd.mi_person_key
)
SELECT 
    ewd.*,
    1 as target,
    'ed' as cohort_name,
    CASE 
        WHEN tc.mi_person_key IS NOT NULL THEN 'ed'
        WHEN ewd.event_type = 'medical' AND ewd.hcg_line IS NULL THEN 'NON_ED'
        ELSE 'NON_ED'
    END as cohort,
    CASE WHEN tc.mi_person_key IS NOT NULL THEN 1 ELSE 0 END as is_target_case,
    -- Temporal fields: targets get first_ed_date, controls get NULL
    NULL as first_falls_date,
    CASE 
        WHEN tc.mi_person_key IS NOT NULL THEN ewd.first_ed_date
        ELSE NULL
    END as first_ed_date
FROM events_with_dates ewd
LEFT JOIN target_cases tc ON ewd.mi_person_key = tc.mi_person_key
LEFT JOIN sampled_controls sc ON ewd.mi_person_key = sc.mi_person_key
WHERE (tc.mi_person_key IS NOT NULL OR sc.mi_person_key IS NOT NULL)
  -- Apply balanced 30-day lookback window to both targets and controls
  AND (
      -- Target cases: include medical events OR drug events within 30 days before target
      (tc.mi_person_key IS NOT NULL AND (
          ewd.event_type = 'medical' 
          OR (ewd.event_type = 'pharmacy' AND ewd.days_to_target_event IS NOT NULL 
              AND ewd.days_to_target_event >= 0 AND ewd.days_to_target_event <= 30)
      ))
      -- Controls: apply same temporal logic for balanced comparison
      OR (sc.mi_person_key IS NOT NULL AND (
          ewd.event_type = 'medical'
          OR (ewd.event_type = 'pharmacy' AND ewd.days_to_target_event IS NOT NULL 
              AND ewd.days_to_target_event >= 0 AND ewd.days_to_target_event <= 30)
      ))
  );
```

**Key Features:**
- **Target cases:** Patients with HCG ED visits (`event_classification = 'ed'`)
- **Exclusion:** Patients meeting the falls target definition are excluded from ED targets and controls
- **Complete separation for targets:** Ensures falls target patients do not enter the ed cohort target/control construction
- **Statistical Independence:** Controls sampled without replacement WITHIN cohort (can reuse across cohorts)
- **Balanced Temporal Windows:** Both targets and controls use the configured drug-to-ED lookback window
  - Targets: Reference date = first ed event
  - Controls: Reference date = first non-ED medical event
- **Temporal Fields:**
  - `first_ed_date`: Populated for targets only (NULL for controls)
  - `days_to_target_event`: Calculated for both (days to reference date)
- **Cohort column:** `'ed'` for targets, `'NON_ED'` for controls

---

### Phase 3 Summary: Key Improvements

**Statistical Soundness:**
- ✅ **No Control Reuse Within Cohorts:** Controls sampled without replacement WITHIN each cohort maintains statistical independence
- ✅ **Cross-Cohort Reuse Allowed:** Same controls CAN be reused between falls and ed (independent studies)
- ✅ **Balanced Temporal Windows:** ed applies same 30-day lookback to targets and controls
- ✅ **Column Matching:** All columns match between target cases and controls (NULL for cohort-specific fields)
- ✅ **Ratio Transparency:** Warnings logged when ratio falls below 5:1

**Temporal Field Differences:**

| Cohort | `first_falls_date` | `first_ed_date` | `days_to_target_event` | Temporal Window |
| :-- | :-- | :-- | :-- | :-- |
| **falls** | ✅ Targets only | ❌ NULL | ❌ NULL* | None (all events) |
| **ed** | ❌ NULL | ✅ Targets only | ✅ Both (calculated) | 30-day (both) |

\* Can be calculated manually from `event_date` and `first_falls_date` if needed.

**Control Sampling Logic:**
- Uses `LEAST(needed_count, available_count)` to prevent over-sampling
- Should achieve 5:1 ratio unless partition (age_band + event_year) is genuinely small
- If fewer controls available than needed, uses all available (logs warning - expected only for small partitions)
- **Within-cohort:** No reuse ensures each control patient appears exactly once per cohort
- **Across-cohort:** Same controls can appear in both falls and ed (independent studies)

---

### ed Cohort (Control-Only Case - Zero Targets)

**View:** `ed_cohort` (when `ed_case_count = 0`)

```sql
CREATE OR REPLACE VIEW ed_cohort AS
WITH falls_target_patients AS (
    -- Patients meeting the falls target definition are excluded from ed entirely
    -- Actual implementation uses get_opioid_icd_sql_condition() for normalized all-diagnosis-column matching
    SELECT DISTINCT mi_person_key
    FROM unified_event_fact_table
    WHERE event_classification = 'target'
),
control_candidates AS (
    SELECT DISTINCT mi_person_key
    FROM unified_event_fact_table
    WHERE event_classification != 'ed'
      AND mi_person_key NOT IN (SELECT mi_person_key FROM falls_target_patients)  -- Exclude falls target patients
),
sampled_controls AS (
    SELECT mi_person_key
    FROM control_candidates
    ORDER BY RANDOM()
    LIMIT {control_limit}  -- avg_target_count * 5 or default 5000
)
SELECT 
    uef.*,
    0 as target,  -- All controls, no targets
    'ed' as cohort_name,
    'NON_ED' as cohort,  -- All controls are non-ED
    0 as is_target_case  -- All are controls
FROM unified_event_fact_table uef
INNER JOIN sampled_controls sc ON uef.mi_person_key = sc.mi_person_key;
```

**Purpose:** Creates a control-only cohort when no HCG ED targets are found, excluding falls target patients.

---

## Phase 4: Finalization

### Overview
Validates cohorts and saves them to S3 in Parquet format.

### Save falls Cohort

```sql
COPY falls_cohort TO 's3://pgxdatalake/gold/{PROJECT_SLUG}/cohorts/cohort_name=falls/event_year={event_year}/age_band={age_band}/cohort.parquet' 
(FORMAT PARQUET, COMPRESSION SNAPPY);
```

**Path Structure:** `gold/{PROJECT_SLUG}/cohorts/cohort_name={cohort}/event_year={year}/age_band={age_band}/cohort.parquet`

**Example:** `s3://pgxdatalake/gold/cpic_time_to_event/cohorts/cohort_name=falls/event_year=2019/age_band=65-74/cohort.parquet`

---

### Save ed Cohort

```sql
COPY ed_cohort TO 's3://pgxdatalake/gold/{PROJECT_SLUG}/cohorts/cohort_name=ed/event_year={event_year}/age_band={age_band}/cohort.parquet' 
(FORMAT PARQUET, COMPRESSION SNAPPY);
```

**Example:** `s3://pgxdatalake/gold/cpic_time_to_event/cohorts/cohort_name=ed/event_year=2019/age_band=65-74/cohort.parquet`

---

### QA Validation Queries

**Check cohort record counts:**

```sql
SELECT COUNT(*) FROM falls_cohort;
SELECT COUNT(*) FROM ed_cohort;
```

**Check control ratios:**

```sql
SELECT 
    COUNT(DISTINCT CASE WHEN is_target_case = 1 THEN mi_person_key END) as target_cases,
    COUNT(DISTINCT CASE WHEN is_target_case = 0 THEN mi_person_key END) as control_cases,
    CAST(COUNT(DISTINCT CASE WHEN is_target_case = 0 THEN mi_person_key END) AS FLOAT) / 
         NULLIF(COUNT(DISTINCT CASE WHEN is_target_case = 1 THEN mi_person_key END), 0) as control_ratio
FROM falls_cohort;

SELECT 
    COUNT(DISTINCT CASE WHEN is_target_case = 1 THEN mi_person_key END) as target_cases,
    COUNT(DISTINCT CASE WHEN is_target_case = 0 THEN mi_person_key END) as control_cases,
    CAST(COUNT(DISTINCT CASE WHEN is_target_case = 0 THEN mi_person_key END) AS FLOAT) / 
         NULLIF(COUNT(DISTINCT CASE WHEN is_target_case = 1 THEN mi_person_key END), 0) as control_ratio
FROM ed_cohort;
```

**Verify temporal fields:**

```sql
-- Check falls temporal fields
SELECT 
    COUNT(*) as total_records,
    COUNT(CASE WHEN first_falls_date IS NOT NULL THEN 1 END) as records_with_target_date,
    COUNT(CASE WHEN is_target_case = 1 AND first_falls_date IS NOT NULL THEN 1 END) as targets_with_date,
    COUNT(CASE WHEN is_target_case = 0 AND first_falls_date IS NULL THEN 1 END) as controls_with_null_date
FROM falls_cohort;

-- Check ed temporal fields and balanced windows
SELECT 
    is_target_case,
    COUNT(*) as total_events,
    COUNT(CASE WHEN event_type = 'pharmacy' THEN 1 END) as drug_events,
    COUNT(CASE WHEN event_type = 'pharmacy' AND days_to_target_event IS NOT NULL 
               AND days_to_target_event >= 0 AND days_to_target_event <= 30 THEN 1 END) as drugs_in_window,
    AVG(CASE WHEN days_to_target_event IS NOT NULL AND days_to_target_event >= 0 
             AND days_to_target_event <= 30 THEN days_to_target_event END) as avg_days_in_window
FROM ed_cohort
GROUP BY is_target_case;
```

**Check falls target distribution:**

```sql
SELECT 
    COUNT(DISTINCT mi_person_key) as distinct_falls_patients,
    COUNT(DISTINCT CASE WHEN is_target_case = 1 THEN mi_person_key END) as falls_target_patients,
    COUNT(DISTINCT CASE WHEN is_target_case = 0 THEN mi_person_key END) as falls_control_patients
FROM falls_cohort;
```

**Verify cohort separation:**

```sql
-- Check if any falls target patients appear in ed cohort
SELECT COUNT(DISTINCT mi_person_key) as falls_target_patients_in_ed
FROM ed_cohort
WHERE mi_person_key IN (
    SELECT DISTINCT mi_person_key
    FROM unified_event_fact_table
    WHERE event_classification = 'target'
);
-- Should return 0
```

---

## Key Concepts

### Event Classification Priority

1. **Target ICD/CPT codes** → `'target'` (or `'falls'` if default mode)
2. **HCG ED visits** → `'ed'` (using `hcg_detail` for precision - see HCG Detail Matching below)
3. **Other events** → `'non_target'` (or `'ed'` if default mode)

### HCG Detail Matching for Precise ED Visit Identification

The pipeline uses **both `hcg_line` and `hcg_detail`** to precisely identify ED visits for adverse drug event analysis:

- **P51 - ER Visits and Observation Care:**
  - ✅ **Includes:** `P51b - PHY ED Visits and Observation Care - ED Visits` (actual ED visits)
  - ❌ **Excludes:** `P51a - PHY ED Visits and Observation Care - Observation Care` (observation care, not true ED visits)
  - **Rationale:** Observation care visits are not true emergency department visits and should not be included in adverse drug event identification

- **O11 - Emergency Room:**
  - ✅ **Includes:** All details (all are ED visits)

- **P33 - Urgent Care Visits:**
  - ✅ **Includes:** All details (urgent care is relevant for adverse drug events)

**SQL Condition:**
```sql
(hcg_line = 'P51 - ER Visits and Observation Care' AND hcg_detail = 'P51b - PHY ED Visits and Observation Care - ED Visits')
OR hcg_line = 'O11 - Emergency Room'
OR hcg_line = 'P33 - Urgent Care Visits'
```

This precision ensures that only actual ED visits (not observation care) are used for adverse drug event identification, improving the signal-to-noise ratio in the polypharmacy cohort.

### Cohort Separation

- **falls cohort:** Patients with qualifying fall injury target events (`fall_injury_any = 1`) using injury ICD prefixes AND W00–W19 external fall-cause prefixes on the same encounter.
- **ed cohort:** Patients with HCG ED visits (using `hcg_detail` for precision: P51b only, excludes P51a observation care), excluding patients who meet the falls target definition.
- **Complete separation:** Falls target patients cannot appear in ed as targets or controls.
- **Comprehensive checking:** All 10 ICD diagnosis columns (`primary_icd_diagnosis_code` through `ten_icd_diagnosis_code`) are checked for falls target matching.

### Control-Only Cohorts

When a partition has zero targets:
- Uses pre-computed average target count from `cohort_target_averages.json`
- Samples `avg_targets * 5` controls (maintains 5:1 structure)
- All records marked as `is_target_case = 0` and `target = 0`
- Ensures every partition has a cohort file for model training

### Cohort Column Values

The `cohort` column tracks three types:
- **`falls`:** Target cases in falls_cohort
- **`ed`:** Target cases in ed_cohort
- **`NON_ED`:** Controls in both cohorts

### 5:1 Control Ratio

- For each target case, up to 5 controls are randomly sampled
- Controls are selected from patients who are NOT target cases
- Random sampling ensures unbiased control selection
- **Statistical Independence:** Controls are sampled **without replacement** (no reuse)
  - Each control patient appears only once
  - If fewer than 5:1 ratio is available, all available controls are used
  - Warnings are logged when ratio falls below 5:1
- Ratio is maintained even in control-only cohorts (using average target count)

### Temporal Fields and Drug Window Analysis

The pipeline calculates temporal relationships between events and target events, with different behavior for each cohort:

#### Temporal Fields Schema

| Field | Type | falls | ed | Description |
| :-- | :-- | :-- | :-- | :-- |
| `first_falls_date` | STRING | ✅ Populated | ❌ NULL | Date of first qualifying fall injury event per patient |
| `first_ed_date` | STRING | ❌ NULL | ✅ Populated | Date of first qualifying ED event per patient |
| `days_to_target_event` | INTEGER | ❌ NULL | ✅ Calculated | Days from event to first target event |
| `event_date` | STRING | ✅ All | ✅ All | Date of the event |
| `event_sequence` | INTEGER | ✅ All | ✅ All | Sequential order of events per patient |

#### falls Cohort Temporal Behavior

- **Complete Drug History:** All drug events included (no time restriction)
- **No Filtering:** All pharmacy and medical events included regardless of timing
- **First Target Date:** Calculated as `MIN(event_date)` where `event_classification = 'target'` in dynamic targeting mode
- **Days Calculation:** `days_to_target_event` is NULL; calculate manually if needed:
  ```sql
  SELECT 
    event_date,
    first_falls_date,
    datediff(first_falls_date::DATE, event_date::DATE) as days_to_target
  FROM falls_cohort
  WHERE first_falls_date IS NOT NULL
  ```

#### ed Cohort Temporal Behavior

- **Dual Filter System:** The cohort applies two sequential filters to ensure only true adverse drug events:
  1. **ED Visit Frequency Filter (<7 visits per year):**
     - Rationale: Patients with 7+ ED visits per year are likely not true adverse drug events (may indicate chronic conditions or frequent ED utilization patterns)
     - Applied via `hcg_patients_with_visit_counts` CTE that counts ED visits per patient per year
     - Patients with 7+ visits are excluded before temporal relationship analysis
     - Logging shows total patients before filter, after filter, and how many were excluded
  2. **Temporal Drug-ED Relationship Filter (1-21 days, excluding 0-day):**
     - Rationale: True adverse drug events should have a temporal relationship between drug exposure and ED visit
     - Applied via sequential CTEs: `ed_events` → `drug_events` → `ed_drug_pairs` → `ed_drug_days` → `qualifying_ed` (filters to 1-21 days, excludes 0-day) → `index_qualifying_ed` → `target_cases`
     - For each ED event, finds most recent drug event before it
     - Calculates days from drug event to ED event
     - Only includes patients where drug event is within 1-21 days of ED event (excluding 0-day discharge prescriptions)
     - QA check shows distribution of days (1-7, 8-14, 15-21 days, excluding 0-day discharge prescriptions)
- **Sequential CTE Approach:** The filtering uses a linear, step-by-step CTE structure for clarity:
  - Each filter step is a separate CTE that builds on the previous step
  - Makes the logic easy to follow, debug, and modify
  - Follows SQL best practices for complex filtering logic
- **30-Day Lookback Window:** Applied to BOTH target cases AND controls for balanced comparison
- **Target Cases:**
  - Reference date: First ed event (index event per patient, filtered to <7 visits per year)
  - Includes: Medical events OR drug events within 30 days before target
- **Controls:**
  - Reference date: First non-ED medical event (fallback to first medical event)
  - Includes: Medical events OR drug events within 30 days before reference date
- **Drug Event Filtering:** Applied via SQL WHERE clause:
  ```sql
  WHERE (
    -- Target cases: medical events OR drugs within 30 days before target
    (is_target_case = 1 AND (
      event_type = 'medical' 
      OR (event_type = 'pharmacy' 
          AND days_to_target_event >= 0 
          AND days_to_target_event <= 30)
    ))
    -- Controls: same temporal logic for balanced comparison
    OR (is_target_case = 0 AND (
      event_type = 'medical'
      OR (event_type = 'pharmacy' 
          AND days_to_target_event >= 0 
          AND days_to_target_event <= 30)
    ))
  )
  ```
- **First Target Date:** Calculated as `MIN(event_date)` where `event_classification = 'ed'` (excluding falls target patients)
- **Control Reference Date:** Calculated as `MIN(event_date)` for first non-ED medical event per control
- **Days Calculation:** Pre-calculated as `datediff(reference_date::DATE, event_date::DATE)`
  - For targets: Days to first ed event
  - For controls: Days to reference date (first non-ED medical event)
  - Positive values: Event before reference date (included in 30-day window)
  - Zero: Event on reference date
  - Negative values: Event after reference date (excluded for drug events)

#### SQL Implementation Example

```sql
-- First target dates calculation (falls)
WITH first_target_dates AS (
    SELECT 
        mi_person_key,
        MIN(event_date) as first_falls_date
    FROM unified_event_fact_table
    WHERE event_classification = 'falls'
    GROUP BY mi_person_key
)

-- Days calculation (ed)
SELECT 
    uef.*,
    CASE 
        WHEN ftd.first_ed_date IS NOT NULL AND uef.event_date IS NOT NULL
        THEN CAST(datediff(ftd.first_ed_date::DATE, uef.event_date::DATE) AS INTEGER)
        ELSE NULL
    END as days_to_target_event
FROM unified_event_fact_table uef
LEFT JOIN first_target_dates ftd ON uef.mi_person_key = ftd.mi_person_key
```

---

## Environment Variables

The following environment variables control dynamic targeting:

| Variable | Description | Example |
| :-- | :-- | :-- |
| `PGX_TARGET_NAME` | Human-readable target name | `falls` |
| `PGX_TARGET_ICD_CODES` | Comma-separated exact ICD codes | `T079,T149` |
| `PGX_TARGET_CPT_CODES` | Comma-separated exact CPT codes | `99281,99282` |
| `PGX_TARGET_ICD_PREFIXES` | Comma-separated ICD prefixes | `S,T07,T14,W00,W01` |
| `PGX_TARGET_CPT_PREFIXES` | Comma-separated CPT prefixes | `9928` |

When set, the pipeline uses generic `'target'`/`'non_target'` classification. When unset, it defaults to `'falls'`/`'ed'` classification.

---

## Related Documentation

- `docs/README_create_cohort.md` - Comprehensive pipeline guide
- `control_only_cohort_analysis.md` - Control-only cohort strategy analysis
- `precompute_target_averages.py` - Pre-computation script for target averages

---

**Note:** All SQL queries use DuckDB syntax and are executed via the Python pipeline. Parameters like `{age_band}`, `{event_year}`, and `{classification_sql}` are dynamically substituted at runtime.

