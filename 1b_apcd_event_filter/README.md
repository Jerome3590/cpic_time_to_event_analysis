# Step 1b: APCD Event Filter

Filters APCD claims to identify target events: **falls** and **ED visits**.

## Target Outcomes

### Falls — `fall_injury_any`

An encounter is labeled `fall_injury_any = 1` when **both** criteria are satisfied on the **same encounter**:

#### Criterion 1 — Injury diagnosis
At least one ICD-10-CM diagnosis code in any of these ranges:

| Range | Description |
|-------|-------------|
| S00–S99 | Injuries to specific body regions (head, neck, thorax, abdomen, extremities, etc.) |
| T07 | Unspecified multiple injuries |
| T14 | Injury of unspecified body region |
| T20–T32 | Burns and corrosions |
| T33–T34 | Frostbite |
| T79 | Certain early complications of trauma (traumatic shock, compartment syndrome) |

#### Criterion 2 — External cause fall code
At least one ICD-10-CM code in **W00–W19** on the same encounter:

| Code | Description |
|------|-------------|
| W00 | Fall due to ice and snow |
| W01 | Fall on same level from slipping, tripping and stumbling |
| W03 | Other fall on same level due to collision with another person |
| W06 | Fall from bed |
| W10 | Fall on and from stairs and steps |
| W11 | Fall on and from ladder |
| W17 | Other fall from one level to another |
| W18 | Other slipping, tripping and stumbling |
| W19 | Unspecified fall |

Implementation rule: `code >= 'W00' and code <= 'W19'` (string comparison after normalizing dots/format).

#### Pseudocode

```text
For each encounter E:

  has_injury = any dx_code in:
      S00–S99 OR T07 OR T14 OR T20–T32 OR T33–T34 OR T79

  has_fall_ecode = any dx_code in W00–W19

  # Optional: only initial encounters
  if incident_only:
      has_injury    = has_injury    AND any matching code with 7th char == 'A'
      has_fall_ecode = has_fall_ecode AND any W00–W19 code with 7th char == 'A'

  fall_injury_any = 1 if has_injury AND has_fall_ecode else 0
```

#### Exclusions (outcome side — treat as features, not outcomes)
- `R29.6` — Tendency to fall / repeated falls → **feature only**
- `Z91.81` — History of falling → **feature only**
- CPT `1100F` — Falls risk screening (process measure) → **feature only**
- `T80–T88` — Complications of surgical/medical care (iatrogenic, not mechanical fall injury)

#### Auxiliary outcome flags
| Flag | Definition |
|------|------------|
| `fall_injury_any` | Injury (S00–T79 subset) AND W00–W19 on same encounter |
| `fall_injury_serious` | `fall_injury_any = 1` AND any fracture: T02.\*, S12.\*, S22.\*, S32.\*, S42.\*, S52.\*, S62.\*, S72.\*, S82.\*, S92.\* |
| `fall_injury_head` | `fall_injury_any = 1` AND any head injury S00–S09 |

---

### ED Visits
Same logic as `pgx-analysis`:
- Place of Service (POS) = 23 (Emergency Room)
- UB-04 Revenue codes: 045x, 0981 (ER-specific)

---

## TODO
- [ ] Copy `filter_protocol_events.py` from `pgx-analysis/1b_apcd_event_filter/`
- [ ] Implement two-criterion `fall_injury_any` label (injury S00–S99/T07/T14/T20–T34/T79 AND W00–W19 on same encounter)
- [ ] Add exclusion logic: exclude `R29.6`, `Z91.81`, CPT `1100F`, and `T80–T88` from outcome — move to feature pipeline
- [ ] Compute auxiliary flags: `fall_injury_serious` and `fall_injury_head`
- [ ] Consider incident-only filter (7th character `A`) — confirm with team
- [ ] Validate event counts against expected prevalence
- [ ] Update `administrative_codes_lookup.json`: add `R29.6`, `Z91.81`, CPT `1100F` as admin exclusions
