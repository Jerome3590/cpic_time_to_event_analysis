# Age Band Scope: 65–85 Only

**Date:** 2026-06  
**Status:** Final — implemented  

---

## Decision Summary

This project restricts analysis to **two age bands only**: `65-74` and `75-84`.

### Rationale

Fall injury risk is clinically concentrated in the **65–85 geriatric population**:

- Falls are the **leading cause of injury death** in adults 65+ (CDC WISQARS)
- Polypharmacy burden peaks in this age group (typically 5+ concurrent medications)
- CPIC pharmacogenomic actionability (CYP2D6, CYP3A4) is most clinically relevant here — sedatives, antihypertensives, and psychotropics are common fall-risk medications
- Virginia APCD data has sufficient volume for both `falls` and `ed` outcomes in this range
- Restricting scope keeps compute tractable: **16 partitions** (2 cohorts × 2 bands × 4 years) vs 128 in the full-band pgx-analysis run

---

## Active Age Bands

| Age Band | Cohorts | Target column | Partitions (band × year) |
|----------|---------|---------------|--------------------------|
| `65-74` | `falls`, `ed` | `fall_injury_any`, `ed_event` | 1 × 4 = 4 each |
| `75-84` | `falls`, `ed` | `fall_injury_any`, `ed_event` | 1 × 4 = 4 each |

**Total: 16 partitions** across 4 event years (2016–2019).

---

## Where This Is Enforced

### `py_helpers/constants.py`

```python
AGE_BANDS = ['65-74', '75-84']

REQUIRED_COHORTS = {
    "falls": ['65-74', '75-84'],
    "ed":    ['65-74', '75-84'],
}
```

### `r_helpers/constants.R`

```r
AGE_BANDS <- c("65-74", "75-84")
COHORT_NAMES <- c("falls", "ed")
```

### Runner scripts

```
2_create_cohort/run_series_falls.py  →  AGE_BANDS_ORDERED = ["65-74", "75-84"]
2_create_cohort/run_series_ed.py     →  AGE_BANDS_ORDERED = ["65-74", "75-84"]
```

### Archived step-level runner notebooks

Standalone runner notebooks for `5_pgx_analysis`, `6_final_model`, and `7_shap_analysis` have been moved to `archive/inactive_notebooks/`. The active consolidated workflow is `3_model_train_shap_ffa.ipynb`, which uses `REQUIRED_COHORTS = ["65-74", "75-84"]` through the shared constants.

---

## ED Cohort Parameters (uniform, no age-band variation needed)

Since both bands are geriatric adults with similar healthcare utilization patterns,
uniform ED filtering parameters apply:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| ED time window | N/A (single encounter label) | `ed_event = 1` on encounter with POS=23 or revenue code 045x/0981 |
| No drug-proximity filter | — | ED cohort is outcome-only; no temporal drug window required |

---

## Fall Cohort Parameters (uniform across both bands)

| Parameter | Value |
|-----------|-------|
| Injury ICD criterion | S00–S99, T07, T14, T20–T34, T79 (any position) |
| External cause criterion | W00–W19 (any position; same patient within `CPIC_FALL_TARGET_WINDOW_DAYS`, default 7 days) |
| Auxiliary: `fall_injury_serious` | + fracture codes T02, S12/22/32/42/52/62/72/82/92 |
| Auxiliary: `fall_injury_head` | + S00–S09 |
| Feature flags (NOT outcomes) | R29.6 (tendency to fall), Z91.81 (history of falls), CPT 1100F |

---

## Excluded Age Bands (vs. pgx-analysis)

The following age bands from the original pgx-analysis are **not used in this project**:

| Age Band | Reason excluded |
|----------|-----------------|
| 0-12 | Fall injury not clinically relevant; insufficient polypharmacy |
| 13-24 | Same; outside geriatric focus |
| 25-44 | Outside geriatric focus |
| 45-54 | Outside geriatric focus |
| 55-64 | Outside geriatric focus |
| 85-114 | Data sparsity in Virginia APCD for this age range |

---

## References

- `py_helpers/constants.py` — `AGE_BANDS`, `REQUIRED_COHORTS`, `COHORT_TARGET_COLUMN`
- `2_create_cohort/README.md` — cohort creation pipeline overview
- `RUNTIME_ENVIRONMENT.md` — EC2 paths, env vars
- `2_create_cohort/README_ec2_32core_1tb_cohort_runs.md` — EC2 runbook
