-- Quick QA for ED cohort parquet outputs.
-- Requires cohorts.cpic_tte_ed_cohort_qa from create_cohort_qa_tables.sql.

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
FROM cohorts.cpic_tte_ed_cohort_qa
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
FROM cohorts.cpic_tte_ed_cohort_qa
GROUP BY 1, 2
ORDER BY 2, 1;

-- ED target pharmacy rows should be within 1-21 days of the target event.
SELECT
    event_year,
    age_band,
    COUNT(*) AS ed_rows,
    MIN(days_to_target_event) AS min_days_to_target_event,
    MAX(days_to_target_event) AS max_days_to_target_event,
    SUM(IF(is_target_case = 1 AND event_type = 'pharmacy' AND days_to_target_event BETWEEN 1 AND 21, 1, 0)) AS target_pharmacy_rows_in_1_21d,
    SUM(IF(is_target_case = 1 AND event_type = 'pharmacy' AND (days_to_target_event IS NULL OR days_to_target_event < 1 OR days_to_target_event > 21), 1, 0)) AS target_pharmacy_rows_outside_1_21d
FROM cohorts.cpic_tte_ed_cohort_qa
GROUP BY 1, 2
ORDER BY 2, 1;

-- Target/control patient coverage by event type.
SELECT
    event_year,
    age_band,
    event_type,
    is_target_case,
    COUNT(*) AS rows,
    COUNT(DISTINCT mi_person_key) AS patients
FROM cohorts.cpic_tte_ed_cohort_qa
GROUP BY 1, 2, 3, 4
ORDER BY 2, 1, 3, 4;
