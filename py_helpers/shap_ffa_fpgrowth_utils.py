"""
Feature importance utilities for dashboard visuals.

Allowed codes for DTW are mandatory from a single source only:
SHAP/FFA Consensus Filter artifacts under 10_analysis_results/visualizations/scenario.
No fallback to Step 3b feature importance or all drug events.
See get_shap_ffa_allowed_codes_by_density_bin.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

import pandas as pd


def _parse_feature_name(feature: str) -> Tuple[str, str]:
    """
    Parse feature name to (code_type, code). Handles "item_<code>", "drug_<code>", "icd_<code>", "cpt_<code>".
    Returns the **code** that matches model data (e.g. LORAZEPAM not drug_LORAZEPAM) for BupaR/DTW filtering.
    Returns: (code_type, code); code_type is 'drug', 'icd', 'cpt', or 'other'.
    """
    if feature is None or (isinstance(feature, float) and pd.isna(feature)):
        return ("other", "")
    feature = str(feature).strip()
    if not feature:
        return ("other", "")
    # Strip known prefixes so we get the code that appears in model data (drug_name, icd columns, procedure_code)
    if feature.startswith("drug_"):
        code = feature[5:].strip()
        return ("drug", code) if code else ("other", "")
    if feature.startswith("icd_"):
        code = feature[4:].strip()
        return ("icd", code) if code else ("other", "")
    if feature.startswith("cpt_"):
        code = feature[4:].strip()
        return ("cpt", code) if code else ("other", "")
    if feature.startswith("item_"):
        code = feature[5:].strip()
        # Handle second-level prefixes (item_drug_X --> drug_X --> X)
        if code.startswith("drug_"):
            code = code[5:].strip()
            return ("drug", code) if code else ("other", "")
        if code.startswith("icd_"):
            code = code[4:].strip()
            return ("icd", code) if code else ("other", "")
        if code.startswith("cpt_"):
            code = code[4:].strip()
            return ("cpt", code) if code else ("other", "")
    else:
        code = feature
    if not code:
        return ("other", "")
    # Non-code features (e.g. n_events, pgx_num_drugs) should not be added to allowed codes
    if "_" in code and not code.replace(".", "").replace("-", "").replace("_", "").isalnum():
        return ("other", "")
    if code.isdigit():
        return ("cpt", code)
    if code[0].isalpha() and len(code) >= 2:
        rest = code[1:].replace(".", "").replace("-", "")
        if rest.isdigit():
            return ("icd", code)
        if len(code) <= 5 and code.isalnum():
            return ("icd", code)
        # Skip numeric/aggregate-like names (e.g. n_events, pgx_num_cpic_drugs)
        if "num_" in code or code.startswith("n_") or "pgx_" in code.lower():
            return ("other", "")
        return ("drug", code)
    if code.replace(".", "").isdigit():
        return ("cpt", code)
    return ("other", "")


def _load_shap_importance(
    cohort: str,
    age_band: str,
    project_root: Optional[Path] = None,
    data_root: Optional[Path] = None,
) -> pd.DataFrame:
    """Load SHAP global importance. Returns DataFrame with columns: feature, importance."""
    age_band_fname = age_band.replace("-", "_")
    base = f"{cohort}_{age_band_fname}"
    filename = f"{base}_shap_global_importance_xgboost.csv"
    candidates = []
    if project_root:
        candidates.append(project_root / "7_shap_analysis" / "outputs" / cohort / age_band_fname / filename)
    if data_root:
        candidates.append(data_root / "gold" / "shap_analysis" / cohort / age_band / filename)
    for path in candidates:
        if path and path.exists():
            df = pd.read_csv(path)
            if "feature" not in df.columns and len(df.columns) >= 1:
                df = df.rename(columns={df.columns[0]: "feature"})
            imp_col = next(
                (c for c in df.columns if "shap" in c.lower() or "importance" in c.lower()),
                df.columns[1] if len(df.columns) > 1 else None,
            )
            if imp_col is None:
                return pd.DataFrame()
            df = df[["feature", imp_col]].copy()
            df.columns = ["feature", "importance"]
            return df
    return pd.DataFrame()


def _load_ffa_importance(
    cohort: str,
    age_band: str,
    project_root: Optional[Path] = None,
    data_root: Optional[Path] = None,
) -> pd.DataFrame:
    """
    Load FFA importance. Returns DataFrame with columns: feature, importance.
    Tries causal_importance.parquet first, then feature_importance_axp.parquet
    (same file Combine step uses) so BupaR finds FFA when SHAP/FFA pipeline completed.
    """
    age_band_fname = age_band.replace("-", "_")
    candidates = []
    if project_root:
        base = project_root / "8_ffa_analysis" / "outputs" / cohort / age_band_fname / "xgboost"
        candidates.append(base / "causal_importance.parquet")
        candidates.append(base / "feature_importance_axp.parquet")
    if data_root:
        base = data_root / "gold" / "ffa_analysis" / cohort / age_band / "xgboost"
        candidates.append(base / "causal_importance.parquet")
        candidates.append(base / "feature_importance_axp.parquet")
    for path in candidates:
        if path and path.exists():
            try:
                df = pd.read_parquet(path)
            except Exception:
                continue
            if "feature" not in df.columns or df.empty:
                continue
            imp_col = next(
                (c for c in df.columns if c != "feature" and ("causal" in c.lower() or "importance" in c.lower())),
                None,
            )
            if imp_col is None and len(df.columns) > 1:
                for c in df.columns:
                    if c != "feature" and pd.api.types.is_numeric_dtype(df[c]):
                        imp_col = c
                        break
            if imp_col is None:
                continue
            df = df[["feature", imp_col]].copy()
            df.columns = ["feature", "importance"]
            return df
    return pd.DataFrame()


def _load_combined_importance_from_dashboard(
    cohort: str,
    age_band: str,
    project_root: Optional[Path] = None,
) -> pd.DataFrame:
    """
    Load combined SHAP+FFA importance from the Combine step output.
    Used as fallback when 7_shap_analysis / 8_ffa_analysis paths are missing.
    Location: 10_analysis_results/visualizations/scenario/{cohort}/{age_band_fname}/combined_importance.csv
    Returns DataFrame with columns: feature, importance.
    """
    if not project_root:
        return pd.DataFrame()
    age_band_fname = age_band.replace("-", "_")
    path = (
        project_root
        / "10_analysis_results"
        / "visualizations"
        / "scenario"
        / cohort
        / age_band_fname
        / "combined_importance.csv"
    )
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path)
        if "feature" not in df.columns or df.empty:
            return pd.DataFrame()
        imp_col = next(
            (
                c
                for c in df.columns
                if c != "feature"
                and ("combined" in c.lower() or "importance" in c.lower())
            ),
            df.columns[1] if len(df.columns) > 1 else None,
        )
        if imp_col is None:
            imp_col = df.columns[1] if len(df.columns) > 1 else None
        if imp_col is None:
            return pd.DataFrame()
        df = df[["feature", imp_col]].copy()
        df.columns = ["feature", "importance"]
        return df
    except Exception:
        return pd.DataFrame()


def _extract_consensus_features(payload: Any) -> Set[str]:
    """Extract the consensus feature list from supported JSON payload shapes."""
    if isinstance(payload, list):
        return {str(x).strip() for x in payload if str(x).strip()}
    if not isinstance(payload, dict):
        return set()
    raw = payload.get("consensus_features", [])
    if isinstance(raw, dict):
        raw = raw.get("features", [])
    if isinstance(raw, list):
        return {str(x).strip() for x in raw if str(x).strip()}
    return set()


def _load_consensus_feature_importance(
    cohort: str,
    age_band: str,
    project_root: Optional[Path] = None,
    bin_name: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load Consensus Filter features and their combined importances.

    Source:
      10_analysis_results/visualizations/scenario/{cohort}/{age_band_fname}/bin_models/{bin}/

    The returned dataframe has columns feature and importance and contains only
    features present in consensus_features.json.
    """
    project_root = project_root or Path.cwd()
    age_band_fname = age_band.replace("-", "_")
    base = (
        Path(project_root)
        / "10_analysis_results"
        / "visualizations"
        / "scenario"
        / cohort
        / age_band_fname
    )
    candidates = []
    if bin_name:
        candidates.append(base / "bin_models" / bin_name)
    else:
        try:
            from py_helpers.event_density_utils import DENSITY_BINS
        except ImportError:
            DENSITY_BINS = ("low", "medium", "high", "extreme")
        candidates.extend(base / "bin_models" / b for b in DENSITY_BINS)
        candidates.append(base)

    frames = []
    for artifact_dir in candidates:
        consensus_path = artifact_dir / "consensus_features.json"
        if not consensus_path.exists():
            continue
        try:
            consensus_features = _extract_consensus_features(
                json.loads(consensus_path.read_text(encoding="utf-8"))
            )
        except Exception:
            consensus_features = set()
        if not consensus_features:
            continue

        combined_path = artifact_dir / "combined_importance.csv"
        if not combined_path.exists():
            combined_path = artifact_dir / "combined_shap_importance.csv"
        if combined_path.exists():
            try:
                df = pd.read_csv(combined_path)
                if "feature" not in df.columns and len(df.columns) >= 1:
                    df = df.rename(columns={df.columns[0]: "feature"})
                imp_col = next(
                    (
                        c
                        for c in df.columns
                        if c != "feature" and ("combined" in c.lower() or "importance" in c.lower())
                    ),
                    None,
                )
                if imp_col is None and len(df.columns) > 1:
                    imp_col = df.columns[1]
                if imp_col:
                    df = df[["feature", imp_col]].copy()
                    df.columns = ["feature", "importance"]
                    df["feature"] = df["feature"].astype(str)
                    df = df[df["feature"].isin(consensus_features)].copy()
                else:
                    df = pd.DataFrame()
            except Exception:
                df = pd.DataFrame()
        else:
            df = pd.DataFrame()

        if df.empty:
            df = pd.DataFrame(
                {"feature": sorted(consensus_features), "importance": 1.0}
            )
        df["importance"] = pd.to_numeric(df["importance"], errors="coerce").fillna(0.0)
        frames.append(df[["feature", "importance"]])

    if not frames:
        return pd.DataFrame(columns=["feature", "importance"])
    out = pd.concat(frames, ignore_index=True)
    return (
        out.groupby("feature", as_index=False)["importance"]
        .max()
        .sort_values("importance", ascending=False)
    )


def get_shap_ffa_important_codes(
    cohort: str,
    age_band: str,
    item_type: str,
    top_n: int = 500,
    project_root: Optional[Path] = None,
    data_root: Optional[Path] = None,
    use_shap: bool = True,
    use_ffa: bool = True,
) -> Set[str]:
    """
    Return the set of item codes (drug/ICD/CPT) from SHAP/FFA Consensus Filter artifacts.

    Single source: 10_analysis_results/visualizations/scenario/{cohort}/{age_band}/bin_models/{bin}.
    No fallback to Step 3b feature importance or all events.
    """
    merged = _load_consensus_feature_importance(cohort, age_band, project_root, bin_name=None)
    if merged.empty:
        return set()
    if "importance" not in merged.columns:
        merged["importance"] = 1.0
    merged = merged.groupby("feature", as_index=False)["importance"].max()
    merged = merged.sort_values("importance", ascending=False).head(top_n)
    # Map to code_type and code
    code_sets = {"drug": set(), "icd": set(), "cpt": set()}
    for feat in merged["feature"].astype(str):
        code_type, code = _parse_feature_name(feat)
        if code and code_type in code_sets:
            code_sets[code_type].add(code)
    if item_type == "drug_name":
        return code_sets["drug"]
    if item_type == "icd_code":
        return code_sets["icd"]
    if item_type == "cpt_code":
        return code_sets["cpt"]
    if item_type == "medical_code":
        return code_sets["drug"] | code_sets["icd"] | code_sets["cpt"]
    return set()


def get_shap_ffa_allowed_codes_combined(
    cohort: str,
    age_band: str,
    top_n: int = 500,
    project_root: Optional[Path] = None,
    data_root: Optional[Path] = None,
    use_shap: bool = True,
    use_ffa: bool = True,
) -> Set[str]:
    """
    Return the union of consensus allowed codes (drug + ICD + CPT) across density bins.
    Single source: SHAP/FFA Consensus Filter artifacts.
    """
    drug = get_shap_ffa_important_codes(
        cohort, age_band, "drug_name", top_n, project_root, data_root, use_shap, use_ffa
    )
    icd = get_shap_ffa_important_codes(
        cohort, age_band, "icd_code", top_n, project_root, data_root, use_shap, use_ffa
    )
    cpt = get_shap_ffa_important_codes(
        cohort, age_band, "cpt_code", top_n, project_root, data_root, use_shap, use_ffa
    )
    return drug | icd | cpt


def get_shap_ffa_allowed_codes_by_density_bin(
    cohort: str,
    age_band: str,
    top_n: int = 500,
    project_root: Optional[Path] = None,
) -> Dict[str, Set[str]]:
    """
    Return consensus allowed codes by density bin.

    Keys are low / medium / high / extreme when corresponding Consensus Filter
    artifacts exist. Each value is the parsed set of drug/ICD/CPT codes from
    consensus features ordered by combined importance.
    """
    try:
        from py_helpers.event_density_utils import DENSITY_BINS
    except ImportError:
        DENSITY_BINS = ("low", "medium", "high", "extreme")
    by_bin: Dict[str, Set[str]] = {}
    for bin_name in DENSITY_BINS:
        df = _load_consensus_feature_importance(cohort, age_band, project_root, bin_name=bin_name)
        codes: Set[str] = set()
        if not df.empty:
            if "importance" in df.columns:
                df = df.sort_values("importance", ascending=False)
            if top_n and top_n > 0:
                df = df.head(top_n)
            for feat in df["feature"].astype(str):
                code_type, code = _parse_feature_name(feat)
                if code and code_type in {"drug", "icd", "cpt"}:
                    codes.add(code)
        if codes:
            by_bin[str(bin_name)] = codes
    return by_bin


def write_shap_ffa_allowed_codes_for_bupar(
    cohort: str,
    age_band: str,
    output_path: Path,
    top_n: int = 500,
    project_root: Optional[Path] = None,
    data_root: Optional[Path] = None,
    use_shap: bool = True,
    use_ffa: bool = True,
) -> bool:
    """
    Write a JSON object of consensus allowed codes by density bin for DTW.
    Returns True if the file was written (at least one code), False if consensus artifacts are missing or empty.
    """
    by_bin = get_shap_ffa_allowed_codes_by_density_bin(
        cohort, age_band, top_n=top_n, project_root=project_root
    )
    if not by_bin:
        return False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({k: sorted(v) for k, v in by_bin.items()}, f, indent=2)
    return True


def _allowed_codes_needs_regen(path: Path) -> bool:
    """
    Return True if the allowed_codes JSON at *path* is missing, empty, or contains
    no drug codes (e.g. stale file that only has CPT/ICD codes from a previous run).
    Used by workflow scripts to decide whether to regenerate rather than reuse.
    """
    if not path.exists() or path.stat().st_size == 0:
        return True
    try:
        codes = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return True
    if not codes:
        return True
    for c in codes:
        code_type, _ = _parse_feature_name(str(c))
        if code_type == "drug":
            return False   # at least one drug code present - file is valid
    return True            # only CPT/ICD/other codes - stale, needs regen


def _load_final_feature_importance(
    cohort: str,
    age_band: str,
    project_root: Optional[Path] = None,
    data_root: Optional[Path] = None,
) -> pd.DataFrame:
    """
    Load Step 3b cohort_feature_importance CSV only. Same input as Step 4 model training and SHAP/FFA.
    No fallback. Raises FileNotFoundError if 3b artifact is missing (pipeline breaks until 3b is run).
    Returns DataFrame with columns: feature, importance.
    """
    project_root = project_root or Path.cwd()
    try:
        from py_helpers.file_resolver import FileResolver
    except ImportError:
        raise FileNotFoundError(
            "FileResolver required to load Step 3b cohort_feature_importance. "
            "Same input as Step 4 model training and SHAP/FFA; no fallback."
        )
    resolver = FileResolver(
        file_type="cohort_feature_importance",
        project_root=project_root,
        cohort=cohort,
        age_band=age_band,
    )
    path = resolver.resolve()
    if not path or not path.exists():
        paths_checked = resolver.get_candidate_paths()
        paths_str = "\n  ".join(str(p) for p in paths_checked) if paths_checked else "(none)"
        raise FileNotFoundError(
            f"Step 3b cohort_feature_importance required (same input as Step 4 model training and SHAP/FFA) but not found for {cohort}/{age_band}. "
            f"Checked:\n  {paths_str}\n"
            "Run 3b_feature_importance_eda first. No fallback."
        )
    df = pd.read_csv(path)
    if "feature" not in df.columns and len(df.columns) >= 1:
        df = df.rename(columns={df.columns[0]: "feature"})
    imp_col = next(
        (c for c in df.columns if c != "feature" and ("importance" in c.lower() or "mean" in c.lower())),
        df.columns[1] if len(df.columns) > 1 else None,
    )
    if imp_col is None and "feature" in df.columns:
        df = df[["feature"]].copy()
        df["importance"] = 1.0
    elif imp_col is not None:
        df = df[["feature", imp_col]].copy()
        df.columns = ["feature", "importance"]
    return df


def get_final_feature_importance_codes(
    cohort: str,
    age_band: str,
    item_type: str,
    top_n: int = 500,
    project_root: Optional[Path] = None,
    data_root: Optional[Path] = None,
) -> Set[str]:
    """
    Return the set of item codes from final (cohort) feature importance for FP-Growth.

    item_type: 'drug_name', 'icd_code', 'cpt_code', or 'medical_code'.
    Used by legacy FP-Growth helpers only; DTW uses Consensus Filter artifacts.
    """
    df = _load_final_feature_importance(cohort, age_band, project_root, data_root)
    if df.empty:
        return set()
    if "importance" not in df.columns:
        df["importance"] = 1.0
    df = df.sort_values("importance", ascending=False).head(top_n)
    code_sets: Dict[str, Set[str]] = {"drug": set(), "icd": set(), "cpt": set()}
    for feat in df["feature"].astype(str):
        code_type, code = _parse_feature_name(feat)
        if code and code_type in code_sets:
            code_sets[code_type].add(code)
    if item_type == "drug_name":
        return code_sets["drug"]
    if item_type == "icd_code":
        return code_sets["icd"]
    if item_type == "cpt_code":
        return code_sets["cpt"]
    if item_type == "medical_code":
        return code_sets["drug"] | code_sets["icd"] | code_sets["cpt"]
    return set()
