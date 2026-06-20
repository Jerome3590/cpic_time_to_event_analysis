#!/usr/bin/env bash
#
# Project-specific cleanup for cpic_time_to_event_analysis.
#
# Clears generated pipeline artifacts for the falls/ed time-to-event workflow:
# - Project-scoped S3 artifacts under s3://$CPIC_S3_BUCKET/gold/$CPIC_PROJECT_SLUG/
# - Project-scoped S3 checkpoints under s3://$CPIC_CHECKPOINT_BUCKET/gold/$CPIC_PROJECT_SLUG/pipeline_checkpoints/
# - Generated local project output folders under this repository root
# - Generated EC2/NVMe project output folders under /mnt/nvme/$CPIC_PROJECT_SLUG/
#
# IMPORTANT: This script only deletes local paths under this repository root or the
# project-specific NVMe root, and only deletes S3 paths under the project-specific
# S3 prefix. It does not delete shared EC2/NVMe paths such as /mnt/nvme/gold/medical,
# /mnt/nvme/gold/pharmacy, /mnt/nvme/gold/cohorts, /mnt/nvme/cohorts_staging, or
# /mnt/nvme/4_model_data.
#
# Usage:
#   ./utility_scripts/cleanup_cohort_data.sh [--skip-checkpoints] [--skip-s3] [--skip-local] [--clear-feature-importance] [--clear-athena-qa] [--yes]
#
# Defaults:
#   CPIC_S3_BUCKET=pgxdatalake
#   CPIC_CHECKPOINT_BUCKET=$CPIC_S3_BUCKET
#   CPIC_PROJECT_SLUG=cpic_time_to_event
#   CPIC_NVME_ROOT=/mnt/nvme
#
# By default, Step 3 feature-importance outputs are preserved so downstream steps can reuse
# existing selected features. Pass --clear-feature-importance for a full Step 3 recompute.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SKIP_CHECKPOINTS=false
SKIP_S3=false
SKIP_LOCAL=false
CLEAR_FEATURE_IMPORTANCE=false
CLEAR_ATHENA_QA=false
AUTO_CONFIRM=false

usage() {
    echo "Usage: $0 [--skip-checkpoints] [--skip-s3] [--skip-local] [--clear-feature-importance] [--clear-athena-qa] [--yes]"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-checkpoints)
            SKIP_CHECKPOINTS=true
            shift
            ;;
        --skip-s3)
            SKIP_S3=true
            shift
            ;;
        --skip-local)
            SKIP_LOCAL=true
            shift
            ;;
        --skip-feature-importance)
            # Backward compatible no-op; preserving feature importance is the default.
            shift
            ;;
        --clear-feature-importance)
            CLEAR_FEATURE_IMPORTANCE=true
            shift
            ;;
        --clear-athena-qa)
            CLEAR_ATHENA_QA=true
            shift
            ;;
        --yes)
            AUTO_CONFIRM=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PROJECT_NAME="cpic_time_to_event_analysis"
PROJECT_SLUG="${CPIC_PROJECT_SLUG:-cpic_time_to_event}"
S3_BUCKET="${CPIC_S3_BUCKET:-pgxdatalake}"
CHECKPOINT_BUCKET="${CPIC_CHECKPOINT_BUCKET:-$S3_BUCKET}"
NOTEBOOK_METADATA_BUCKET="${CPIC_NOTEBOOK_METADATA_BUCKET:-mushin-solutions-project-metadata}"
ATHENA_RESULTS_BUCKET="${CPIC_ATHENA_RESULTS_BUCKET:-aws-athena-query-results-us-east-1-535362115856}"
NVME_ROOT="${CPIC_NVME_ROOT:-/mnt/nvme}"
PROJECT_NVME_ROOT="${CPIC_PROJECT_NVME_ROOT:-${NVME_ROOT}/${PROJECT_SLUG}}"

COHORTS=("falls" "ed")
AGE_BANDS=("65-74" "75-84")
EVENT_YEARS=("2016" "2017" "2018" "2019")

S3_PROJECT_ROOT="s3://${S3_BUCKET}/gold/${PROJECT_SLUG}"
S3_CHECKPOINT_ROOT="s3://${CHECKPOINT_BUCKET}/gold/${PROJECT_SLUG}/pipeline_checkpoints"
S3_NOTEBOOK_METADATA_ROOT="s3://${NOTEBOOK_METADATA_BUCKET}/notebooks/cpic-time-to-event-analysis"
S3_CREATE_COHORT_NOTEBOOK_ROOT="s3://${NOTEBOOK_METADATA_BUCKET}/notebooks/create_cohort"
S3_ATHENA_QA_ROOT="s3://${ATHENA_RESULTS_BUCKET}/cpic_time_to_event_qa"

if [ "$PROJECT_NVME_ROOT" = "/" ] || [ "$PROJECT_NVME_ROOT" = "$NVME_ROOT" ]; then
    echo "Invalid project NVMe root: $PROJECT_NVME_ROOT"
    echo "Set CPIC_PROJECT_NVME_ROOT to a project-specific child, for example: ${NVME_ROOT}/${PROJECT_SLUG}"
    exit 1
fi

LOG_FILE="${PROJECT_ROOT}/cleanup_cohort_data_$(date +%Y%m%d_%H%M%S).log"
DELETED_COUNT=0

PROJECT_OUTPUT_DIRS=(
    "2_create_cohort/cohort_metrics"
    "4_model_data/cohort_name=falls"
    "4_model_data/cohort_name=ed"
    "5_pgx_analysis/outputs"
    "6_final_model/outputs"
    "6_final_model/model_outputs"
    "7_shap_analysis/outputs"
    "8_ffa_analysis/results"
    "9_dtw_analysis/outputs"
    "feature_encoding_outputs"
    "logs"
)

FEATURE_IMPORTANCE_LOCAL_DIRS=(
    "3a_feature_importance/outputs"
    "3b_feature_importance_eda/outputs"
    "3_feature_importance/outputs"
)

S3_PRESERVED_BY_DEFAULT=(
    "${S3_PROJECT_ROOT}/feature_importance/"
    "${S3_PROJECT_ROOT}/bupar/"
)

S3_ALWAYS_CLEAN=(
    "${S3_PROJECT_ROOT}/cohorts/"
    "${S3_PROJECT_ROOT}/event_filter/"
    "${S3_PROJECT_ROOT}/dtw_filter/"
    "${S3_PROJECT_ROOT}/pgx_features/"
    "${S3_PROJECT_ROOT}/final_model/"
    "${S3_PROJECT_ROOT}/models/"
    "${S3_PROJECT_ROOT}/analysis_visuals/"
    "${S3_PROJECT_ROOT}/shap_analysis/"
    "${S3_PROJECT_ROOT}/ffa_analysis/"
    "${S3_PROJECT_ROOT}/logs/"
)

S3_NOTEBOOK_METADATA_CLEAN=(
    "${S3_NOTEBOOK_METADATA_ROOT}/"
    "${S3_CREATE_COHORT_NOTEBOOK_ROOT}/"
)

S3_ATHENA_QA_CLEAN=(
    "${S3_ATHENA_QA_ROOT}/"
)

LOCAL_ALWAYS_CLEAN=(
    "${PROJECT_ROOT}/data/gold/cohorts"
    "${PROJECT_NVME_ROOT}/gold/cohorts"
    "${PROJECT_NVME_ROOT}/cohorts_staging"
    "${PROJECT_NVME_ROOT}/4_model_data"
)

log_message() {
    echo "$1" | tee -a "$LOG_FILE"
}

increment_deleted_count() {
    DELETED_COUNT=$((DELETED_COUNT + 1))
}

is_project_s3_path() {
    local path=$1

    case "$path" in
        "${S3_PROJECT_ROOT}/"*|"${S3_CHECKPOINT_ROOT}/"*|"${S3_NOTEBOOK_METADATA_ROOT}/"*|"${S3_CREATE_COHORT_NOTEBOOK_ROOT}/"*|"${S3_ATHENA_QA_ROOT}/"*) return 0 ;;
        *) return 1 ;;
    esac
}

is_project_local_path() {
    local path=$1

    case "$path" in
        "${PROJECT_ROOT}/"*|"${PROJECT_NVME_ROOT}/"*) return 0 ;;
        *) return 1 ;;
    esac
}

check_s3_path() {
    local path=$1
    local description=$2

    if [ "$SKIP_S3" = true ]; then
        log_message "[SKIP S3] $description"
        return 0
    fi

    set +e
    aws s3 ls "$path" &>/dev/null
    local ls_status=$?
    set -e

    if [ "$ls_status" -eq 0 ]; then
        set +e
        local count
        count=$(aws s3 ls "$path" --recursive 2>/dev/null | wc -l | tr -d ' ')
        local size
        size=$(aws s3 ls "$path" --recursive --summarize 2>/dev/null | awk '/Total Size/ {print $3}')
        set -e
        log_message "[S3 EXISTS] $description"
        log_message "           Path: $path"
        log_message "           Files: ${count:-unknown}"
        [ -n "${size:-}" ] && log_message "           Size: ${size} bytes"
    else
        log_message "[S3 MISSING] $description"
        log_message "            Path: $path"
    fi
}

check_local_path() {
    local path=$1
    local description=$2

    if [ "$SKIP_LOCAL" = true ]; then
        log_message "[SKIP LOCAL] $description"
        return 0
    fi

    if [ -d "$path" ] || [ -f "$path" ]; then
        log_message "[LOCAL EXISTS] $description"
        log_message "              Path: $path"
        if [ -d "$path" ]; then
            local count
            count=$(find "$path" -type f 2>/dev/null | wc -l | tr -d ' ')
            local size
            size=$(du -sh "$path" 2>/dev/null | awk '{print $1}')
            log_message "              Files: ${count:-unknown}"
            [ -n "${size:-}" ] && log_message "              Size: $size"
        else
            local size
            size=$(du -sh "$path" 2>/dev/null | awk '{print $1}')
            [ -n "${size:-}" ] && log_message "              Size: $size"
        fi
    else
        log_message "[LOCAL MISSING] $description"
        log_message "               Path: $path"
    fi
}

delete_s3_path() {
    local path=$1
    local description=$2

    if [ "$SKIP_S3" = true ]; then
        echo -e "${YELLOW}[SKIP S3]${NC} $description"
        return 0
    fi

    if ! is_project_s3_path "$path"; then
        echo -e "${RED}[S3 BLOCKED]${NC} Refusing to delete non-project S3 path: $path"
        log_message "[S3 BLOCKED] $description"
        log_message "             Path: $path"
        log_message "             Reason: outside project S3 prefixes"
        log_message ""
        return 1
    fi

    echo -e "${YELLOW}[S3]${NC} Deleting: $description"
    log_message "[S3 DELETE] $description"
    log_message "           Path: $path"

    set +e
    aws s3 ls "$path" &>/dev/null
    local ls_status=$?
    set -e

    if [ "$ls_status" -ne 0 ]; then
        echo -e "${YELLOW}[S3]${NC} Path not found: $description"
        log_message "           Status: NOT FOUND"
        log_message ""
        return 0
    fi

    set +e
    aws s3 rm "$path" --recursive
    local delete_status=$?
    set -e

    if [ "$delete_status" -eq 0 ]; then
        echo -e "${GREEN}[S3]${NC} Deleted: $description"
        log_message "           Status: DELETED"
        increment_deleted_count
    else
        echo -e "${YELLOW}[S3]${NC} Deletion may have failed: $description"
        log_message "           Status: DELETION ATTEMPTED (exit code: $delete_status)"
    fi
    log_message ""
}

delete_local_path() {
    local path=$1
    local description=$2

    if [ "$SKIP_LOCAL" = true ]; then
        echo -e "${YELLOW}[SKIP LOCAL]${NC} $description"
        return 0
    fi

    if ! is_project_local_path "$path"; then
        echo -e "${RED}[LOCAL BLOCKED]${NC} Refusing to delete non-project local path: $path"
        log_message "[LOCAL BLOCKED] $description"
        log_message "                Path: $path"
        log_message "                Reason: outside project root and project NVMe root"
        log_message ""
        return 1
    fi

    echo -e "${YELLOW}[LOCAL]${NC} Deleting: $description"
    log_message "[LOCAL DELETE] $description"
    log_message "              Path: $path"

    if [ ! -d "$path" ] && [ ! -f "$path" ]; then
        echo -e "${YELLOW}[LOCAL]${NC} Path not found: $description"
        log_message "              Status: NOT FOUND"
        log_message ""
        return 0
    fi

    rm -rf "$path"
    echo -e "${GREEN}[LOCAL]${NC} Deleted: $description"
    log_message "              Status: DELETED"
    increment_deleted_count
    log_message ""
}

print_summary() {
    echo "=========================================="
    echo "CPIC Time-to-Event Cleanup"
    echo "=========================================="
    echo "Project root:      $PROJECT_ROOT"
    echo "Project slug:      $PROJECT_SLUG"
    echo "S3 project root:   $S3_PROJECT_ROOT"
    echo "Checkpoint root:   $S3_CHECKPOINT_ROOT"
    echo "Notebook metadata: $S3_NOTEBOOK_METADATA_ROOT"
    echo "Project NVMe root: $PROJECT_NVME_ROOT"
    echo ""
    echo "This script will clear generated artifacts for cohorts: ${COHORTS[*]}"
    echo "Age bands: ${AGE_BANDS[*]}"
    echo "Event years: ${EVENT_YEARS[*]}"
    echo ""
    echo "Preserved always:"
    echo "  - Any local path outside ${PROJECT_ROOT} and ${PROJECT_NVME_ROOT}"
    echo "  - Any S3 path outside ${S3_PROJECT_ROOT}/ and ${S3_CHECKPOINT_ROOT}/"
    if [ "$CLEAR_FEATURE_IMPORTANCE" = false ]; then
        echo "  - Step 3 feature-importance outputs and checkpoints"
    fi
    if [ "$CLEAR_ATHENA_QA" = false ]; then
        echo "  - Athena QA query result files"
    fi
    echo ""
    echo -e "${YELLOW}WARNING: This deletes generated local and S3 data for this project.${NC}"
    echo ""
}

print_summary

if [ "$AUTO_CONFIRM" = false ]; then
    read -r -p "Are you sure you want to continue? Type yes: " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Cleanup cancelled."
        exit 0
    fi
else
    echo "Auto-confirmation enabled (--yes). Proceeding with cleanup..."
fi

log_message "=========================================="
log_message "${PROJECT_NAME} Cleanup Log"
log_message "Started: $(date)"
log_message "Project root: $PROJECT_ROOT"
log_message "Project slug: $PROJECT_SLUG"
log_message "S3 project root: $S3_PROJECT_ROOT"
log_message "=========================================="
log_message ""

echo ""
echo "=========================================="
echo "Scanning existing data..."
echo "=========================================="
log_message "--- Scanning existing data ---"

for path in "${S3_ALWAYS_CLEAN[@]}"; do
    check_s3_path "$path" "Project artifact: $path"
done

if [ "$CLEAR_FEATURE_IMPORTANCE" = true ]; then
    for path in "${S3_PRESERVED_BY_DEFAULT[@]}"; do
        check_s3_path "$path" "Feature importance artifact: $path"
    done
fi

if [ "$SKIP_CHECKPOINTS" = false ]; then
    check_s3_path "$S3_CHECKPOINT_ROOT/" "Project pipeline checkpoints"
fi

for path in "${S3_NOTEBOOK_METADATA_CLEAN[@]}"; do
    check_s3_path "$path" "Notebook metadata artifact: $path"
done

if [ "$CLEAR_ATHENA_QA" = true ]; then
    for path in "${S3_ATHENA_QA_CLEAN[@]}"; do
        check_s3_path "$path" "Athena QA query result artifact: $path"
    done
fi

for path in "${LOCAL_ALWAYS_CLEAN[@]}"; do
    check_local_path "$path" "Generated local data: $path"
done

for rel_path in "${PROJECT_OUTPUT_DIRS[@]}"; do
    check_local_path "${PROJECT_ROOT}/${rel_path}" "Project output: ${rel_path}"
done

if [ "$CLEAR_FEATURE_IMPORTANCE" = true ]; then
    for rel_path in "${FEATURE_IMPORTANCE_LOCAL_DIRS[@]}"; do
        check_local_path "${PROJECT_ROOT}/${rel_path}" "Feature importance output: ${rel_path}"
    done
fi

log_message ""
log_message "--- End of scan ---"
log_message ""

echo ""
echo "=========================================="
echo "Starting cleanup..."
echo "=========================================="
log_message "--- Starting cleanup ---"

for path in "${S3_ALWAYS_CLEAN[@]}"; do
    delete_s3_path "$path" "Project artifact: $path"
done

if [ "$CLEAR_FEATURE_IMPORTANCE" = true ]; then
    for path in "${S3_PRESERVED_BY_DEFAULT[@]}"; do
        delete_s3_path "$path" "Feature importance artifact: $path"
    done
else
    echo "--- Step 3 Feature Importance (preserved) ---"
    log_message "Step 3 feature-importance outputs preserved; use --clear-feature-importance to clear them."
fi

if [ "$SKIP_CHECKPOINTS" = false ]; then
    delete_s3_path "$S3_CHECKPOINT_ROOT/" "Project pipeline checkpoints"
fi

for path in "${S3_NOTEBOOK_METADATA_CLEAN[@]}"; do
    delete_s3_path "$path" "Notebook metadata artifact: $path"
done

if [ "$CLEAR_ATHENA_QA" = true ]; then
    for path in "${S3_ATHENA_QA_CLEAN[@]}"; do
        delete_s3_path "$path" "Athena QA query result artifact: $path"
    done
else
    echo "--- Athena QA results (preserved) ---"
    log_message "Athena QA query result files preserved; use --clear-athena-qa to clear them."
fi

for path in "${LOCAL_ALWAYS_CLEAN[@]}"; do
    delete_local_path "$path" "Generated local data: $path"
done

for rel_path in "${PROJECT_OUTPUT_DIRS[@]}"; do
    delete_local_path "${PROJECT_ROOT}/${rel_path}" "Project output: ${rel_path}"
done

if [ "$CLEAR_FEATURE_IMPORTANCE" = true ]; then
    for rel_path in "${FEATURE_IMPORTANCE_LOCAL_DIRS[@]}"; do
        delete_local_path "${PROJECT_ROOT}/${rel_path}" "Feature importance output: ${rel_path}"
    done
fi

log_message ""
log_message "=========================================="
log_message "Cleanup completed: $(date)"
log_message "Deleted $DELETED_COUNT item groups"
log_message "Log file saved to: $LOG_FILE"
log_message "=========================================="

echo ""
echo "=========================================="
echo -e "${GREEN}Cleanup completed!${NC}"
echo "=========================================="
echo "Deleted $DELETED_COUNT item groups"
echo "Log file saved to: $LOG_FILE"
echo ""
echo "Next steps:"
echo "  1. Re-run Step 2 cohort series:"
echo "     python 2_create_cohort/run_series_falls.py --skip-existing --concurrent-workers 1"
echo "     python 2_create_cohort/run_series_ed.py --skip-existing --concurrent-workers 1"
echo "  2. Re-run Athena cohort QA:"
echo "     python aws/athena/scripts/run_cohort_qa.py"
echo "  3. Re-run Step 3b as needed:"
echo "     python 3b_feature_importance_eda/run_feature_importance_eda.py --cohort falls --age-band <age_band>"
echo "     python 3b_feature_importance_eda/run_feature_importance_eda.py --cohort ed --age-band <age_band>"
echo "  4. Re-run Step 4:"
echo "     python 4_model_data/create_model_data.py --cohort falls --age-band <age_band>"
echo "     python 4_model_data/create_model_data.py --cohort ed --age-band <age_band>"
echo "  5. Re-run Step 6:"
echo "     python 6_final_model/train_final_model.py --cohort falls --age-band <age_band>"
echo "     python 6_final_model/train_final_model.py --cohort ed --age-band <age_band>"
