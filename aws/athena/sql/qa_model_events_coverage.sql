-- Quick QA for Step 4 model_events.parquet outputs.
-- Requires cohorts.cpic_tte_model_events_qa from create_model_events_qa_tables.sql.

-- Partition coverage, event rows, and case/control balance.
SELECT
    cohort_name,
    age_band,
    COUNT(*) AS rows,
    COUNT(DISTINCT mi_person_key) AS patients,
    COUNT(*) FILTER (WHERE target = 1) AS case_rows,
    COUNT(*) FILTER (WHERE target = 0) AS control_rows,
    COUNT(DISTINCT IF(target = 1, mi_person_key, NULL)) AS case_patients,
    COUNT(DISTINCT IF(target = 0, mi_person_key, NULL)) AS control_patients,
    ROUND(
        CAST(COUNT(DISTINCT IF(target = 0, mi_person_key, NULL)) AS DOUBLE)
        / NULLIF(COUNT(DISTINCT IF(target = 1, mi_person_key, NULL)), 0),
        2
    ) AS control_to_case_patient_ratio,
    MIN(event_date) AS min_event_date,
    MAX(event_date) AS max_event_date
FROM cohorts.cpic_tte_model_events_qa
GROUP BY 1, 2
ORDER BY 1, 2;

-- Required value sanity and target-date coverage.
SELECT
    cohort_name,
    age_band,
    SUM(IF(mi_person_key IS NULL, 1, 0)) AS null_patient_rows,
    SUM(IF(event_date IS NULL, 1, 0)) AS null_event_date_rows,
    SUM(IF(target NOT IN (0, 1) OR target IS NULL, 1, 0)) AS invalid_target_rows,
    SUM(IF(cohort_name = 'falls' AND target = 1 AND first_fall_date IS NULL, 1, 0)) AS falls_case_rows_missing_first_fall_date,
    SUM(IF(cohort_name = 'ed' AND target = 1 AND first_ed_date IS NULL, 1, 0)) AS ed_case_rows_missing_first_ed_date,
    SUM(IF(cohort_name = 'falls' AND target = 0 AND first_fall_date IS NOT NULL, 1, 0)) AS falls_control_rows_with_first_fall_date,
    ARRAY_JOIN(ARRAY_AGG(DISTINCT CAST(target AS VARCHAR)), ',') AS target_values
FROM cohorts.cpic_tte_model_events_qa
GROUP BY 1, 2
ORDER BY 1, 2;

-- Post-target leakage check: case rows should be strictly before their target date.
SELECT
    cohort_name,
    age_band,
    COUNT(*) FILTER (WHERE target = 1) AS case_rows,
    SUM(
        IF(
            cohort_name = 'falls'
            AND target = 1
            AND first_fall_date IS NOT NULL
            AND event_date IS NOT NULL
            AND CAST(event_date AS DATE) >= CAST(first_fall_date AS DATE),
            1,
            0
        )
    ) AS falls_case_rows_on_or_after_target,
    SUM(
        IF(
            cohort_name = 'ed'
            AND target = 1
            AND first_ed_date IS NOT NULL
            AND event_date IS NOT NULL
            AND CAST(event_date AS DATE) >= CAST(first_ed_date AS DATE),
            1,
            0
        )
    ) AS ed_case_rows_on_or_after_target
FROM cohorts.cpic_tte_model_events_qa
GROUP BY 1, 2
ORDER BY 1, 2;

-- Target/control rows by event type.
SELECT
    cohort_name,
    age_band,
    event_type,
    target,
    COUNT(*) AS rows,
    COUNT(DISTINCT mi_person_key) AS patients
FROM cohorts.cpic_tte_model_events_qa
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2, 3, 4;

-- ED model data should preserve pharmacy/drug rows for both cases and controls.
SELECT
    cohort_name,
    age_band,
    COUNT(*) FILTER (WHERE drug_name IS NOT NULL) AS drug_rows,
    COUNT(*) FILTER (WHERE target = 1 AND drug_name IS NOT NULL) AS case_drug_rows,
    COUNT(*) FILTER (WHERE target = 0 AND drug_name IS NOT NULL) AS control_drug_rows,
    COUNT(DISTINCT IF(drug_name IS NOT NULL, mi_person_key, NULL)) AS drug_patients
FROM cohorts.cpic_tte_model_events_qa
WHERE cohort_name = 'ed'
GROUP BY 1, 2
ORDER BY 1, 2;
