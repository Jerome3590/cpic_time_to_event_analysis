# Step 8: FFA + DTW + FP-Growth + BupaR

Causal feature attribution, temporal trajectory analysis, and process mining.

## TODO

### Formal Feature Attribution (FFA)
- [ ] Copy `ffa_analysis.py`, `catboost_axp_explainer.py`, `xgboost_axp_explainer.py`
- [ ] Copy `combined_causal_analysis.py`, `create_visualizations.py`
- [ ] Update target variable references to `falls_event` / `ed_event`
- [ ] Generate causal importance CSVs per bin per age band

### DTW (Dynamic Time Warping)
- [ ] Copy DTW scripts from `pgx-analysis/8_ffa_analysis/`
- [ ] Apply `dtaidistance` to pre-fall medication sequences
- [ ] Research question: Do temporal medication sequences predict fall timing?
- [ ] Cluster patients by drug sequence similarity (falls vs. non-falls)
- [ ] Identify critical time windows before fall events

### FP-Growth
- [ ] Copy `fpgrowth_utils.py`, `create_fpgrowth_visualizations.py` from `py_helpers/`
- [ ] Mine frequent drug combinations in fall-risk patients
- [ ] Focus: polypharmacy patterns (sedatives + antihypertensives, opioids + benzodiazepines)
- [ ] Set minimum support/confidence thresholds appropriate for falls prevalence

### BupaR Process Mining
- [ ] Copy BupaR R scripts from `r_helpers/`
- [ ] Build care pathway process maps for pre-fall clinical sequences
- [ ] Compare: fall-ED pathway vs. non-fall ED pathway vs. fall-non-ED pathway
- [ ] Identify bottleneck transitions in care that precede falls

## Research Questions
1. What temporal medication sequences (DTW clusters) are most predictive of fall events?
2. Which drug-drug interaction patterns (FP-Growth rules) co-occur in high-fall-risk patients?
3. What clinical care pathways (BupaR process maps) precede a fall ED visit vs. non-fall ED visit?
4. Do CPIC pharmacogenomic actionability levels modulate fall risk independent of polypharmacy burden?
5. Does the temporal gap between a high-risk medication prescription and a fall follow a predictable DTW pattern?
