# Refactor Lessons Learned: Cohort & Age Band Cleanup

**Scope:** Removal of deprecated cohorts (`opioid_ed`, `ed_non_opioid`), restriction of
age bands to `65-74` and `75-84`, removal of opioid ICD code logic (`F1120`), and update
of target date columns to `first_fall_date` / `first_ed_date`.

**Commits:** `97bfda1` → `0a4279c` (6 commits, ~100 files touched)

---

## 0. Leakage Fixes Must Be Ported Across Related Cohort Repos

June 2026 QA identified two leakage classes in the related PGx pipeline that also apply to this CPIC time-to-event repo:

1. **Temporal holdout leakage:** final-model training must keep 2019 as a true holdout and must not reuse pre-fix checkpoints/artifacts.
2. **ED cohort construction asymmetry:** Step 4 ED model data must represent cases and controls with symmetric pre-index windows and row-inclusion filters.

For this repo, the equivalent cohorts are:

| PGx repo | CPIC time-to-event repo | Risk |
|---|---|---|
| `opioid_ed` | final model temporal split for `falls` / `ed` | 2019 holdout records leaking into training artifacts |
| `non_opioid_ed` | `ed` | cases/controls built from asymmetric event windows or filters |

**Required safeguards:**
- Step 4 must support `--force-rebuild` so stale S3/local `model_events.parquet` files are not reused after construction fixes.
- Step 4 must log target-date source/output mappings and non-null case counts.
- Step 4 `ed` cases and controls must both come from gold medical/pharmacy events using comparable 365-day pre-index windows.
- Step 4 `ed` must not apply Step 3b important-item inclusion only to cases while controls retain broad gold histories.
- Step 6 must support and use `--force-retrain` when rerunning after temporal-split or Step 4 construction fixes.
- Notebook orchestration should force-rebuild corrected Step 4 cohorts and force-retrain only those rebuilt downstream models.

**QA checks before accepting metrics:**
- Log patient-level `n_events` distributions by target after Step 4.
- Verify target-date columns (`first_fall_date` / `first_ed_date`) are present and non-null for case rows.
- Verify no 2019 rows appear in training and 2019 is only evaluated as holdout.
- Treat unusually high recall/AUC/PR-AUC as a leakage signal until audited.

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

---

## 10. Plan Extension: Dynamic Target Event Definition (ICD / CPT / HCG / POS / Revenue Codes)

The plan above covers *naming* the target. This section covers making the *clinical
detection logic* (the codes that define what counts as a target event) fully dynamic.

---

### Current State

Target detection codes are currently split across three places:

**`py_helpers/constants.py` — hardcoded detection constants:**
```python
FALL_INJURY_ICD_PREFIXES = ('S', 'T07', 'T14', 'T20', ..., 'T79')
FALL_EXTERNAL_CAUSE_PREFIXES = ('W00', 'W01', ..., 'W19')
ED_PLACE_OF_SERVICE_CODES = {'23'}
ED_REVENUE_CODE_PREFIXES = ('045',)
ED_REVENUE_CODES_EXACT = {'0981'}
```

**`2_create_cohort/0_create_cohort.py` — partial env var override system:**
```python
# These env vars override target detection at cohort-creation time only:
PGX_TARGET_NAME          # cohort display name
PGX_TARGET_ICD_CODES     # exact ICD match
PGX_TARGET_CPT_CODES     # exact CPT match
PGX_TARGET_ICD_PREFIXES  # ICD prefix match
PGX_TARGET_CPT_PREFIXES  # CPT prefix match
```

**`2_create_cohort/check_hcg_drug_dates.py` — HCG codes used for ED identification:**
```python
hcg_condition = """
    (hcg_line = 'P51 - ER Visits and Observation Care' AND hcg_detail = 'P51b - ...')
    OR hcg_line = 'O11 - Emergency Room'
    OR hcg_line = 'P33 - Urgent Care Visits'
"""
```

**Gaps:**
- `PGX_TARGET_*` env vars are only wired into `0_create_cohort.py` — not into
  `constants.py`, `1b_apcd_event_filter/`, or downstream steps
- HCG codes have no env var override path at all
- Revenue codes and POS codes have no env var override path
- The env var system silently ignores unknown var names (no validation)
- There is no single function that returns "the SQL WHERE clause for this cohort's target"

---

### Phase 8A — Unified Target Definition Struct in `constants.py`

Add a `COHORT_TARGET_DEFINITION` dict that captures **all** code types for each cohort:

```python
# py_helpers/constants.py

from dataclasses import dataclass, field
from typing import FrozenSet, Tuple

@dataclass(frozen=True)
class TargetDefinition:
    """Complete clinical definition of a binary target event."""
    target_column: str               # Binary column name in model_events parquet
    target_date_column: str          # Date column (first occurrence)
    display_name: str                # Human-readable label

    # ICD-10 detection (applied across all 10 diagnosis code columns)
    icd_prefixes: Tuple[str, ...] = ()        # startswith match (e.g. 'S', 'T07')
    icd_exact: FrozenSet[str] = field(default_factory=frozenset)  # exact match
    external_cause_prefixes: Tuple[str, ...] = ()  # for fall: W00-W19
    require_external_cause: bool = False       # True: BOTH injury + cause required

    # CPT detection
    cpt_exact: FrozenSet[str] = field(default_factory=frozenset)
    cpt_prefixes: Tuple[str, ...] = ()

    # Place of Service (POS) codes
    pos_codes: FrozenSet[str] = field(default_factory=frozenset)

    # Revenue codes (UB-04)
    revenue_code_prefixes: Tuple[str, ...] = ()
    revenue_codes_exact: FrozenSet[str] = field(default_factory=frozenset)

    # HCG (Milliman Healthcare Cost Group) line values
    hcg_line_values: FrozenSet[str] = field(default_factory=frozenset)
    hcg_detail_values: FrozenSet[str] = field(default_factory=frozenset)


COHORT_TARGET_DEFINITIONS: dict[str, TargetDefinition] = {

    "falls": TargetDefinition(
        target_column="fall_injury_any",
        target_date_column="first_fall_date",
        display_name="Falls",
        icd_prefixes=(
            'S', 'T07', 'T14',
            'T20', 'T21', 'T22', 'T23', 'T24', 'T25', 'T26', 'T27', 'T28', 'T29',
            'T30', 'T31', 'T32', 'T33', 'T34', 'T79',
        ),
        external_cause_prefixes=(
            'W00', 'W01', 'W02', 'W03', 'W04', 'W05', 'W06', 'W07',
            'W08', 'W09', 'W10', 'W11', 'W12', 'W13', 'W14', 'W15',
            'W16', 'W17', 'W18', 'W19',
        ),
        require_external_cause=True,   # injury code AND external cause on same encounter
    ),

    "ed": TargetDefinition(
        target_column="ed_event",
        target_date_column="first_ed_date",
        display_name="Emergency Department",
        pos_codes=frozenset({'23'}),                  # CMS POS 23 = Emergency Room
        revenue_code_prefixes=('045',),               # 045x = Emergency room
        revenue_codes_exact=frozenset({'0981'}),       # 0981 = Emergency room services
        hcg_line_values=frozenset({
            'O11 - Emergency Room',
            'P51 - ER Visits and Observation Care',
            'P33 - Urgent Care Visits',
        }),
        hcg_detail_values=frozenset({
            'P51b - PHY ED Visits and Observation Care - ED Visits',
        }),
    ),
}

# Backward-compat accessors — existing code uses these
COHORT_TARGET_COLUMN = {k: v.target_column for k, v in COHORT_TARGET_DEFINITIONS.items()}
COHORT_TARGET_DATE_COLUMN = {k: v.target_date_column for k, v in COHORT_TARGET_DEFINITIONS.items()}

def get_target_definition(cohort: str) -> TargetDefinition:
    defn = COHORT_TARGET_DEFINITIONS.get((cohort or "").strip().lower())
    if defn is None:
        raise ValueError(f"No target definition for cohort '{cohort}'. "
                         f"Valid: {sorted(COHORT_TARGET_DEFINITIONS)}")
    return defn
```

**Result:** `get_target_definition("falls")` is the single authoritative source for all
fall-related detection codes, usable anywhere in the pipeline.

---

### Phase 8B — SQL Generator Helper

Add a function that converts a `TargetDefinition` into a SQL WHERE clause, so every
step that queries APCD data uses identical detection logic:

```python
# py_helpers/constants.py

def get_target_event_sql(cohort: str, icd_col: str = "primary_icd_diagnosis_code",
                         pos_col: str = "place_of_service_code",
                         revenue_col: str = "revenue_code",
                         hcg_line_col: str = "hcg_line",
                         hcg_detail_col: str = "hcg_detail",
                         all_icd_cols: list = None) -> str:
    """Return a SQL WHERE clause that identifies target events for the given cohort.

    Example:
        sql = get_target_event_sql("ed")
        # Returns: "(place_of_service_code IN ('23') OR revenue_code LIKE '045%' OR ...)"
    """
    defn = get_target_definition(cohort)
    clauses = []
    icd_cols = all_icd_cols or ALL_ICD_DIAGNOSIS_COLUMNS

    # ICD prefix match (across all diagnosis columns)
    if defn.icd_prefixes:
        prefix_conds = [
            " OR ".join(f"{c} LIKE '{p}%'" for c in icd_cols)
            for p in defn.icd_prefixes
        ]
        icd_clause = "(" + " OR ".join(f"({c})" for c in prefix_conds) + ")"

        if defn.require_external_cause and defn.external_cause_prefixes:
            ext_conds = [
                " OR ".join(f"{c} LIKE '{p}%'" for c in icd_cols)
                for p in defn.external_cause_prefixes
            ]
            ext_clause = "(" + " OR ".join(f"({c})" for c in ext_conds) + ")"
            clauses.append(f"({icd_clause} AND {ext_clause})")
        else:
            clauses.append(icd_clause)

    # POS codes
    if defn.pos_codes:
        vals = ", ".join(f"'{v}'" for v in sorted(defn.pos_codes))
        clauses.append(f"({pos_col} IN ({vals}))")

    # Revenue code prefixes
    for prefix in defn.revenue_code_prefixes:
        clauses.append(f"({revenue_col} LIKE '{prefix}%')")

    # Revenue codes exact
    if defn.revenue_codes_exact:
        vals = ", ".join(f"'{v}'" for v in sorted(defn.revenue_codes_exact))
        clauses.append(f"({revenue_col} IN ({vals}))")

    # HCG line values
    if defn.hcg_line_values:
        vals = ", ".join(f"'{v}'" for v in sorted(defn.hcg_line_values))
        clauses.append(f"({hcg_line_col} IN ({vals}))")

    if not clauses:
        raise ValueError(f"Target definition for '{cohort}' produced no SQL conditions.")

    return "(" + "\n   OR ".join(clauses) + ")"
```

**Usage in any pipeline script:**
```python
from py_helpers.constants import get_target_event_sql

target_sql = get_target_event_sql("ed")
query = f"SELECT * FROM medical WHERE {target_sql}"
```

---

### Phase 8C — Wire Into `pipeline_config.yaml`

Extend the YAML schema to carry code definitions, so a user can define a new cohort
entirely in config without editing Python:

```yaml
# pipeline_config.yaml
cohorts:
  falls:
    age_bands: ["65-74", "75-84"]
    target_column: fall_injury_any
    target_date_column: first_fall_date
    display_name: Falls
    detection:
      icd_prefixes: ["S", "T07", "T14", "T20", "T21", "T22", "T23", "T24",
                     "T25", "T26", "T27", "T28", "T29", "T30", "T31", "T32",
                     "T33", "T34", "T79"]
      external_cause_prefixes: ["W00", "W01", "W02", "W03", "W04", "W05",
                                 "W06", "W07", "W08", "W09", "W10", "W11",
                                 "W12", "W13", "W14", "W15", "W16", "W17",
                                 "W18", "W19"]
      require_external_cause: true

  ed:
    age_bands: ["65-74", "75-84"]
    target_column: ed_event
    target_date_column: first_ed_date
    display_name: Emergency Department
    detection:
      pos_codes: ["23"]
      revenue_code_prefixes: ["045"]
      revenue_codes_exact: ["0981"]
      hcg_line_values:
        - "O11 - Emergency Room"
        - "P51 - ER Visits and Observation Care"
        - "P33 - Urgent Care Visits"
      hcg_detail_values:
        - "P51b - PHY ED Visits and Observation Care - ED Visits"

  # Example: new cohort requires only adding this block
  hip_fracture:
    age_bands: ["65-74", "75-84"]
    target_column: hip_fracture_event
    target_date_column: first_hip_fracture_date
    display_name: Hip Fracture
    detection:
      icd_prefixes: ["S72", "S32", "M84.4", "M80"]
      external_cause_prefixes: ["W00", "W01", "W02", "W03", "W04", "W05",
                                 "W06", "W07", "W08", "W09", "W10", "W11",
                                 "W12", "W13", "W14", "W15", "W16", "W17",
                                 "W18", "W19"]
      require_external_cause: false
```

The `_load_pipeline_config()` loader (Phase 2) converts the YAML `detection` block into
a `TargetDefinition` dataclass at import time.

---

### Phase 8D — Connect to Existing `PGX_TARGET_*` Env Vars

The existing env var system in `0_create_cohort.py` is retained for ad-hoc overrides,
but the *default values* are now populated from `COHORT_TARGET_DEFINITIONS` rather than
being absent:

```python
# py_helpers/cohort_utils.py — run_cohort()
from py_helpers.constants import get_target_definition

defn = get_target_definition(job["cohort"])

# Build env vars from the registry — no hardcoded defaults
target_env = {
    "PGX_TARGET_NAME":         defn.target_column,
    "PGX_TARGET_ICD_PREFIXES": ",".join(defn.icd_prefixes),
    "PGX_TARGET_CPT_CODES":    ",".join(defn.cpt_exact),
    # Pass HCG/POS/revenue as new env vars:
    "PGX_TARGET_POS_CODES":       ",".join(defn.pos_codes),
    "PGX_TARGET_REVENUE_PREFIXES":  ",".join(defn.revenue_code_prefixes),
    "PGX_TARGET_HCG_LINE_VALUES": "|".join(defn.hcg_line_values),
}
# Merge into subprocess env
```

Add the corresponding `--target-pos-codes`, `--target-revenue-prefixes`,
`--target-hcg-line-values` arguments to `0_create_cohort.py` to accept these.

---

### Phase 8E — Use `get_target_event_sql()` in Filter Steps

Replace hardcoded detection blocks in:

| File | Current approach | After |
|---|---|---|
| `1b_apcd_event_filter/filter_protocol_events.py` | Hardcoded ICD prefix checks | `get_target_event_sql(cohort)` |
| `2_create_cohort/0_create_cohort.py` | Env var driven, partial | `get_target_definition(cohort)` |
| `2_create_cohort/check_hcg_drug_dates.py` | Hardcoded `hcg_condition` string | `get_target_definition("ed").hcg_line_values` |
| `4_model_data/create_model_data.py` | Ad-hoc target column checks | `get_target_definition(cohort).target_column` |
| `py_helpers/feature_importance_filters.py` | Hardcoded `fall_injury`/`ed_event` strings | `get_target_definition(cohort).target_column` |

---

### Updated Implementation Order (Full Plan)

| Phase | What | Effort | Risk |
|---|---|---|---|
| **1** | Add `COHORT_TARGET_DATE_COLUMN` + `COHORT_DISPLAY_NAME` to `constants.py` | Low | None |
| **4** | `validate_cohort_age_band()` helper | Low | None |
| **8A** | `TargetDefinition` dataclass + `COHORT_TARGET_DEFINITIONS` dict | Medium | Low |
| **8B** | `get_target_event_sql()` helper | Medium | Low |
| **5** | Dynamic `argparse choices=` from registry | Medium | Low |
| **2** | `pipeline_config.yaml` + loader | Medium | Low |
| **8C** | YAML `detection:` block → `TargetDefinition` | Medium | Low |
| **6** | Orchestrators loop over `REQUIRED_COHORTS` | Medium | Medium |
| **8D** | `run_cohort()` builds env vars from registry | Medium | Medium |
| **8E** | Replace hardcoded detection blocks with `get_target_event_sql()` | High | Medium |
| **3** | Eliminate all module-level `AGE_BAND = "..."` constants | High | Low |
| **7** | `CANONICAL_AGE_BAND_ORDER` derived from `AGE_BANDS` | Low | None |

---

### End State: Adding a Completely New Cohort

```yaml
# pipeline_config.yaml — the only file that changes
cohorts:
  hip_fracture:
    age_bands: ["65-74", "75-84"]
    target_column: hip_fracture_event
    target_date_column: first_hip_fracture_date
    display_name: Hip Fracture
    detection:
      icd_prefixes: ["S72"]
      external_cause_prefixes: ["W00", "W01", "W18", "W19"]
      require_external_cause: false
```

```bash
# Run the full pipeline for the new cohort — no code changes
python 2_create_cohort/0_create_cohort.py --cohort hip_fracture --age-band 65-74
python 3a_feature_importance/run_mc_feature_importance.py --cohort hip_fracture --age-band 65-74
# ... all downstream steps work automatically
```
