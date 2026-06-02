# Refactor Lessons Learned: Cohort & Age Band Cleanup

**Scope:** Removal of deprecated cohorts (`opioid_ed`, `ed_non_opioid`), restriction of
age bands to `65-74` and `75-84`, removal of opioid ICD code logic (`F1120`), and update
of target date columns to `first_fall_date` / `first_ed_date`.

**Commits:** `97bfda1` → `0a4279c` (6 commits, ~100 files touched)

---

## 1. Categorise Before You Edit

Before touching a single file, bucket every hit from `git grep` into:

| Category | Action |
|---|---|
| **Runtime logic** — imports, function calls, SQL, variable values | Fix first; breaks on import |
| **CLI defaults / argparse `default=`** | Fix; wrong defaults silently run wrong band |
| **Hardcoded script-level constants** (`AGE_BAND = "13-24"`) | Fix; scripts run against wrong data |
| **Docstring / `help=` examples** | Fix last; no runtime impact |
| **Raw data ETL** (`1a_apcd_input_data/`) | Leave alone; must process all source age bands |
| **Backward-compat aliases** (`"ed_non_opioid": "ed"`) | Leave alone; intentional |

Mixing categories caused wasted edits (fixing docstrings before broken imports).

---

## 2. Runtime Errors Found — Root Causes

### 2a. Removed functions still imported
Several scripts imported functions that were deleted from `py_helpers/constants.py`
during an earlier migration:

```python
# These no longer exist — caused ImportError on any import of the module
from py_helpers.constants import age_band_uses_f1120_target  # deleted
from py_helpers.constants import cohort_uses_f1120_target    # deleted
from py_helpers.constants import get_cohort_slug             # renamed
from py_helpers.constants import get_target_name             # renamed
```

**Fix:** Remove dead imports; use replacements:
- `get_cohort_slug(age_band)` → `get_cohort_slug_by_cohort(cohort_name)`
- `get_target_name(age_band)` → `get_target_name_by_cohort(cohort_name)`
- `age_band_uses_f1120_target` / `cohort_uses_f1120_target` → removed, no replacement needed

**Lesson:** When renaming or deleting a function from a shared helper module, immediately
grep for all callers across the entire repo and fix them in the same commit.

### 2b. Undefined variable in f-string SQL
`create_control_cohort_model_data.py` had an SQL diagnostic query containing
`{opioid_condition}` — a variable that was deleted when opioid logic was removed but the
f-string referencing it was missed:

```python
# opioid_condition was deleted — this raised NameError at runtime
query = f"... WHERE {opioid_condition} ..."
```

**Lesson:** After removing a variable, search for its name in f-strings and format strings
— IDEs often don't flag undefined names inside f-strings as errors.

### 2c. Wrong function signature (age_band vs cohort_name)
`ensure_control_cohort.py` and `check_model_events_controls.py` called
`get_cohort_slug(age_band)` — passing an age band string to a function that expects a
cohort name. The old `get_cohort_slug` derived the cohort from the age band
(`"opioid"` for `< 65`, `"polypharmacy"` for `>= 65`). After the refactor, cohort is
always passed explicitly.

**Fix:** Replace with `get_cohort_slug_by_cohort(control_cohort)` using the cohort name
already available in the function's own parameters.

**Lesson:** When a function's *semantics* change (not just its name), search for every
call site and verify the argument being passed is still the right type.

---

## 3. Grep Patterns That Worked Best

```bash
# Find all non-existent function references
git grep -rn "age_band_uses_f1120\|cohort_uses_f1120\|get_cohort_slug\b\|get_target_name\b" -- "*.py"

# Find deprecated cohort names (excluding intentional aliases)
git grep -rn "ed_non_opioid\b\|opioid_ed\b" -- "*.py" | grep -v "COHORT_ALIASES\|legacy fallback\|build_ed_non_opioid"

# Find deprecated age bands (excluding raw ETL and generic docstring examples)
git grep -rn "0-12\|13-24\|25-44\|85-114" -- "*.py" | grep -v "1a_apcd_input_data\|BETWEEN.*AND"

# Find stale S3 path prefixes
git grep -rn "cohorts_F1120" -- "*.py"

# Find stale target date columns
git grep -rn "first_o11_p_date\|first_f1120_date\|first_ed_non_opioid_date" -- "*.py"
```

---

## 4. Files That Are Intentionally Unchanged

These files contain the deprecated age bands / ICD codes **by design** and must not be
updated:

| File | Reason |
|---|---|
| `1a_apcd_input_data/merge_part_files_to_main.py` | Raw ETL SQL — classifies every member age into all age bands from source data |
| `1a_apcd_input_data/3b_clean_medical.py` | Same — raw age band assignment |
| `1a_apcd_input_data/5_step1_data_quality_qa.py` | QA against all raw age bands intentionally |
| `1a_apcd_input_data/6_target_frequency_analysis.py` | F1120 frequency analysis on raw data — legitimate |
| `1a_apcd_input_data/7_update_codes.py` | ICD normalization `F11.20 → F1120` — generic algorithm |
| `py_helpers/s3_utils.py` (`"ed_non_opioid": "ed"`) | Backward-compat alias for reading legacy S3 partitions |
| `py_helpers/cohort_utils.py` (`build_ed_non_opioid_union_query`) | Backward-compat alias |
| `py_helpers/feature_utils.py` (F1120 normalization examples) | Generic ICD code normalization, not cohort-specific |

---

## 5. Multi-Edit Tool Pitfalls

- **Exact whitespace match required.** Multi-edit fails silently if the `old_string` has
  even one character difference from the file. Always re-read the target lines with the
  `read_file` tool before writing the edit.
- **Parallel edits on the same file must not overlap.** Two edits modifying adjacent lines
  in the same `multi_edit` call can conflict. Split into sequential calls if in doubt.
- **Verify after large edits.** After applying a multi-edit to a critical file (especially
  SQL or import blocks), read back the modified lines to confirm the result.

---

## 6. SQL Query Refactoring Notes

When removing a SQL variable from an f-string query, check **all** queries in the file,
not just the primary one. `create_control_cohort_model_data.py` had a separate
*diagnostic* query block that also referenced `{opioid_condition}` and was missed in
the initial pass.

Pattern to grep for:
```bash
git grep -n "opioid_condition\|hcg_line\|F1120\|first_o11_p" -- "*.py" | grep -v "^Binary"
```

---

## 7. Commit Strategy That Worked

Committing by pipeline step (one commit per directory batch) made bisecting easier and
kept diffs readable:

1. `6_final_model/` — most critical (production model training)
2. `3b_feature_importance_eda/` + `4_model_data/` — broken imports
3. `utility_scripts/` + `py_helpers/` — shared helpers
4. `3a/5/7` pipeline steps — help text / docstrings
5. `8_ffa_analysis/` — hardcoded analysis constants

---

## 8. Checklist for Future Cohort/Target Changes

When adding or removing a cohort or age band:

- [ ] Update `py_helpers/constants.py` — `AGE_BANDS`, `REQUIRED_COHORTS`, `COHORT_TARGET_COLUMN`
- [ ] Update `py_helpers/data_utils.py` — `validate_cohort_name`
- [ ] Update `py_helpers/feature_importance_heatmap.py` — `CANONICAL_AGE_BAND_ORDER`
- [ ] Grep for all callers of any renamed/deleted constants function
- [ ] Grep for all f-strings referencing deleted variables
- [ ] Grep for hardcoded `AGE_BAND = "..."` script-level constants in `8_ffa_analysis/`
- [ ] Update CLI `default=` values in argparse across all pipeline steps
- [ ] Update S3 path helpers in `py_helpers/s3_utils.py` and `cohort_utils.py`
- [ ] Update diagnostic/utility scripts: `check_model_events_controls.py`,
  `check_cohort_parquet_controls.py`, `check_pipeline_status_s3.py`
- [ ] Leave `1a_apcd_input_data/` ETL SQL unchanged
- [ ] Add backward-compat alias in `s3_utils.py` if old S3 partitions still exist

---

## 9. Plan: Make Cohorts and Targets Fully Dynamic

**Goal:** A user should be able to define a new cohort + age band + target in one place
and have the entire pipeline work without touching any other file.

**Current state:** `py_helpers/constants.py` already holds the canonical registry
(`REQUIRED_COHORTS`, `COHORT_TARGET_COLUMN`). The gap is that dozens of scripts still
hardcode age bands or cohort names instead of reading from this registry.

---

### Phase 1 — Single Source of Truth (`py_helpers/constants.py`)

The registry already exists. Harden it:

```python
# py_helpers/constants.py

AGE_BANDS = ['65-74', '75-84']

REQUIRED_COHORTS: dict[str, list[str]] = {
    "falls": list(AGE_BANDS),
    "ed":    list(AGE_BANDS),
}

COHORT_TARGET_COLUMN: dict[str, str] = {
    "falls": "fall_injury_any",
    "ed":    "ed_event",
}

COHORT_TARGET_DATE_COLUMN: dict[str, str] = {   # ADD THIS
    "falls": "first_fall_date",
    "ed":    "first_ed_date",
}

COHORT_DISPLAY_NAME: dict[str, str] = {          # ADD THIS
    "falls": "Falls",
    "ed":    "Emergency Department",
}
```

**Rule:** Every other file reads from these dicts. Nothing else is the authority.

---

### Phase 2 — Config File Override (`pipeline_config.yaml`)

Add an optional YAML config at the repo root so users can extend the registry without
editing Python:

```yaml
# pipeline_config.yaml
cohorts:
  falls:
    age_bands: ["65-74", "75-84"]
    target_column: fall_injury_any
    target_date_column: first_fall_date
    display_name: Falls
  ed:
    age_bands: ["65-74", "75-84"]
    target_column: ed_event
    target_date_column: first_ed_date
    display_name: Emergency Department

event_years: ["2016", "2017", "2018", "2019"]
s3_bucket: pgxdatalake
```

Add a loader to `py_helpers/constants.py` that merges YAML over the Python defaults at
import time:

```python
# py_helpers/constants.py (addition)
import yaml
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent.parent / "pipeline_config.yaml"

def _load_pipeline_config() -> dict:
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}

_cfg = _load_pipeline_config()

if "cohorts" in _cfg:
    REQUIRED_COHORTS = {k: v["age_bands"] for k, v in _cfg["cohorts"].items()}
    COHORT_TARGET_COLUMN = {k: v["target_column"] for k, v in _cfg["cohorts"].items()}
    COHORT_TARGET_DATE_COLUMN = {k: v["target_date_column"] for k, v in _cfg["cohorts"].items()}
    AGE_BANDS = sorted({ab for bands in REQUIRED_COHORTS.values() for ab in bands})
```

**Impact:** Adding a new cohort now requires only editing `pipeline_config.yaml`.

---

### Phase 3 — Eliminate All Hardcoded Script-Level Constants

Every file with `AGE_BAND = "65-74"` at module level becomes a runtime error if a user
runs a different band. Replace all of them with CLI arguments:

**Before (8_ffa_analysis scripts):**
```python
AGE_BAND = "65-74"          # hardcoded — wrong for any other band
COHORT_NAME = "falls"
```

**After:**
```python
# All configuration via CLI — no module-level hardcoding
if __name__ == "__main__":
    import argparse
    from py_helpers.constants import REQUIRED_COHORTS
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", required=True, choices=list(REQUIRED_COHORTS))
    parser.add_argument("--age-band", required=True)
    args = parser.parse_args()
    COHORT_NAME = args.cohort
    AGE_BAND = args.age_band
```

Files to convert (still have module-level hardcoding after this refactor):
- `8_ffa_analysis/combined_causal_analysis.py`
- `8_ffa_analysis/create_visualizations.py`
- `8_ffa_analysis/interactive_risk_explorer.py`
- `8_ffa_analysis/compare_shap_causal.py`
- `8_ffa_analysis/check_inputs.py`
- `8_ffa_analysis/list_s3_artifacts.py`
- `8_ffa_analysis/test_grouping_conservative_approximation.py`

---

### Phase 4 — Central Validation Helper

Add one function that all CLI scripts call to validate their `--cohort` / `--age-band`
inputs against the live registry:

```python
# py_helpers/constants.py (addition)
def validate_cohort_age_band(cohort: str, age_band: str) -> None:
    """Raise ValueError if the cohort/age_band combination is not in REQUIRED_COHORTS."""
    if cohort not in REQUIRED_COHORTS:
        raise ValueError(
            f"Unknown cohort '{cohort}'. Valid: {sorted(REQUIRED_COHORTS)}"
        )
    if age_band not in REQUIRED_COHORTS[cohort]:
        raise ValueError(
            f"Age band '{age_band}' not valid for cohort '{cohort}'. "
            f"Valid: {REQUIRED_COHORTS[cohort]}"
        )
```

Every CLI `main()` calls this immediately after `parse_args()`. Replaces the scattered
`validate_cohort_name()` calls in `data_utils.py` and the ad-hoc checks elsewhere.

---

### Phase 5 — Dynamic `argparse` `choices=`

Replace every static `choices=["falls", "ed"]` and `choices=["65-74", "75-84"]` with
values pulled from the registry at parse time:

```python
from py_helpers.constants import REQUIRED_COHORTS, AGE_BANDS

parser.add_argument("--cohort",   required=True, choices=sorted(REQUIRED_COHORTS))
parser.add_argument("--age-band", required=True, choices=AGE_BANDS)
```

This means `--help` always shows the correct valid values, and argparse itself rejects
invalid inputs before any script logic runs.

---

### Phase 6 — Orchestrator Reads From Registry

The pipeline orchestrators (`cohort_utils.run_cohort`, `monitor_s3_uploads.py`,
`check_pipeline_status_s3.py`) currently have their own hardcoded cohort lists.
Replace with:

```python
from py_helpers.constants import REQUIRED_COHORTS

for cohort, age_bands in REQUIRED_COHORTS.items():
    for age_band in age_bands:
        # ... run step
```

**Files to update in Phase 6:**
- `py_helpers/cohort_utils.py` — `run_cohort` job builder
- `utility_scripts/check_pipeline_status_s3.py`
- `utility_scripts/monitor_s3_uploads.py`
- `py_helpers/check_cohort_parquet_controls.py`
- `py_helpers/check_model_events_controls.py`

---

### Phase 7 — Feature Importance Heatmap Auto-Ordering

`CANONICAL_AGE_BAND_ORDER` in `feature_importance_heatmap.py` is currently hardcoded.
Derive it from the registry:

```python
from py_helpers.constants import AGE_BANDS
CANONICAL_AGE_BAND_ORDER = AGE_BANDS   # always matches registry order
```

---

### Implementation Order

| Phase | Effort | Risk | Do When |
|---|---|---|---|
| 1 — Add missing registry keys | Low | None | Now |
| 2 — YAML config file + loader | Medium | Low (additive) | Next sprint |
| 4 — `validate_cohort_age_band` helper | Low | None | Now |
| 5 — Dynamic `argparse choices=` | Medium | Low | Next sprint |
| 6 — Orchestrators read from registry | Medium | Medium | After Phase 5 |
| 3 — Eliminate module-level constants | High | Low | After Phase 5 |
| 7 — Heatmap auto-ordering | Low | None | With Phase 3 |

---

### What Adding a New Cohort Will Look Like After This Work

1. Add entry to `pipeline_config.yaml` (or `REQUIRED_COHORTS` in `constants.py`):
   ```yaml
   hip_fracture:
     age_bands: ["65-74", "75-84"]
     target_column: hip_fracture_event
     target_date_column: first_hip_fracture_date
     display_name: Hip Fracture
   ```
2. Add the target column definition to `2_create_cohort/0_create_cohort.py`.
3. Run the pipeline — every script picks up the new cohort automatically via
   `REQUIRED_COHORTS`.
4. **No other file changes required.**
