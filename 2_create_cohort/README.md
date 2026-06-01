# Step 2: Cohort Creation

Creates the final analysis cohort with falls and ED visit targets.

## Cohort Definition

- **Index date**: First qualifying `fall_injury_any` event OR ED visit per patient per age band
- **Lookback**: 12 months of prior claims for feature engineering
- **Exclusions**: Patients with < 90 days of enrollment prior to index date
- **Age bands**: **65–74** and **75–84** only (falls risk is clinically concentrated in the 65–85 population)
- **Event years**: 2016, 2017, 2018, 2019

```mermaid
flowchart TD
    A([Virginia APCD Claims]) --> B[Step 1a: Bronze → Silver → Gold\nParquet conversion · Imputation · Cleaning]
    B --> C[Step 1b: Event Filter\nfall_injury_any · ed_event · auxiliary flags]

    C --> D{Age band\nrestriction}
    D -->|65–74| E1[Cohort: falls / 65–74]
    D -->|75–84| E2[Cohort: falls / 75–84]
    D -->|65–74| F1[Cohort: ed / 65–74]
    D -->|75–84| F2[Cohort: ed / 75–84]

    E1 & E2 --> G1[fall_injury_any cohort parquets\ncohort_name=falls · event_year=Y · age_band=Z]
    F1 & F2 --> G2[ed_event cohort parquets\ncohort_name=ed · event_year=Y · age_band=Z]

    G1 & G2 --> H[Step 3a: MC-CV Feature Importance]
    H --> I[Step 3b: BupaR Post-target EDA]
    I --> J[Step 4: Model Data\nmodel_events.parquet]
    J --> K[Steps 5–8: PGx · Final Model · SHAP · FFA]

    style D fill:#fff3cd,stroke:#ffc107
    style G1 fill:#d4edda,stroke:#28a745
    style G2 fill:#d4edda,stroke:#28a745
```

## Target Columns

### Primary outcomes
| Column | Definition |
|--------|------------|
| `fall_injury_any` | 1 if encounter has injury (S00–S99/T07/T14/T20–T34/T79) AND external cause (W00–W19) |
| `ed_event` | 1 if encounter is an ED visit (POS=23 or revenue code 045x/0981) |

### Auxiliary fall outcome flags
| Column | Definition |
|--------|------------|
| `fall_injury_serious` | `fall_injury_any = 1` AND any fracture code (T02, S12, S22, S32, S42, S52, S62, S72, S82, S92) |
| `fall_injury_head` | `fall_injury_any = 1` AND any head injury code S00–S09 |

### Key feature columns (NOT outcomes)
| Column | Note |
|--------|------|
| `r29_6_flag` | R29.6 (tendency to fall / repeated falls) — fall-risk feature, not outcome |
| `z91_81_flag` | Z91.81 (history of falling) — fall-risk feature, not outcome |

## Column Mapping from pgx-analysis
| Old (pgx-analysis) | New (cpic) |
|---|---|
| `opioid_ed_event` | `fall_injury_any` |
| `polypharmacy_ed_event` | `ed_event` |

## TODO
- [ ] Copy `0_create_cohort.py` from `pgx-analysis/2_create_cohort/`
- [ ] Update target columns: `fall_injury_any`, `fall_injury_serious`, `fall_injury_head`, `ed_event`
- [ ] Add feature columns: `r29_6_flag`, `z91_81_flag` (from Step 1b exclusion output)
- [ ] Copy `2_step2_data_quality_qa.py` and update outcome references
- [ ] Copy `3_cohort_final_metrics.py`
- [ ] Update `final_cohort_schema.json` with new target and auxiliary columns
- [x] **Age band restriction: 65–74 and 75–84 only** (falls risk is clinically concentrated in the 65–85 population)
- [ ] Run on EC2 (32-core/1TB instance for full Virginia APCD)
