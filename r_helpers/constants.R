# ============================================================
# CONSTANTS FOR FEATURE IMPORTANCE ANALYSIS
# ============================================================
# Shared constants matching py_helpers/constants.py

# Age bands: 65-85 group only (falls risk is clinically concentrated here)
AGE_BANDS <- c("65-74", "75-84")

# Event years for cohort analysis
EVENT_YEARS <- c("2016", "2017", "2018", "2019")

# Cohort names
# falls: fall_injury_any = 1
# ed:    ed_event = 1
COHORT_NAMES <- c("falls", "ed")

# Target column per cohort
COHORT_TARGET_COLUMN <- c(
  "falls" = "fall_injury_any",
  "ed"    = "ed_event"
)

# Helper: get target column for a cohort
get_target_column <- function(cohort) {
  col <- COHORT_TARGET_COLUMN[cohort]
  if (is.na(col)) "fall_injury_any" else col
}

