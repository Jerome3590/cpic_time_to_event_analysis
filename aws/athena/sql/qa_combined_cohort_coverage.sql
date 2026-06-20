-- Combined coverage QA for falls and ED cohort parquet outputs.
-- Requires both QA tables from create_cohort_qa_tables.sql.

WITH combined AS (
    SELECT
        'falls' AS cohort_file,
        event_year,
        age_band,
        mi_person_key,
        is_target_case,
        event_date,
        event_type,
        event_classification,
        target
    FROM cohorts.cpic_tte_falls_cohort_qa
    UNION ALL
    SELECT
        'ed' AS cohort_file,
        event_year,
        age_band,
        mi_person_key,
        is_target_case,
        event_date,
        event_type,
        event_classification,
        target
    FROM cohorts.cpic_tte_ed_cohort_qa
)
SELECT
    cohort_file,
    COUNT(DISTINCT event_year || '/' || age_band) AS partitions,
    COUNT(*) AS rows,
    COUNT(DISTINCT mi_person_key) AS patients,
    COUNT(DISTINCT IF(is_target_case = 1, mi_person_key, NULL)) AS target_patients,
    COUNT(DISTINCT IF(is_target_case = 0, mi_person_key, NULL)) AS control_patients
FROM combined
GROUP BY 1
ORDER BY 1;

-- Per-partition summary for trend and size checks.
WITH combined AS (
    SELECT
        'falls' AS cohort_file,
        event_year,
        age_band,
        mi_person_key,
        is_target_case,
        event_date
    FROM cohorts.cpic_tte_falls_cohort_qa
    UNION ALL
    SELECT
        'ed' AS cohort_file,
        event_year,
        age_band,
        mi_person_key,
        is_target_case,
        event_date
    FROM cohorts.cpic_tte_ed_cohort_qa
)
SELECT
    cohort_file,
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
FROM combined
GROUP BY 1, 2, 3
ORDER BY 1, 3, 2;
