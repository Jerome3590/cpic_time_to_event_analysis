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

## Clinical Coding Notes

### Code sequencing
ICD-10-CM coding guidance sequences the injury (S/T code) as the primary diagnosis and the external cause (W00–W19) as a secondary code. For labeling purposes, sequencing order does not matter — only that **both appear on the same encounter**.

### Optional inclusions (research-dependent)
- **T36–T65** (poisoning, toxic effects): include only if medication-related injuries from falls are in scope. Most fall-injury algorithms treat poisonings separately and exclude them from the injury criterion.
- **T80–T88** (complications of surgical/medical care): exclude by default; include only if iatrogenic complications following a fall injury are explicitly in scope.

### Feature codes (output from this step for downstream use)
The following codes are excluded from the outcome but should be passed forward as binary feature flags:

| Code | Feature column | Clinical meaning |
|------|----------------|-----------------|
| R29.6 | `r29_6_flag` | Tendency to fall / repeated falls |
| Z91.81 | `z91_81_flag` | Personal history of falling |
| CPT 1100F | `cpt_1100f_flag` | Falls risk screening performed |

---

## References
- ICD-10-CM Chapter 19 (S00–T88): <https://www.aapc.com/codes/icd-10-codes-range/S00-T88/>
- ICD-10-CM Chapter 20 external cause fall codes (W00–W19): <https://www.aapc.com/codes/icd-10-codes-range/V00-Y99/V00-X58/W00-X58/W00-W19/>
- CDC injury matrix reference: <https://www.cdc.gov/nchs/injury/injury_matrices.htm>
- Coding guidance for fall injuries: <https://codingintel.com/diagnosis-coding-for-fall/>
- ICD-10-CM 7th character usage (initial/subsequent/sequela): <https://basicmedicalkey.com/injury-and-certain-other-consequences-of-external-causes-and-external-causes-of-morbidity-icd-10-cm-chapter-19-codes-s00-t88-and-chapter-20-codes-v00-y99/>
- W19 unspecified fall: <https://www.aapc.com/codes/icd-10-codes/W19>
- Z91.81 history of falling: <https://skriber.com/blog/z91-81-icd-10-code-for-history-of-falls>

---

## TODO
- [ ] Copy `filter_protocol_events.py` from `pgx-analysis/1b_apcd_event_filter/`
- [ ] Implement two-criterion `fall_injury_any` label (injury S00–S99/T07/T14/T20–T34/T79 AND W00–W19 on same encounter)
- [ ] Add exclusion logic: exclude `R29.6`, `Z91.81`, CPT `1100F`, and `T80–T88` from outcome — move to feature pipeline
- [ ] Compute auxiliary flags: `fall_injury_serious` and `fall_injury_head`
- [ ] Consider incident-only filter (7th character `A`) — confirm with team
- [ ] Validate event counts against expected prevalence
- [ ] Update `administrative_codes_lookup.json`: add `R29.6`, `Z91.81`, CPT `1100F` as admin exclusions
