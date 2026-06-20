# final_cohort_schema.py
"""
Schema for the final cohort output of create_cohort.py
- Order matches final_cohort_schema.json
- Includes descriptions and key comments for each field
- Updated to reflect Phase 3 output with fixed 21-day window (multiclass targets removed)
"""

final_cohort_schema = [
    # Unique person identifier
    ("mi_person_key", "str", "Unique masked person key (primary identifier)"),
    
    # Event details
    ("event_date", "timestamp", "Date/time of event"),
    ("event_type", "str", "Type of event: 'medical' or 'pharmacy'"),
    ("data_source", "str", "Source of event data: 'medical' or 'pharmacy'"),
    
    # Demographics (imputed)
    ("age_imputed", "int", "Imputed age at event (1-114)"),
    ("member_gender", "str", "Gender of member (imputed)"),
    ("member_race", "str", "Race/ethnicity of member (imputed)"),
    ("zip_imputed", "str", "ZIP code at date of service (imputed)"),
    ("county_imputed", "str", "County at date of service (imputed)"),
    ("payer_imputed", "str", "Type of insurance payer (imputed)"),
    
    # ALL ICD diagnosis codes (for ML feature discovery) - positions 1-10
    ("primary_icd_diagnosis_code", "str", "Primary ICD diagnosis code (medical events only)"),
    ("two_icd_diagnosis_code", "str", "Second ICD diagnosis code (medical events only)"),
    ("three_icd_diagnosis_code", "str", "Third ICD diagnosis code (medical events only)"),
    ("four_icd_diagnosis_code", "str", "Fourth ICD diagnosis code (medical events only)"),
    ("five_icd_diagnosis_code", "str", "Fifth ICD diagnosis code (medical events only)"),
    ("six_icd_diagnosis_code", "str", "Sixth ICD diagnosis code (medical events only)"),
    ("seven_icd_diagnosis_code", "str", "Seventh ICD diagnosis code (medical events only)"),
    ("eight_icd_diagnosis_code", "str", "Eighth ICD diagnosis code (medical events only)"),
    ("nine_icd_diagnosis_code", "str", "Ninth ICD diagnosis code (medical events only)"),
    ("ten_icd_diagnosis_code", "str", "Tenth ICD diagnosis code (medical events only)"),
    
    # ALL ICD procedure codes (for ML feature discovery) - positions 2-10
    ("two_icd_procedure_code", "str", "Second ICD procedure code (medical events only)"),
    ("three_icd_procedure_code", "str", "Third ICD procedure code (medical events only)"),
    ("four_icd_procedure_code", "str", "Fourth ICD procedure code (medical events only)"),
    ("five_icd_procedure_code", "str", "Fifth ICD procedure code (medical events only)"),
    ("six_icd_procedure_code", "str", "Sixth ICD procedure code (medical events only)"),
    ("seven_icd_procedure_code", "str", "Seventh ICD procedure code (medical events only)"),
    ("eight_icd_procedure_code", "str", "Eighth ICD procedure code (medical events only)"),
    ("nine_icd_procedure_code", "str", "Ninth ICD procedure code (medical events only)"),
    ("ten_icd_procedure_code", "str", "Tenth ICD procedure code (medical events only)"),
    
    # Drug event fields (may be NULL for medical events)
    ("drug_name", "str", "Drug name (pharmacy events only)"),
    ("therapeutic_class_1", "str", "Therapeutic class level 1 (pharmacy events only)"),
    
    # CPT/procedure codes (medical events only)
    ("procedure_code", "str", "Procedure code (medical events only)"),
    ("cpt_mod_1_code", "str", "CPT modifier 1 (medical events only)"),
    ("cpt_mod_2_code", "str", "CPT modifier 2 (medical events only)"),
    
    # HCG fields for ED visit identification (medical events only)
    ("hcg_setting", "str", "Healthcare setting (medical events only)"),
    ("hcg_line", "str", "Healthcare line code - used for ED visit identification (medical events only)"),
    ("hcg_detail", "str", "Healthcare detail (medical events only)"),
    
    # Event classification and sequence
    ("event_classification", "str", "Event classification: 'falls', 'ed', or 'non_target'"),
    ("event_sequence", "int", "Sequential order of events per patient (globally ordered across medical and pharmacy)"),
    
    # Cohort metadata
    # NOTE: target is normalized to match is_target_case for legacy consumers.
    ("target", "int", "Target/control indicator normalized from is_target_case: 1=target case, 0=control"),
    ("cohort_name", "str", "Cohort group name: 'falls' or 'ed'"),
    ("cohort", "str", "Cohort classification label for target/control grouping"),
    
    # Target case indicators
    # NOTE: is_target_case uses a fixed 21-day window for adverse drug event identification (excluding 0-day discharge prescriptions)
    # NOTE: Multiclass targets (7d, 14d, 30d, 45d) have been removed - simplified to single 21-day window
    ("is_target_case", "int", "Target case indicator: 1=target case (drug event 1-21 days before ED), 0=control (ED without qualifying drug event)"),
    
    # Cohort-specific event dates
    # NOTE: first_falls_date is populated for falls cohort targets only (NULL for ed and falls controls)
    # NOTE: first_ed_date is populated for ed cohort only (NULL for falls)
    ("first_falls_date", "timestamp", "Date of first qualifying falls event - falls cohort targets only"),
    ("first_ed_date", "timestamp", "Date of first qualifying ED target event - ed cohort targets only"),
    
    # Temporal analysis
    # NOTE: days_to_target_event is NULL for falls cohort (can be calculated from event_date and first_fall_date)
    # NOTE: days_to_target_event is calculated for ed cohort (used for 21-day window filtering)
    ("days_to_target_event", "int", "Days from event to target event - NULL for falls, calculated for ed")
]
