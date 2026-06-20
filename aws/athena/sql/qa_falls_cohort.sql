-- Quick QA for falls cohort parquet outputs.
-- Requires cohorts.cpic_tte_falls_cohort_qa from create_cohort_qa_tables.sql.

-- Partition coverage and patient counts.
SELECT
    event_year,
    age_band,
    COUNT(*) AS rows,
    COUNT(DISTINCT mi_person_key) AS patients,
    COUNT(DISTINCT IF(is_target_case = 1, mi_person_key, NULL)) AS target_patients,
    COUNT(DISTINCT IF(is_target_case = 0, mi_person_key, NULL)) AS control_patients,
    ROUND(
        CAST(COUNT(DISTINCT IF(is_target_case = 0, mi_person_key, NULL)) AS DOUBLE)
        / NULLIF(COUNT(DISTINCT IF(is_target_case = 1, mi_person_key, NULL)), 0),
        2
    ) AS control_to_target_patient_ratio,
    MIN(event_date) AS min_event_date,
    MAX(event_date) AS max_event_date
FROM cohorts.cpic_tte_falls_cohort_qa
GROUP BY 1, 2
ORDER BY 2, 1;

-- Required value sanity.
SELECT
    event_year,
    age_band,
    SUM(IF(mi_person_key IS NULL, 1, 0)) AS null_patient_rows,
    SUM(IF(event_date IS NULL, 1, 0)) AS null_event_date_rows,
    SUM(IF(event_type NOT IN ('medical', 'pharmacy') OR event_type IS NULL, 1, 0)) AS invalid_event_type_rows,
    SUM(IF(is_target_case NOT IN (0, 1) OR is_target_case IS NULL, 1, 0)) AS invalid_is_target_case_rows,
    SUM(IF(target <> is_target_case OR target IS NULL, 1, 0)) AS target_mismatch_rows,
    ARRAY_JOIN(ARRAY_AGG(DISTINCT CAST(target AS VARCHAR)), ',') AS target_values
FROM cohorts.cpic_tte_falls_cohort_qa
GROUP BY 1, 2
ORDER BY 2, 1;

-- Event classifications present in falls outputs.
-- Falls cohorts use patient-level falls materialization, so final event rows
-- are not required to contain event_classification = 'falls'.
SELECT
    event_year,
    age_band,
    event_classification,
    COUNT(*) AS rows,
    COUNT(DISTINCT mi_person_key) AS patients
FROM cohorts.cpic_tte_falls_cohort_qa
GROUP BY 1, 2, 3
ORDER BY 2, 1, 4 DESC;

-- Target/control patient coverage by event type.
SELECT
    event_year,
    age_band,
    event_type,
    is_target_case,
    COUNT(*) AS rows,
    COUNT(DISTINCT mi_person_key) AS patients
FROM cohorts.cpic_tte_falls_cohort_qa
GROUP BY 1, 2, 3, 4
ORDER BY 2, 1, 3, 4;
