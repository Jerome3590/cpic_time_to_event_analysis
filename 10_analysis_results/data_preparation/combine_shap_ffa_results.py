#!/usr/bin/env python3
"""
Combine SHAP and FFA outputs into scenario / pseudo-causal interaction artifacts.

Adapted from pgx-analysis. Inputs are Step 7 SHAP outputs and Step 8 FFA outputs;
outputs are dashboard/scenario artifacts used by interaction analysis.
"""

from __future__ import annotations

import argparse
import ast
import json
import logging
import os
import re
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from py_helpers.constants import PROJECT_SLUG, S3_BUCKET  # noqa: E402
from py_helpers.event_density_utils import DENSITY_BINS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _age_band_fname(age_band: str) -> str:
    return age_band.replace("-", "_")


def _read_table(path: Path) -> pd.DataFrame:
    import duckdb

    path_str = str(path).replace("'", "''")
    con = duckdb.connect()
    try:
        if path.suffix.lower() == ".parquet":
            return con.execute(f"SELECT * FROM read_parquet('{path_str}')").df()
        return con.execute(f"SELECT * FROM read_csv_auto('{path_str}')").df()
    finally:
        con.close()


def _normalize_importance(df: pd.DataFrame, source: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["feature", "importance"])
    df = df.copy()
    if "feature" not in df.columns:
        df = df.rename(columns={df.columns[0]: "feature"})
    candidates = [
        "importance",
        "mean_abs_shap",
        "causal_responsibility",
        "causal_importance",
        "normalized_importance",
        "raw_count",
    ]
    imp_col = next((c for c in candidates if c in df.columns and c != "feature"), None)
    if imp_col is None:
        for col in df.columns:
            if col != "feature" and pd.api.types.is_numeric_dtype(df[col]):
                imp_col = col
                break
    if imp_col is None:
        raise ValueError(f"No numeric importance column found for {source}")
    out = df[["feature", imp_col]].copy()
    out.columns = ["feature", "importance"]
    out["feature"] = out["feature"].astype(str)
    out["importance"] = pd.to_numeric(out["importance"], errors="coerce").fillna(0.0)
    return out.groupby("feature", as_index=False)["importance"].max().sort_values(
        "importance", ascending=False
    )


def find_shap_results(
    cohort: str, age_band: str, project_root: Path, bin_name: Optional[str] = None
) -> Tuple[Optional[Path], Optional[Path]]:
    age_band_fname = _age_band_fname(age_band)
    base = f"{cohort}_{age_band_fname}"
    shap_base = project_root / "7_shap_analysis" / "outputs" / cohort / age_band_fname
    shap_dir = shap_base / "bin_models" / bin_name if bin_name else shap_base
    importance = shap_dir / f"{base}_shap_global_importance_xgboost.csv"
    sample = shap_dir / f"{base}_shap_sample_values_xgboost.parquet"
    return (importance if importance.exists() else None, sample if sample.exists() else None)


def find_ffa_results(
    cohort: str, age_band: str, project_root: Path, bin_name: Optional[str] = None
) -> Tuple[Optional[Path], Optional[Path]]:
    age_band_fname = _age_band_fname(age_band)
    age_dirs = [age_band_fname] if age_band_fname == age_band else [age_band_fname, age_band]
    for age_dir in age_dirs:
        base = project_root / "8_ffa_analysis" / "outputs" / cohort / age_dir
        ffa_base = base / "bin_models" / bin_name if bin_name else base
        model_dir = ffa_base / "xgboost"
        explanations = model_dir / "axp_explanations.parquet"
        if not explanations.exists():
            explanations = model_dir / "axp_explanations.csv"
        importance_candidates = [
            model_dir / "feature_importance_axp.parquet",
            model_dir / "feature_importance_axp.csv",
            model_dir / "causal_importance.parquet",
            model_dir / "causal_importance.csv",
        ]
        importance = next((p for p in importance_candidates if p.exists()), None)
        if explanations.exists() and importance is not None:
            return explanations, importance
    return None, None


def load_shap_sample_parquet(path: Path, feature_names: Optional[List[str]] = None) -> Optional[np.ndarray]:
    if path is None or not path.exists():
        return None
    df = _read_table(path)
    df = df.drop(columns=[c for c in ("row_id", "bias", "mi_person_key") if c in df.columns], errors="ignore")
    if feature_names:
        cols = [c for c in feature_names if c in df.columns]
        if cols:
            df = df[cols]
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if not numeric_cols:
        return None
    return df[numeric_cols].to_numpy()


def extract_features_from_ffa_rules(rules: Any) -> Set[str]:
    if rules is None or (isinstance(rules, float) and pd.isna(rules)):
        return set()
    if isinstance(rules, str):
        try:
            rules = ast.literal_eval(rules)
        except Exception:
            return set(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*[<>=]", rules))
    features: Set[str] = set()
    if isinstance(rules, list):
        for rule in rules:
            if isinstance(rule, str):
                features.update(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*[<>=]", rule))
    return features


def calculate_consensus_features(
    shap_importance: pd.DataFrame, ffa_importance: pd.DataFrame, top_k: int = 20
) -> Dict[str, Any]:
    shap_top = set(shap_importance.head(top_k)["feature"].astype(str)) if not shap_importance.empty else set()
    ffa_top = set(ffa_importance.head(top_k)["feature"].astype(str)) if not ffa_importance.empty else set()
    consensus = shap_top & ffa_top
    return {
        "consensus_features": sorted(consensus),
        "shap_only": sorted(shap_top - ffa_top),
        "ffa_only": sorted(ffa_top - shap_top),
        "consensus_count": len(consensus),
        "shap_count": len(shap_top),
        "ffa_count": len(ffa_top),
        "consensus_rate": len(consensus) / top_k if top_k else 0.0,
    }


def _normalize(series: pd.Series) -> pd.Series:
    series = pd.to_numeric(series, errors="coerce").fillna(0.0)
    denom = float(series.max() - series.min())
    if denom <= 0:
        return pd.Series(np.zeros(len(series)), index=series.index)
    return (series - series.min()) / (denom + 1e-10)


def combine_importance_scores(
    shap_importance: pd.DataFrame,
    ffa_importance: pd.DataFrame,
    weight_shap: float = 0.5,
    weight_ffa: float = 0.5,
) -> pd.DataFrame:
    shap = shap_importance.copy() if shap_importance is not None else pd.DataFrame()
    ffa = ffa_importance.copy() if ffa_importance is not None else pd.DataFrame()
    if shap.empty and ffa.empty:
        return pd.DataFrame()
    if not shap.empty:
        shap["shap_norm"] = _normalize(shap["importance"])
    if not ffa.empty:
        ffa["ffa_norm"] = _normalize(ffa["importance"])
    if shap.empty:
        combined = ffa[["feature", "ffa_norm"]].copy()
        combined["shap_norm"] = 0.0
    elif ffa.empty:
        combined = shap[["feature", "shap_norm"]].copy()
        combined["ffa_norm"] = 0.0
    else:
        combined = shap[["feature", "shap_norm"]].merge(
            ffa[["feature", "ffa_norm"]], on="feature", how="outer"
        )
        combined[["shap_norm", "ffa_norm"]] = combined[["shap_norm", "ffa_norm"]].fillna(0.0)
    combined["combined_importance"] = (
        weight_shap * combined["shap_norm"] + weight_ffa * combined["ffa_norm"]
    )
    return combined.sort_values("combined_importance", ascending=False)


def _process_patient_chunk(
    args: Tuple[int, pd.DataFrame, Optional[np.ndarray], List[str], Set[str]]
) -> List[Dict[str, Any]]:
    start_offset, ffa_chunk, shap_values, feature_names, consensus_set = args
    results = []
    for local_i, (idx, row) in enumerate(ffa_chunk.iterrows()):
        row_pos = start_offset + local_i
        matched_rules = row.get("axp", row.get("explanation", row.get("rules", [])))
        ffa_features = extract_features_from_ffa_rules(matched_rules)
        record = {
            "patient_index": int(idx) if isinstance(idx, (int, np.integer)) else str(idx),
            "patient_id": row.get("instance_id", row.get("mi_person_key", idx)),
            "ffa_matched_rules": str(matched_rules),
            "ffa_features": sorted(ffa_features),
            "ffa_rule_count": len(matched_rules) if isinstance(matched_rules, list) else int(bool(str(matched_rules))),
        }
        if shap_values is not None and row_pos < len(shap_values):
            patient_shap = shap_values[row_pos]
            shap_df = pd.DataFrame(
                {"feature": feature_names[: len(patient_shap)], "shap_value": patient_shap}
            ).sort_values("shap_value", ascending=False)
            record["shap_top_positive"] = shap_df.head(5)["feature"].tolist()
            record["shap_top_negative"] = shap_df.tail(5)["feature"].tolist()
            record["shap_total"] = float(np.nansum(patient_shap))
            patient_features = set(shap_df.head(10)["feature"]) | ffa_features
        else:
            record["shap_top_positive"] = []
            record["shap_top_negative"] = []
            record["shap_total"] = None
            patient_features = ffa_features
        record["consensus_features"] = sorted(consensus_set & patient_features)
        results.append(record)
    return results


def generate_patient_explanations(
    shap_values: Optional[np.ndarray],
    ffa_explanations: pd.DataFrame,
    feature_names: List[str],
    n_samples: int = 0,
    global_consensus_features: Optional[List[str]] = None,
    n_workers: int = 1,
) -> pd.DataFrame:
    if ffa_explanations is None or ffa_explanations.empty:
        return pd.DataFrame()
    sample_size = len(ffa_explanations) if n_samples <= 0 else min(n_samples, len(ffa_explanations))
    ffa_sample = ffa_explanations.head(sample_size)
    consensus_set = set(global_consensus_features or [])
    workers = max(1, n_workers if n_workers > 0 else min(4, os.cpu_count() or 1))
    if workers == 1 or sample_size <= 1:
        return pd.DataFrame(_process_patient_chunk((0, ffa_sample, shap_values, feature_names, consensus_set)))
    chunk_size = max(1, (sample_size + workers - 1) // workers)
    chunks = [
        (start, ffa_sample.iloc[start : start + chunk_size].copy(), shap_values, feature_names, consensus_set)
        for start in range(0, sample_size, chunk_size)
    ]
    results: List[Dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        for chunk_results in executor.map(_process_patient_chunk, chunks):
            results.extend(chunk_results)
    return pd.DataFrame(results)


def _feature_type_counts(df: pd.DataFrame) -> Dict[str, int]:
    counts = {"drug": 0, "icd": 0, "cpt": 0, "other": 0}
    if df.empty or "feature" not in df.columns:
        return counts
    for feature in df["feature"].astype(str):
        if feature.startswith("item_drug_") or feature.startswith("drug_"):
            counts["drug"] += 1
        elif feature.startswith("item_icd_") or feature.startswith("icd_"):
            counts["icd"] += 1
        elif feature.startswith("item_cpt_") or feature.startswith("cpt_"):
            counts["cpt"] += 1
        else:
            counts["other"] += 1
    return counts


def generate_dashboard_outputs(
    combined_importance: pd.DataFrame,
    output_dir: Path,
    cohort: str,
    age_band: str,
    top_k: int = 20,
) -> Dict[str, Any]:
    if combined_importance.empty:
        dashboard_data = {
            "cohort": cohort,
            "age_band": age_band,
            "timestamp": datetime.now().isoformat(),
            "ffa_method": "shap_ffa_combined",
            "top_interaction_factors": [],
            "summary": {
                "total_features": 0,
                "top_k": int(top_k),
                "mean_importance": 0.0,
                "max_importance": 0.0,
                "top_feature": None,
                "top_feature_importance": None,
                "feature_type_counts": {"drug": 0, "icd": 0, "cpt": 0, "other": 0},
            },
            "feature_importance": [],
            "notes": {
                "source": "combine_shap_ffa_results",
                "shap_source": "7_shap_analysis",
                "ffa_source": "8_ffa_analysis",
            },
        }
        with open(output_dir / "dashboard_data.json", "w", encoding="utf-8") as f:
            json.dump(dashboard_data, f, indent=2)
        pd.DataFrame().to_csv(output_dir / "top_interaction_factors.csv", index=False)
        pd.DataFrame().to_csv(output_dir / "combined_shap_importance.csv", index=False)
        return dashboard_data

    vals = combined_importance["combined_importance"].fillna(0.0)
    out = combined_importance.copy()
    out["combined_importance_norm"] = _normalize(vals)
    out = out[vals > 0].sort_values("combined_importance", ascending=False)
    all_causal = out.rename(columns={"combined_importance_norm": "interaction_responsibility"}).copy()
    all_causal["shap_importance"] = all_causal.get("shap_norm", all_causal["interaction_responsibility"])
    all_causal["rule_frequency"] = all_causal.get("rule_frequency", 0)
    all_causal["total_rules"] = all_causal.get("total_rules", 0)
    summary = {
        "total_features": int(len(out)),
        "top_k": int(top_k),
        "mean_importance": float(all_causal["interaction_responsibility"].mean()) if len(all_causal) else 0.0,
        "max_importance": float(all_causal["interaction_responsibility"].max()) if len(all_causal) else 0.0,
        "top_feature": all_causal.iloc[0]["feature"] if len(all_causal) else None,
        "top_feature_importance": float(all_causal.iloc[0]["interaction_responsibility"]) if len(all_causal) else None,
        "feature_type_counts": _feature_type_counts(out),
    }
    dashboard_data = {
        "cohort": cohort,
        "age_band": age_band,
        "timestamp": datetime.now().isoformat(),
        "ffa_method": "shap_ffa_combined",
        "top_interaction_factors": all_causal.to_dict("records"),
        "summary": summary,
        "feature_importance": out.head(50).to_dict("records"),
        "notes": {
            "source": "combine_shap_ffa_results",
            "shap_source": "7_shap_analysis",
            "ffa_source": "8_ffa_analysis",
        },
    }
    with open(output_dir / "dashboard_data.json", "w", encoding="utf-8") as f:
        json.dump(dashboard_data, f, indent=2)
    all_causal.head(top_k).to_csv(output_dir / "top_interaction_factors.csv", index=False)
    out.to_csv(output_dir / "combined_shap_importance.csv", index=False)
    return dashboard_data


def generate_summary_report(
    consensus_data: Dict[str, Any],
    combined_importance: pd.DataFrame,
    patient_explanations: pd.DataFrame,
    cohort: str,
    age_band: str,
) -> str:
    counts = _feature_type_counts(combined_importance)
    lines = [
        "=" * 80,
        "SHAP + FFA COMBINED ANALYSIS SUMMARY",
        f"  Cohort: {cohort} / {age_band}",
        "=" * 80,
        "",
        "FEATURE TYPES (combined importance):",
        f"  drug: {counts['drug']}, icd: {counts['icd']}, cpt: {counts['cpt']}, other: {counts['other']}",
        "",
        "CONSENSUS FEATURES:",
        f"  - Consensus features: {consensus_data.get('consensus_count', 0)}",
        f"  - SHAP-only features: {len(consensus_data.get('shap_only', []))}",
        f"  - FFA-only features: {len(consensus_data.get('ffa_only', []))}",
        f"  - Consensus rate: {consensus_data.get('consensus_rate', 0.0):.1%}",
        "",
    ]
    if not combined_importance.empty:
        lines.append("COMBINED FEATURE IMPORTANCE (Top 10):")
        for i, (_, row) in enumerate(combined_importance.head(10).iterrows(), 1):
            lines.append(
                f"  {i}. {row.get('feature', '')}: {row.get('combined_importance', 0):.4f} "
                f"(SHAP: {row.get('shap_norm', 0):.3f}, FFA: {row.get('ffa_norm', 0):.3f})"
            )
        lines.append("")
    if patient_explanations is not None and not patient_explanations.empty:
        lines.append("PATIENT EXPLANATIONS:")
        lines.append(f"  - Total patients analyzed: {len(patient_explanations)}")
        if "consensus_features" in patient_explanations.columns:
            n_consensus = patient_explanations["consensus_features"].apply(lambda x: len(x) > 0).sum()
            lines.append(f"  - Patients with consensus features: {n_consensus}")
        lines.append("")
    lines.append("=" * 80)
    return "\n".join(lines)


def upload_scenario_data_to_dashboard(json_path: Path, cohort: str, age_band: str, bin_name: Optional[str] = None) -> bool:
    try:
        import boto3

        bucket = os.environ.get("S3_DASHBOARD_BUCKET", "jerome-dixon.io")
        prefix = os.environ.get("S3_DASHBOARD_PREFIX", "vcu/cpic-time-to-event").strip("/")
        bin_seg = f"/{bin_name}" if bin_name else ""
        key = f"{prefix}/visualizations/scenario/{cohort}/{age_band}{bin_seg}/scenario_data.json"
        boto3.client("s3").upload_file(
            str(json_path),
            bucket,
            key,
            ExtraArgs={"ContentType": "application/json"},
        )
        logger.info("Uploaded scenario data to s3://%s/%s", bucket, key)
        return True
    except Exception as exc:
        logger.warning("Dashboard S3 upload skipped: %s", exc)
        return False


def upload_outputs_to_gold(output_dir: Path, cohort: str, age_band: str, bin_name: Optional[str] = None) -> List[str]:
    uploaded: List[str] = []
    try:
        from py_helpers.checkpoint_utils import save_step_checkpoint, upload_file_to_s3

        bin_seg = f"/bin_models/{bin_name}" if bin_name else ""
        prefix = f"s3://{S3_BUCKET}/gold/{PROJECT_SLUG}/analysis_visuals/scenario/{cohort}/{age_band}{bin_seg}"
        for name in [
            "dashboard_data.json",
            "combined_importance.csv",
            "combined_shap_importance.csv",
            "top_interaction_factors.csv",
            "consensus_features.json",
            "patient_explanations.csv",
            "summary_report.txt",
        ]:
            local = output_dir / name
            if local.exists():
                uri = f"{prefix}/{name}"
                if upload_file_to_s3(local, uri, logger=logger):
                    uploaded.append(uri)
        if uploaded:
            save_step_checkpoint(
                step_name="10_combined_shap_ffa",
                cohort=cohort,
                age_band=age_band,
                metadata={"bin": bin_name, "n_outputs": len(uploaded)},
                output_paths=uploaded,
            )
    except Exception as exc:
        logger.warning("Gold S3 upload skipped: %s", exc)
    return uploaded


def main() -> None:
    parser = argparse.ArgumentParser(description="Combine SHAP and FFA outputs for scenario analysis")
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--age-band", required=True)
    parser.add_argument("--bin", default=None, choices=list(DENSITY_BINS))
    parser.add_argument("--output-dir", default="10_analysis_results/visualizations/scenario")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--weight-shap", type=float, default=0.5)
    parser.add_argument("--weight-ffa", type=float, default=0.5)
    parser.add_argument("--n-patients", type=int, default=0, help="0 = all available FFA explanations")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--upload-to-dashboard", action="store_true")
    parser.add_argument("--upload-to-gold", action="store_true")
    args = parser.parse_args()

    bin_name = args.bin
    age_band_fname = _age_band_fname(args.age_band)
    out_base = Path(args.output_dir)
    output_dir = out_base / args.cohort / age_band_fname
    if bin_name:
        output_dir = output_dir / "bin_models" / bin_name
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Combining SHAP + FFA for %s/%s%s", args.cohort, args.age_band, f" bin={bin_name}" if bin_name else "")
    shap_path, shap_sample_path = find_shap_results(args.cohort, args.age_band, PROJECT_ROOT, bin_name)
    ffa_explanations_path, ffa_importance_path = find_ffa_results(args.cohort, args.age_band, PROJECT_ROOT, bin_name)

    missing = []
    if shap_path is None:
        missing.append("SHAP importance")
    if shap_sample_path is None:
        missing.append("SHAP sample parquet")
    if ffa_explanations_path is None:
        missing.append("FFA explanations")
    if ffa_importance_path is None:
        missing.append("FFA importance")
    if missing:
        raise FileNotFoundError(
            "Cannot combine SHAP + FFA; missing: "
            + ", ".join(missing)
            + f" for {args.cohort}/{args.age_band}"
        )

    shap_importance = _normalize_importance(_read_table(shap_path), "SHAP")
    ffa_importance = _normalize_importance(_read_table(ffa_importance_path), "FFA")
    ffa_explanations = _read_table(ffa_explanations_path)
    feature_names = shap_importance["feature"].astype(str).tolist() or ffa_importance["feature"].astype(str).tolist()
    shap_values = load_shap_sample_parquet(shap_sample_path, feature_names)

    consensus = calculate_consensus_features(shap_importance, ffa_importance, args.top_k)
    combined = combine_importance_scores(shap_importance, ffa_importance, args.weight_shap, args.weight_ffa)
    patients = generate_patient_explanations(
        shap_values,
        ffa_explanations,
        feature_names,
        n_samples=args.n_patients,
        global_consensus_features=consensus.get("consensus_features"),
        n_workers=args.workers,
    )

    with open(output_dir / "consensus_features.json", "w", encoding="utf-8") as f:
        json.dump(consensus, f, indent=2)
    combined.to_csv(output_dir / "combined_importance.csv", index=False)
    patients.to_csv(output_dir / "patient_explanations.csv", index=False)
    generate_dashboard_outputs(combined, output_dir, args.cohort, args.age_band, args.top_k)
    summary = generate_summary_report(consensus, combined, patients, args.cohort, args.age_band)
    (output_dir / "summary_report.txt").write_text(summary, encoding="utf-8")

    if args.upload_to_dashboard:
        upload_scenario_data_to_dashboard(output_dir / "dashboard_data.json", args.cohort, args.age_band, bin_name)
    if args.upload_to_gold:
        upload_outputs_to_gold(output_dir, args.cohort, args.age_band, bin_name)

    print("\n" + summary)
    logger.info("Wrote combined SHAP + FFA artifacts to %s", output_dir)


if __name__ == "__main__":
    main()
