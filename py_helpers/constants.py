# Environment-aware defaults
import os

# Default outputs directory for target artifacts.
DEFAULT_TARGET_OUTPUTS_DIR = os.environ.get(
    'CPIC_TARGET_OUTPUTS_DIR', os.path.join('1a_apcd_input_data', 'outputs')
)

# Richmond, VA zip codes
RICHMOND_ZIP_CODES = {
    '23173', '23218', '23219', '23220', '23221', '23222', '23223', '23224',
    '23225', '23232', '23240', '23241', '23249', '23260', '23261', '23284',
    '23285', '23298'
}

# Drug-name column: values to exclude from model training (not drugs or not useful as features).
# 1036F: CPT Category II tobacco non-user tracking code (not a drug).
# CPT 1100F: Falls risk screening process measure — feature, not outcome.
DRUG_NAMES_EXCLUDED_MODEL_TRAINING = frozenset({
    "Unknown",
    "1036F",
    "1100F",
})

# Substrings to exclude from any feature name (case-insensitive).
# Syringe was removed; it is helpful for identifying diabetics.
FEATURE_SUBSTRINGS_EXCLUDED = frozenset()

# Codes to exclude (lagging/administrative variables)
EXCLUDED_CODES = {
    'Z91.81', 'Z9181',  # History of falling (feature flag, not outcome; see fall_injury_any)
    'R29.6',  'R296',   # Tendency to fall (feature flag, not outcome)
    'W00', 'W01', 'W02', 'W03', 'W04', 'W05', 'W06', 'W07', 'W08', 'W09',  # Fall causes — outcome definition components
    'HCG',    # VHI grouping code
    'hcg',
    'medical_supplies',
    'freestyle_lancets',
}

# Fall injury ICD-10-CM outcome codes — used in event filter (Step 1b).
# fall_injury_any = 1 when BOTH an injury code (FALL_INJURY_ICD_PREFIXES) AND an
# external cause code (FALL_EXTERNAL_CAUSE_PREFIXES) appear on the same encounter.
FALL_INJURY_ICD_PREFIXES = (
    'S',    # S00-S99: injuries to specific body regions
    'T07',  # Unspecified multiple injuries
    'T14',  # Injury of unspecified body region
    'T20', 'T21', 'T22', 'T23', 'T24', 'T25', 'T26', 'T27', 'T28', 'T29',  # Burns/corrosions
    'T30', 'T31', 'T32', 'T33', 'T34',  # Burns + frostbite
    'T79',  # Early complications of trauma
)
FALL_EXTERNAL_CAUSE_PREFIXES = (
    'W00', 'W01', 'W02', 'W03', 'W04', 'W05', 'W06', 'W07', 'W08', 'W09',
    'W10', 'W11', 'W12', 'W13', 'W14', 'W15', 'W16', 'W17', 'W18', 'W19',
)

# Fall injury auxiliary outcome codes
FALL_FRACTURE_CODES = ('T02', 'S12', 'S22', 'S32', 'S42', 'S52', 'S62', 'S72', 'S82', 'S92')
FALL_HEAD_INJURY_PREFIXES = tuple(f'S{i:02d}' for i in range(10))  # S00-S09

# Fall-risk FEATURE flags (NOT outcomes — do not use as labels)
FALL_FEATURE_CODES = {
    'R29.6', 'R296',   # Tendency to fall / repeated falls
    'Z91.81', 'Z9181', # History of falling
    '1100F',           # CPT: falls risk screening (process measure)
}

# Surgical/iatrogenic complication exclusions (T80-T88 are NOT mechanical fall injuries)
SURGICAL_COMPLICATION_PREFIXES = ('T80', 'T81', 'T82', 'T83', 'T84', 'T85', 'T86', 'T87', 'T88')

# ED visit classification (for ed_event target)
ED_PLACE_OF_SERVICE_CODES = {'23'}  # CMS POS 23 = Emergency Room
ED_REVENUE_CODE_PREFIXES = ('045',)  # 045x = Emergency room
ED_REVENUE_CODES_EXACT = {'0981'}    # 0981 = Emergency room services

# All ICD diagnosis code column names (positions 1-10)
ALL_ICD_DIAGNOSIS_COLUMNS = [
    'primary_icd_diagnosis_code',
    'two_icd_diagnosis_code',
    'three_icd_diagnosis_code',
    'four_icd_diagnosis_code',
    'five_icd_diagnosis_code',
    'six_icd_diagnosis_code',
    'seven_icd_diagnosis_code',
    'eight_icd_diagnosis_code',
    'nine_icd_diagnosis_code',
    'ten_icd_diagnosis_code'
]


def get_icd_codes_sql_condition(icd_codes, table_alias=None):
    """
    Generate SQL condition to check for specific ICD codes across ALL diagnosis code positions.
    
    Args:
        icd_codes: Set or list of ICD codes to check
        table_alias: Optional table alias
    
    Returns:
        SQL WHERE condition string checking all 10 ICD diagnosis columns
    """
    prefix = f"{table_alias}." if table_alias else ""
    codes_tuple = tuple(icd_codes)
    
    conditions = [f"{prefix}{col} IN {codes_tuple}" for col in ALL_ICD_DIAGNOSIS_COLUMNS]
    return "(" + " OR ".join(conditions) + ")"


# FpGrowth
TOP_K = 50
MIN_SUPPORT_THRESHOLD = 0.025
MIN_SUPPORT_FINAL = 0.01
MAX_ATTEMPTS = 5
TIMEOUT_SECONDS = 300

# Rule generation
MIN_CONFIDENCE_SMALL = 0.1
MIN_CONFIDENCE_MEDIUM = 0.25
MIN_CONFIDENCE_LARGE = 0.3
MIN_LIFT_SMALL = 0.5
MIN_LIFT_MEDIUM = 0.6
MIN_LIFT_LARGE = 0.7
MIN_SUPPORT_RULE = 0.025
FALLBACK_DELTA = 0.005
MIN_FALLBACK_CONFIDENCE = 0.1
MIN_FALLBACK_LIFT = 0.0


# Pattern metrics
METRIC_COLUMNS = ["support", "confidence", "lift", "certainty"]
MAX_PATTERN_COLUMNS = 15

# AWS configuration
S3_BUCKET = os.environ.get("CPIC_S3_BUCKET", "pgxdatalake")

# Project slug — used to namespace S3 artifacts so multiple projects can share
# the same bucket without path collisions.
PROJECT_SLUG = os.environ.get("CPIC_PROJECT_SLUG", "cpic_time_to_event")

# Existing pipeline paths (no slug — live data already written here; do not rename)
BASE_PATH_COHORT      = f"s3://{S3_BUCKET}/gold/cohorts"
BASE_PATH_FEATURES    = f"s3://{S3_BUCKET}/gold/feature_importance"
BASE_PATH_FINAL_MODEL = f"s3://{S3_BUCKET}/gold/final_model"

# New analysis artifact paths — project-scoped from the start
BASE_PATH_ANALYSIS_VISUALS = f"s3://{S3_BUCKET}/gold/{PROJECT_SLUG}/analysis_visuals"
BASE_PATH_SHAP_ANALYSIS    = f"s3://{S3_BUCKET}/gold/{PROJECT_SLUG}/shap_analysis"
BASE_PATH_FFA_ANALYSIS     = f"s3://{S3_BUCKET}/gold/{PROJECT_SLUG}/ffa_analysis"

MAX_RETRIES = 3
RETRY_DELAY = 2
AWS_REGION = "us-east-1"

# Age bands: 65–85 group only (falls risk is clinically concentrated here)
AGE_BANDS = ['65-74', '75-84']

# Event years for cohort analysis
EVENT_YEARS = ['2016', '2017', '2018', '2019']

# Cohort names
COHORT_NAMES = ['falls', 'ed']

# Pipeline-supported (cohort, age_band) combinations.
# falls: fall_injury_any = 1 (injury S00-S99/T07/T14/T20-T34/T79 + external cause W00-W19)
# ed:    ed_event = 1     (POS=23 or revenue code 045x/0981)
REQUIRED_COHORTS = {
    "falls": list(AGE_BANDS),
    "ed":    list(AGE_BANDS),
}

# Target column per cohort
COHORT_TARGET_COLUMN = {
    "falls": "fall_injury_any",
    "ed":    "ed_event",
}

# Helper function: convert age-band to filename-safe format
def get_target_column(cohort: str) -> str:
    """Return the binary target column name for a given cohort."""
    return COHORT_TARGET_COLUMN.get((cohort or "").strip().lower(), "fall_injury_any")


def get_target_name_by_cohort(cohort: str) -> str:
    """Target display name: falls -> fall_injury_any, ed -> ed_event."""
    return get_target_column(cohort)


def get_cohort_slug_by_cohort(cohort: str) -> str:
    """Cohort slug for S3 paths (same as cohort name in this project)."""
    return (cohort or "").strip().lower()


def get_target_file_suffix(cohort: str) -> str:
    """File suffix for BupaR pre/post target outputs."""
    mapping = {"falls": "fall_injury_any", "ed": "ed_event"}
    return mapping.get((cohort or "").strip().lower(), "target")


def age_band_to_fname(age_band: str) -> str:
    """Convert an age-band like '0-12' to a filename-safe form '0_12'."""
    return age_band.replace('-', '_') if isinstance(age_band, str) else str(age_band)


def get_physical_age_bands_for_gold(age_band: str) -> list:
    """Return the physical age-band partition(s) for gold COHORT data."""
    return [age_band]


def get_physical_age_bands_for_medical_pharmacy(age_band: str) -> list:
    """Return the physical age-band partition(s) for gold MEDICAL and PHARMACY data."""
    return [age_band]


def age_band_partition_candidates(physical_band: str) -> list:
    """
    Return candidate partition folder names for a physical age band (e.g. 85-94).
    Tries hyphen first (85-94), then underscore (85_94) so gold data stored either way is found.
    """
    candidates = [physical_band]
    if "-" in physical_band:
        candidates.append(physical_band.replace("-", "_"))
    return candidates

# Processing Configuration
LOCK_TIMEOUT_HOURS = 6  # Hours before considering a lock stale
DEFAULT_SAMPLE_RATIO = 5  # Default 5x controls per positive case

# Bloom filter configuration
BLOOM_FILTER_FALSE_POSITIVE_RATIO = 0.01  # 1% false positive ratio
DICTIONARY_SIZE_LIMIT_PERCENT = 10  # 10% of row group size (enables Bloom filters)

###############################################################################
# Healthcare Cost Group (HCG) System Documentation
###############################################################################

"""
Milliman HCG (Healthcare Cost Group) System:
A widely used system for categorizing and costing healthcare services. This system helps in
standardizing healthcare service classification and cost analysis across different providers
and settings.

Key Components:
1. HCG Line:
   - A specific code within the HCG system (e.g., "O11" for Emergency Room)
   - Used to identify the type of service provided
   - Based on Virginia APCD data description standards
   - Helps in precise service categorization

2. HCG Setting:
   - Broader categorization of services within the HCG system
   - Examples include: Inpatient, Outpatient, Emergency Room
   - Provides context for the service location and type
   - Used in conjunction with HCG Line for complete service classification

3. VHI Healthcare Pricing Report:
   - Utilizes the Milliman HCG system
   - Analyzes healthcare costs and utilization trends
   - Provides standardized cost comparisons across different service types
   - Helps in understanding healthcare service patterns and costs

Usage in Analysis:
- Service Classification: Using HCG Line and Setting for consistent service categorization
- Cost Analysis: Standardized cost comparisons across different service types
- Trend Analysis: Tracking healthcare utilization patterns
- Quality Metrics: Assessing service delivery patterns and outcomes
"""
