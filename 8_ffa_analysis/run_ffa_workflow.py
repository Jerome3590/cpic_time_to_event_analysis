#!/usr/bin/env python3
"""
Run FFA and combine SHAP + FFA artifacts for one cohort/age band.

This is adapted from pgx-analysis `run_shap_ffa_workflow.py` and produces the
combined scenario / pseudo-causal feature importance artifacts used downstream.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

FFA_DIR = PROJECT_ROOT / "8_ffa_analysis"
if str(FFA_DIR) not in sys.path:
    sys.path.insert(0, str(FFA_DIR))

from py_helpers.constants import PROJECT_SLUG, S3_BUCKET  # noqa: E402
from py_helpers.env_utils import get_workflow_python_bin  # noqa: E402
from py_helpers.event_density_utils import (  # noqa: E402
    DENSITY_BINS,
    cohort_aggregate_final_model_has_artifacts,
    final_model_bin_has_trained_artifacts,
    resolve_step6_cohort_age_dir,
    resolve_step6_train_features_csv,
    validate_per_bin_outputs,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _age_band_fname(age_band: str) -> str:
    return age_band.replace("-", "_")


def _ffa_dirs(cohort: str, age_band: str, bin_name: Optional[str]) -> Tuple[Path, Path]:
    base = PROJECT_ROOT / "8_ffa_analysis" / "outputs" / cohort / _age_band_fname(age_band)
    if bin_name:
        base = base / "bin_models" / bin_name
    return base / "xgboost", base


def _required_ffa_paths(xgb_dir: Path, ffa_base: Path) -> List[Path]:
    return [
        xgb_dir / "feature_importance_axp.parquet",
        xgb_dir / "axp_explanations.parquet",
        ffa_base / "ffa_causal_factors.csv",
    ]


def _ffa_s3_keys(cohort: str, age_band: str, bin_name: Optional[str]) -> List[str]:
    bin_seg = f"/bin_models/{bin_name}" if bin_name else ""
    prefix = f"gold/{PROJECT_SLUG}/ffa_analysis/{cohort}/{age_band}{bin_seg}"
    return [
        f"{prefix}/xgboost/axp_explanations.parquet",
        f"{prefix}/xgboost/feature_importance_axp.parquet",
        f"{prefix}/ffa_causal_factors.csv",
    ]


def _upload_ffa_outputs(
    cohort: str,
    age_band: str,
    bin_name: Optional[str],
    xgb_dir: Path,
    ffa_base: Path,
) -> List[str]:
    uploaded: List[str] = []
    try:
        from py_helpers.checkpoint_utils import save_step_checkpoint, upload_file_to_s3

        mapping = [
            (xgb_dir / "axp_explanations.parquet", _ffa_s3_keys(cohort, age_band, bin_name)[0]),
            (xgb_dir / "feature_importance_axp.parquet", _ffa_s3_keys(cohort, age_band, bin_name)[1]),
            (ffa_base / "ffa_causal_factors.csv", _ffa_s3_keys(cohort, age_band, bin_name)[2]),
        ]
        for local, key in mapping:
            if local.exists():
                uri = f"s3://{S3_BUCKET}/{key}"
                if upload_file_to_s3(local, uri, logger=logger):
                    uploaded.append(uri)
        if uploaded:
            save_step_checkpoint(
                step_name="8_ffa_analysis",
                cohort=cohort,
                age_band=age_band,
                metadata={"bin": bin_name, "n_outputs": len(uploaded)},
                output_paths=uploaded,
            )
    except Exception as exc:
        logger.warning("FFA S3 upload skipped: %s", exc)
    return uploaded


def _download_ffa_outputs(
    cohort: str,
    age_band: str,
    bin_name: Optional[str],
    xgb_dir: Path,
    ffa_base: Path,
) -> bool:
    try:
        from py_helpers.checkpoint_utils import check_step_outputs_exist
        import boto3

        uris = [f"s3://{S3_BUCKET}/{key}" for key in _ffa_s3_keys(cohort, age_band, bin_name)]
        if not check_step_outputs_exist(uris, logger):
            return False
        xgb_dir.mkdir(parents=True, exist_ok=True)
        ffa_base.mkdir(parents=True, exist_ok=True)
        s3 = boto3.client("s3")
        local_paths = [
            xgb_dir / "axp_explanations.parquet",
            xgb_dir / "feature_importance_axp.parquet",
            ffa_base / "ffa_causal_factors.csv",
        ]
        for key, local in zip(_ffa_s3_keys(cohort, age_band, bin_name), local_paths):
            s3.download_file(S3_BUCKET, key, str(local))
            logger.info("Downloaded FFA artifact: s3://%s/%s -> %s", S3_BUCKET, key, local)
        return True
    except Exception as exc:
        logger.warning("Could not download FFA outputs from S3: %s", exc)
        return False


def _shap_dir(cohort: str, age_band: str, bin_name: Optional[str]) -> Path:
    base = PROJECT_ROOT / "7_shap_analysis" / "outputs" / cohort / _age_band_fname(age_band)
    return base / "bin_models" / bin_name if bin_name else base


def _ensure_shap(cohort: str, age_band: str, bin_name: Optional[str], skip_missing_bin: bool) -> None:
    age_band_fname = _age_band_fname(age_band)
    out_dir = _shap_dir(cohort, age_band, bin_name)
    required = out_dir / f"{cohort}_{age_band_fname}_shap_global_importance_xgboost.csv"
    sample = out_dir / f"{cohort}_{age_band_fname}_shap_sample_values_xgboost.parquet"
    if required.exists() and sample.exists():
        logger.info("SHAP outputs already exist for %s/%s%s", cohort, age_band, f" bin={bin_name}" if bin_name else "")
        return
    script = PROJECT_ROOT / "7_shap_analysis" / "run_shap_analysis.py"
    cmd = [str(get_workflow_python_bin()), str(script), "--cohort", cohort, "--age_band", age_band]
    if bin_name:
        cmd.extend(["--bin", bin_name])
    if skip_missing_bin:
        cmd.append("--skip-missing-bin")
    logger.info("Running Step 7 SHAP: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        raise RuntimeError(f"Step 7 SHAP failed with return code {result.returncode}")


def _load_shap_for_ffa(
    cohort: str,
    age_band: str,
    bin_name: Optional[str],
    max_rows: int,
) -> Tuple[dict, Optional[pd.DataFrame]]:
    import duckdb

    age_band_fname = _age_band_fname(age_band)
    base = _shap_dir(cohort, age_band, bin_name)
    csv_path = base / f"{cohort}_{age_band_fname}_shap_global_importance_xgboost.csv"
    parquet_path = base / f"{cohort}_{age_band_fname}_shap_sample_values_xgboost.parquet"
    if not csv_path.exists():
        raise FileNotFoundError(f"SHAP global importance not found: {csv_path}")
    con = duckdb.connect()
    try:
        df_global = con.execute("SELECT feature, mean_abs_shap FROM read_csv_auto(?)", [str(csv_path)]).df()
    finally:
        con.close()
    shap_map = dict(zip(df_global["feature"], df_global["mean_abs_shap"].astype(float), strict=False))
    max_shap = max(shap_map.values()) if shap_map else 1.0
    if max_shap > 0:
        shap_map = {k: v / max_shap for k, v in shap_map.items()}

    shap_values_df = None
    if parquet_path.exists():
        con = duckdb.connect()
        try:
            shap_values_df = con.execute(
                "SELECT * FROM read_parquet(?) LIMIT ?", [str(parquet_path), int(max_rows)]
            ).df()
        finally:
            con.close()
        shap_values_df = shap_values_df.drop(
            columns=[c for c in ("row_id", "bias", "mi_person_key") if c in shap_values_df.columns],
            errors="ignore",
        )
    return shap_map, shap_values_df


def _find_xgboost_json(cohort: str, age_band: str, bin_name: Optional[str]) -> Path:
    age_band_fname = _age_band_fname(age_band)
    base = resolve_step6_cohort_age_dir(PROJECT_ROOT, cohort, age_band)
    bin_base = base / "bin_models" / bin_name if bin_name else base
    candidates = [
        bin_base / "final_model_json" / f"{cohort}_{age_band_fname}_best_xgboost_model.json",
        base / "final_model_json" / f"{cohort}_{age_band_fname}_best_xgboost_model.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(f"XGBoost JSON not found. Checked: {candidates}")


def _find_xgboost_binary(cohort: str, age_band: str, bin_name: Optional[str]) -> Optional[Path]:
    base = resolve_step6_cohort_age_dir(PROJECT_ROOT, cohort, age_band)
    bin_base = base / "bin_models" / bin_name if bin_name else base
    candidates = [
        bin_base / "models" / "xgboost_model.ubj",
        bin_base / "models" / "xgboost_model.model",
        base / "models" / "xgboost_model.ubj",
    ]
    return next((path for path in candidates if path.exists()), None)


def _load_train_features(cohort: str, age_band: str, bin_name: Optional[str], max_rows: int) -> Optional[pd.DataFrame]:
    import duckdb

    csv_path = resolve_step6_train_features_csv(PROJECT_ROOT, cohort, age_band)
    if not csv_path.exists():
        return None
    bin_filter = f" WHERE n_event_bin = '{bin_name}'" if bin_name else ""
    con = duckdb.connect()
    try:
        df = con.execute(
            f"SELECT * FROM read_csv_auto(?){bin_filter} LIMIT ?", [str(csv_path), int(max_rows)]
        ).df()
    finally:
        con.close()
    df = df.drop(columns=[c for c in ("mi_person_key", "target") if c in df.columns], errors="ignore")
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    return df[numeric].copy()


def _run_ffa(
    cohort: str,
    age_band: str,
    bin_name: Optional[str],
    output_dir: Path,
    max_shap_rows: int,
    max_test_rows: int,
) -> pd.DataFrame:
    from ffa_utils import extract_feature_mappings, load_model_json
    from xgboost_axp_explainer import PathConfig, XGBoostSymbolicExplainer

    shap_map, shap_values_df = _load_shap_for_ffa(cohort, age_band, bin_name, max_shap_rows)
    xgb_json = _find_xgboost_json(cohort, age_band, bin_name)
    model_json = load_model_json(xgb_json)
    extract_feature_mappings(model_json)

    if shap_values_df is None or shap_values_df.empty:
        features = list(shap_map.keys())
        shap_values_df = pd.DataFrame(
            np.tile(np.array([list(shap_map.values())]), (min(100, len(shap_map)), 1)),
            columns=features,
        )
        logger.warning("No SHAP sample parquet available; using repeated global SHAP as proxy.")

    path_config = PathConfig(
        model_path=str(xgb_json),
        data_dir=str(output_dir),
        output_dir=str(output_dir),
        tree_rules_path=None,
        age_band=age_band,
        cohort=cohort,
        density_bin=bin_name,
    )
    explainer = XGBoostSymbolicExplainer(
        path_config=path_config,
        shap_importance_map=shap_map,
        shap_values_df=shap_values_df,
    )
    if model_json.get("feature_names"):
        explainer.feature_names = {i: name for i, name in enumerate(model_json["feature_names"])}
    explainer.model_json = model_json
    explainer.fit_from_model_json(model_json)
    logger.info("Explainer fitted with %d rules", len(explainer.rule_clauses))

    counts = defaultdict(int)
    for clause in explainer.rule_clauses:
        for lit in clause or []:
            if lit in getattr(explainer, "id_condition_map", {}):
                feat_idx, _, _ = explainer.id_condition_map[lit]
                feat_name = (explainer.feature_names or {}).get(feat_idx, f"feature_{feat_idx}")
                counts[feat_name] += 1
    total_rule_firings = sum(counts.values()) or 1
    causal = pd.DataFrame(
        [
            {
                "feature": feature,
                "causal_responsibility": (rule_count / total_rule_firings) * shap_map.get(feature, 0.0),
                "shap_importance": shap_map.get(feature, 0.0),
                "rule_frequency": rule_count,
                "total_rules": len(explainer.rule_clauses),
            }
            for feature, rule_count in counts.items()
        ]
    )
    if not causal.empty:
        causal = causal.sort_values("causal_responsibility", ascending=False)

    X_test = _load_train_features(cohort, age_band, bin_name, max_test_rows)
    if X_test is not None and not X_test.empty and model_json.get("feature_names"):
        import xgboost as xgb

        feature_names = model_json["feature_names"]
        X_aligned = X_test.reindex(columns=feature_names, fill_value=0.0)
        booster = xgb.Booster()
        xgb_binary = _find_xgboost_binary(cohort, age_band, bin_name)
        if xgb_binary is not None:
            booster.load_model(str(xgb_binary))
        else:
            booster.load_model(str(xgb_json))
        dmat = xgb.DMatrix(np.asarray(X_aligned, dtype=np.float32), feature_names=feature_names)
        y_pred = (booster.predict(dmat) > 0.5).astype(int)
        axp_df = explainer.explain_dataset(np.asarray(X_aligned, dtype=np.float32), predictions=y_pred, show_progress=True)
        axp_path = output_dir / "axp_explanations.parquet"
        axp_df.to_parquet(axp_path, index=False)
        logger.info("Wrote %s (%d rows)", axp_path, len(axp_df))
    else:
        logger.warning("Training feature sample unavailable; axp_explanations.parquet was not generated.")

    return causal


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FFA and combine SHAP + FFA outputs")
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--age-band", required=True)
    parser.add_argument("--bin", default=None, choices=list(DENSITY_BINS))
    parser.add_argument("--skip-shap", action="store_true")
    parser.add_argument("--skip-combine", action="store_true")
    parser.add_argument("--skip-missing-bin", action="store_true")
    parser.add_argument("--max-shap-rows", type=int, default=5000)
    parser.add_argument("--max-test-rows", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--upload-to-dashboard", action="store_true")
    parser.add_argument("--upload-to-gold", action="store_true", default=True)
    args = parser.parse_args()

    bin_name = args.bin
    if bin_name:
        has_models = final_model_bin_has_trained_artifacts(PROJECT_ROOT, args.cohort, args.age_band, bin_name)
        if not has_models:
            if args.skip_missing_bin:
                logger.info("Skipping missing Step 6 bin model: %s/%s bin=%s", args.cohort, args.age_band, bin_name)
                return
            raise FileNotFoundError(f"No Step 6 per-bin model for {args.cohort}/{args.age_band} bin={bin_name}")
    elif not cohort_aggregate_final_model_has_artifacts(PROJECT_ROOT, args.cohort, args.age_band):
        raise FileNotFoundError(f"No aggregate Step 6 model for {args.cohort}/{args.age_band}")

    validate_per_bin_outputs(
        PROJECT_ROOT,
        args.cohort,
        args.age_band,
        bins=(bin_name,) if bin_name else None,
        raise_on_missing=bool(bin_name),
    )

    xgb_dir, ffa_base = _ffa_dirs(args.cohort, args.age_band, bin_name)
    required = _required_ffa_paths(xgb_dir, ffa_base)
    if all(path.exists() for path in required):
        logger.info("FFA outputs already exist locally; skipping FFA computation.")
    elif _download_ffa_outputs(args.cohort, args.age_band, bin_name, xgb_dir, ffa_base):
        logger.info("Downloaded FFA outputs from project-scoped S3.")
    else:
        if not args.skip_shap:
            _ensure_shap(args.cohort, args.age_band, bin_name, args.skip_missing_bin)
        xgb_dir.mkdir(parents=True, exist_ok=True)
        ffa_base.mkdir(parents=True, exist_ok=True)
        causal = _run_ffa(
            args.cohort,
            args.age_band,
            bin_name,
            xgb_dir,
            args.max_shap_rows,
            args.max_test_rows,
        )
        causal["importance"] = causal.get("causal_responsibility", 0.0)
        causal.to_parquet(xgb_dir / "feature_importance_axp.parquet", index=False)
        causal.to_csv(ffa_base / "ffa_causal_factors.csv", index=False)
        logger.info("Wrote FFA outputs under %s", ffa_base)

    if all(path.exists() for path in required):
        _upload_ffa_outputs(args.cohort, args.age_band, bin_name, xgb_dir, ffa_base)
    else:
        missing = [str(path) for path in required if not path.exists()]
        raise FileNotFoundError("FFA outputs incomplete; missing: " + "; ".join(missing))

    if not args.skip_combine:
        combine_script = PROJECT_ROOT / "10_analysis_results" / "data_preparation" / "combine_shap_ffa_results.py"
        cmd = [
            str(get_workflow_python_bin()),
            str(combine_script),
            "--cohort",
            args.cohort,
            "--age-band",
            args.age_band,
            "--workers",
            str(args.workers),
        ]
        if bin_name:
            cmd.extend(["--bin", bin_name])
        if args.upload_to_dashboard:
            cmd.append("--upload-to-dashboard")
        if args.upload_to_gold:
            cmd.append("--upload-to-gold")
        logger.info("Running combine step: %s", " ".join(cmd))
        result = subprocess.run(cmd, cwd=PROJECT_ROOT)
        if result.returncode != 0:
            raise RuntimeError(f"combine_shap_ffa_results.py failed with return code {result.returncode}")

    logger.info("Step 8 FFA + combined SHAP/FFA workflow complete.")


if __name__ == "__main__":
    main()
