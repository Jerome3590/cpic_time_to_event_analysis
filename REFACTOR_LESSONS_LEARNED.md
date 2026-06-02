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

- [ ] Update `py_helpers/constants.py` — `AGE_BANDS`, `COHORTS`, slug functions
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
