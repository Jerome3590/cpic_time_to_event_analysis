"""
Final feature importance filters: exclude administrative/Z codes and target-leakage features.
Aligns with 3a_feature_importance/run_mc_feature_importance.py so dashboard JSONs use the same
final FI as downstream steps (Step 4 / Step 6).
"""

from pathlib import Path
from typing import Optional, Set

import pandas as pd

from py_helpers.constants import (
    DRUG_NAMES_EXCLUDED_MODEL_TRAINING,
    FALL_EXTERNAL_CAUSE_PREFIXES,
    FEATURE_SUBSTRINGS_EXCLUDED,
)
from py_helpers.feature_utils import feature_to_code, feature_to_code_type

# Lazy import to avoid circular deps
def _load_administrative_codes_to_exclude(project_root: Path) -> Set[str]:
    """
    Build set of administrative/Z codes to exclude (same logic as run_mc_feature_importance).
    Uses 1b_apcd_event_filter/administrative_codes_lookup.json.
    """
    try:
        from py_helpers.file_resolver import load_administrative_codes
    except ImportError:
        return set()
    codes = load_administrative_codes(project_root)
    if not codes:
        return set()
    exclude: Set[str] = set()
    for code in codes.get("icd", []) + codes.get("cpt", []) + codes.get("drug", []):
        c = str(code).strip()
        if not c:
            continue
        exclude.add(c)
        if c[0].isalpha() and any(x.isdigit() for x in c):
            exclude.add(c.replace(".", ""))
            if "." not in c and len(c) >= 4:
                exclude.add(f"{c[:3]}.{c[3:]}")
    return exclude


def _normalize_feature_for_admin_check(feature: str) -> str:
    """Strip item_ prefix for comparison against administrative code list."""
    return str(feature).strip().removeprefix("item_")


def is_leakage_feature(feature_name: str) -> bool:
    """
    True if this feature name indicates target leakage (same patterns as
    run_mc_feature_importance._remove_target_leakage_features).
    """
    s = str(feature_name).strip()
    if not s:
        return False
    if s.startswith("post_"):
        return True
    if "time_to" in s.lower() or "time_to_" in s.lower():
        return True
    if any(x in s for x in ["_30d", "_90d", "_180d"]) and "interval" not in s.lower():
        return True
    if s in ("target_time", "first_time"):
        return True
    if "dtw" in s.lower():
        return True
    if "fall_injury" in s.lower() or "ed_event" in s.lower():
        return True
    return False


def _looks_like_icd_code(code: str) -> bool:
    """Conservative ICD-9/ICD-10 shape check for raw or normalized feature codes."""
    c = str(code).strip().upper().replace(".", "")
    if len(c) < 3:
        return False
    if c[0].isalpha() and c[1:3].isdigit():
        return True
    # ICD-9 diagnosis/procedure codes are often three to five numeric digits.
    return c.isdigit() and 3 <= len(c) <= 5


def _looks_like_cpt_code(code: str) -> bool:
    """Conservative CPT/HCPCS shape check for raw or normalized feature codes."""
    c = str(code).strip().upper().replace(".", "")
    if c.isdigit() and len(c) == 5:
        return True
    return len(c) == 5 and c[0].isalpha() and c[1:].isdigit()


def is_target_definition_feature(feature_name: str, cohort: Optional[str] = None) -> bool:
    """Return True when a feature is part of the cohort target definition."""
    if not cohort:
        return False
    cohort_name = str(cohort).strip().lower()
    if cohort_name != "falls":
        return False

    code = str(feature_to_code(feature_name)).strip().upper().replace(".", "")
    if not code:
        return False
    if not _looks_like_icd_code(code):
        return False

    # Avoid treating drug names that happen to start with "S" as injury ICDs.
    # ICD-10 injury/external-cause target components have a letter + two digits.
    if code.startswith("S") and len(code) >= 3 and code[1:3].isdigit():
        return True
    if code.startswith(("T07", "T14")):
        return True

    external_prefixes = tuple(
        str(prefix).strip().upper().replace(".", "")
        for prefix in FALL_EXTERNAL_CAUSE_PREFIXES
    )
    return code.startswith(external_prefixes)


def identify_fi_filter_reasons(
    df: pd.DataFrame,
    project_root: Path,
    cohort: Optional[str] = None,
    feature_col: str = "feature",
) -> pd.DataFrame:
    """
    Build an auditable feature-filter table for final feature-importance outputs.

    Reasons intentionally mirror the robust Step 3b/Step 6 leakage workflow:
    administrative/code-review exclusions, generic target-leakage naming patterns,
    cohort target-definition ICDs, ED drug-only filtering, and known non-drug
    feature-name exclusions.
    """
    if df is None or df.empty or feature_col not in df.columns:
        return pd.DataFrame(columns=[feature_col, "raw_code", "code_type", "remove", "reasons"])

    admin_exclude = _load_administrative_codes_to_exclude(project_root)
    excluded_drugs_lower = {str(value).strip().lower() for value in DRUG_NAMES_EXCLUDED_MODEL_TRAINING}
    excluded_substrings_lower = {
        str(value).strip().lower()
        for value in FEATURE_SUBSTRINGS_EXCLUDED
        if str(value).strip()
    }

    records = []
    cohort_name = str(cohort).strip().lower() if cohort else ""
    for feature in df[feature_col].astype(str):
        raw_code = feature_to_code(feature)
        code_type = feature_to_code_type(feature)
        reasons = []

        normalized_admin_code = _normalize_feature_for_admin_check(feature)
        if admin_exclude and normalized_admin_code in admin_exclude:
            reasons.append("administrative_or_code_review_exclusion")

        code_normalized = str(raw_code).strip().lower()
        if code_normalized in excluded_drugs_lower:
            reasons.append("known_nonpredictive_drug_name")
        for substring in excluded_substrings_lower:
            if substring in code_normalized:
                reasons.append("known_excluded_feature_substring")
                break

        if is_leakage_feature(feature):
            reasons.append("generic_target_leakage_pattern")

        if is_target_definition_feature(feature, cohort=cohort):
            reasons.append("cohort_target_definition_feature")

        looks_like_non_drug_code = _looks_like_icd_code(raw_code) or _looks_like_cpt_code(raw_code)
        if cohort_name == "ed" and (code_type != "drug" or looks_like_non_drug_code):
            reasons.append("ed_drug_only_modeling_rule")

        records.append(
            {
                feature_col: feature,
                "raw_code": raw_code,
                "code_type": code_type,
                "remove": bool(reasons),
                "reasons": ";".join(sorted(set(reasons))),
            }
        )

    return pd.DataFrame(records)


def filter_fi_df_final(
    df: pd.DataFrame,
    project_root: Path,
    cohort: Optional[str] = None,
    feature_col: str = "feature",
    verbose: bool = False,
) -> pd.DataFrame:
    """
    Keep only final feature importance rows: drop administrative/Z codes and leakage features.
    For ed, also keep only drug-name features (same as pipeline).
    """
    if df is None or df.empty or feature_col not in df.columns:
        return df
    out = df.copy()
    reasons = identify_fi_filter_reasons(
        out,
        project_root=project_root,
        cohort=cohort,
        feature_col=feature_col,
    )
    remove_mask = reasons["remove"].to_numpy()
    if verbose and remove_mask.any():
        counts = (
            reasons.loc[reasons["remove"], "reasons"]
            .str.get_dummies(sep=";")
            .sum()
            .sort_values(ascending=False)
        )
        for reason, count in counts.items():
            print(f"[FI filter] Removed {int(count)} row(s): {reason}")
    out = out.loc[~remove_mask].copy()

    return out.reset_index(drop=True)
