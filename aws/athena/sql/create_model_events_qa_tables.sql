-- Athena setup for CPIC time-to-event model-events QA.
--
-- Step 4 writes model_events.parquet under:
--   s3://pgxdatalake/gold/cpic_time_to_event/cohorts_model_data/cohort_name={cohort}/age_band={age_band}/
--
-- This table intentionally includes only the columns needed for QA. Athena reads
-- Parquet columns by name; omitted columns remain unavailable to these QA queries.

CREATE EXTERNAL TABLE IF NOT EXISTS cohorts.cpic_tte_model_events_qa (
    mi_person_key string,
    event_date timestamp,
    event_type string,
    data_source string,
    age_imputed int,
    member_gender string,
    member_race string,
    zip_imputed string,
    county_imputed string,
    payer_imputed string,
    primary_icd_diagnosis_code string,
    two_icd_diagnosis_code string,
    three_icd_diagnosis_code string,
    four_icd_diagnosis_code string,
    five_icd_diagnosis_code string,
    six_icd_diagnosis_code string,
    seven_icd_diagnosis_code string,
    eight_icd_diagnosis_code string,
    nine_icd_diagnosis_code string,
    ten_icd_diagnosis_code string,
    drug_name string,
    therapeutic_class_1 string,
    therapeutic_class_2 string,
    therapeutic_class_3 string,
    procedure_code string,
    hcg_line string,
    hcg_detail string,
    event_classification string,
    event_sequence bigint,
    first_fall_date timestamp,
    first_ed_date timestamp,
    days_to_target_event bigint,
    target int
)
PARTITIONED BY (cohort_name string, age_band string)
STORED AS PARQUET
LOCATION 's3://pgxdatalake/gold/cpic_time_to_event/cohorts_model_data/';

MSCK REPAIR TABLE cohorts.cpic_tte_model_events_qa;
