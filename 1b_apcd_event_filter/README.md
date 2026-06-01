# Step 1b: APCD Event Filter

Filters APCD claims to identify target events: **falls** and **ED visits**.

## Target Outcomes

### Falls
**Included ICD-10-CM prefixes** (wildcard match on first 3+ characters):
- `R29.6` — Tendency to fall
- `T02` — Multiple fractures
- `S12`, `S22`, `S32`, `S42`, `S52`, `S62`, `S72`, `S82`, `S92` — Regional fractures

**Excluded:**
- `Z91.81` — Personal history of falls (historical/administrative, not an acute event)
- CPT `1100F` — Falls risk screening (preventive screening measure, not a fall event)

### ED Visits
Same logic as `pgx-analysis`:
- Place of Service (POS) = 23 (Emergency Room)
- UB-04 Revenue codes: 045x, 0981 (ER-specific)

## TODO
- [ ] Copy `filter_protocol_events.py` from `pgx-analysis/1b_apcd_event_filter/`
- [ ] Update ICD target codes: replace opioid-ED codes with falls codes
- [ ] Add exclusion logic for `Z91.81` and CPT `1100F`
- [ ] Validate event counts against expected prevalence
- [ ] Update `administrative_codes_lookup.json` as new admin codes are identified
