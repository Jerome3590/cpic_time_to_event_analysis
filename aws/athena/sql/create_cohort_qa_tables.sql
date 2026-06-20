-- Athena setup for CPIC time-to-event cohort QA.
--
-- Run in Athena Query Editor with:
--   Data source: AwsDataCatalog
--   Database: cohorts
--
-- New cohort writes normalize falls and ED outputs to a canonical schema.

CREATE EXTERNAL TABLE IF NOT EXISTS cohorts.cpic_tte_falls_cohort_qa (
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
    drug_name string,
    therapeutic_class_1 string,
    procedure_code string,
    hcg_line string,
    hcg_detail string,
    event_classification string,
    event_sequence bigint,
    target int,
    cohort_name string,
    cohort string,
    is_target_case int,
    first_falls_date timestamp,
    first_ed_date timestamp,
    days_to_target_event int
)
PARTITIONED BY (event_year string, age_band string)
STORED AS PARQUET
LOCATION 's3://pgxdatalake/gold/cpic_time_to_event/cohorts/cohort_name=falls/';

MSCK REPAIR TABLE cohorts.cpic_tte_falls_cohort_qa;

CREATE EXTERNAL TABLE IF NOT EXISTS cohorts.cpic_tte_ed_cohort_qa (
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
    drug_name string,
    therapeutic_class_1 string,
    procedure_code string,
    hcg_line string,
    hcg_detail string,
    event_classification string,
    event_sequence bigint,
    target int,
    cohort_name string,
    cohort string,
    is_target_case int,
    first_falls_date timestamp,
    first_ed_date timestamp,
    days_to_target_event bigint
)
PARTITIONED BY (event_year string, age_band string)
STORED AS PARQUET
LOCATION 's3://pgxdatalake/gold/cpic_time_to_event/cohorts/cohort_name=ed/';

MSCK REPAIR TABLE cohorts.cpic_tte_ed_cohort_qa;
