# Feature Screening Pipeline for High-Cardinality Cohorts

This README describes a reusable feature-screening workflow for high-cardinality tabular data, designed to be applied across different target cohorts (e.g., different outcomes or subpopulations) with minimal changes.

The core design goals are:

- Avoid target-encoding leakage in XGBoost-like models by using **one-hot encoding** only. [web:34][web:41]  
- Leverage **CatBoost’s ordered categorical handling** as a leakage-aware complementary model. [web:31][web:33][web:34]  
- Use **Monte Carlo cross-validation** plus **cross-model feature importance aggregation** to obtain a robust, ranked global feature list. [web:46][web:80][web:83]

You can reuse this workflow for any target cohort by swapping in a new label definition and cohort filter, while keeping the overall procedure the same.

---

## Current Repository Implementation

This repo implements the screening workflow as a project-scoped, target-specific pipeline. Cohorts, feature importances, model data, and downstream artifacts are namespaced by `PROJECT_SLUG` so the same cohort labels can be reused safely for different target definitions.

Current defaults:

- Project slug: `cpic_time_to_event` via `CPIC_PROJECT_SLUG`.
- Cohort S3 root: `s3://pgxdatalake/gold/{PROJECT_SLUG}/cohorts/`.
- Step 3a feature-importance S3 root: `s3://pgxdatalake/gold/{PROJECT_SLUG}/feature_importance/{cohort}/{age_band}/`.
- Step 3a local/NVMe root: `get_feature_importance_root()`, defaulting on EC2 to `/mnt/nvme/{PROJECT_SLUG}/3a_feature_importance/outputs/`.
- Step 3b refined feature-importance local/NVMe root: `get_refined_feature_importance_root()`, defaulting on EC2 to `/mnt/nvme/{PROJECT_SLUG}/3b_feature_importance_eda/outputs/`.
- Step 4 model-event root: `get_model_data_root()`, defaulting on EC2 to `/mnt/nvme/{PROJECT_SLUG}/4_model_data/`.
- Step 6, SHAP, FFA, PGx, DTW, FP-Growth, QA, and target-code outputs use `gold/{PROJECT_SLUG}/...` S3 prefixes.

Validated code path:

1. Step 2 writes project-scoped cohort parquet files through `get_cohort_parquet_path()`.
2. Step 3a reads project-scoped cohorts, runs MCCV, and writes aggregated/per-model FI under project-scoped local and S3 roots.
3. Step 3b filters/refines Step 3a FI into `cohort_feature_importance.csv` under the project-scoped Step 3b root and mirrors to project-scoped S3.
4. Step 4 uses Step 3b `cohort_feature_importance.csv` as the required feature list for model-event construction. There is no intended fallback to unrefined Step 3a FI for final model data.
5. Step 6, SHAP, FFA, PGx, DTW, BupaR, and dashboard helpers consume the same project-scoped Step 3b feature list or downstream project-scoped outputs.

Known cleanup items from the audit:

- `2_create_cohort/3_cohort_final_metrics.py` now reads the production `gold/{PROJECT_SLUG}/cohorts/` layout; `--target-slug` is deprecated and ignored.
- `PipelineState` now writes production checkpoints under `gold/{PROJECT_SLUG}/pipeline_checkpoints/` and can resume from legacy `pgx-pipeline-status/` state during the transition.
- Several notebooks and READMEs still contain stale unscoped examples such as `gold/cohorts`, `gold/feature_importance`, and `gold/final_model`; executable code has been updated more broadly than the documentation.
- `2_create_cohort/2_step2_data_quality_qa.py` defaults `PGX_TARGET_NAME` to `falls` when unset. For target experiments, prefer setting target env vars explicitly.

---

## 1. Cohort Definition and Data Window

1. **Define the target cohort**

   - Specify inclusion/exclusion criteria for the cohort (e.g., diagnosis, age, enrollment conditions).
   - Define the binary (or multi-class) outcome for this cohort.

2. **Define time windows**

   - **Training window**: e.g., 2016–2018.
   - **Hold-out evaluation window**: e.g., 2019 (used later for model evaluation, not for initial feature screening). [web:47][web:57]

3. **Extract features and labels**

   - Build a feature matrix \(X\) and label vector \(y\) for the training window.
   - Include high-cardinality categorical features (IDs, ZIP codes, providers, etc.).
   - Apply cohort filters so all subsequent steps are cohort-specific.

---

## 2. Encoding Strategy

1. **CatBoost**

   - Use CatBoost’s native categorical handling (ordered / expanding mean target statistics and ordered boosting). [web:31][web:33][web:34]  
   - This provides a leakage-aware model for high-cardinality features.

2. **XGBoost and XGBoost RF**

   - Use **one-hot encoding** for all categorical features.
   - No target encoding is applied; thus, the target-encoding leakage mechanism does not apply in this workflow. [web:34][web:41]

   > Note: One-hot encoding can increase dimensionality and sparsity, but compute and storage are handled via cloud infrastructure, so we trade resources for conceptual simplicity and reduced leakage risk.

---

## 3. Monte Carlo Cross-Validation (MCCV)

1. **Set up MCCV**

   - Choose the number of MCCV runs, e.g. **25**. [web:46][web:83]  
   - For each run \(r = 1,\dots,25\):
     - Randomly split the training window into train/validation sets (respect temporal or grouping constraints if needed).
     - Use the same splits for all models in that run.

2. **Purpose**

   - MCCV provides a distribution over feature importances, making rankings more robust to sampling variability and case-mix shifts. [web:46][web:80]

---

## 4. Models Per MCCV Run

For each MCCV run \(r\), fit the following models on the training fold:

1. **CatBoost (GBDT)**

   - Trained with ordered categorical encoding and ordered boosting. [web:31][web:33][web:34]

2. **XGBoost (GBDT)**

   - Standard gradient-boosted trees with **one-hot encoded** categorical features.

3. **XGBoost RF**

   - XGBoost configured in Random Forest mode:
     - Bagging + random feature subsampling, using the same one-hot encoding.

Each model is trained with its own hyperparameters (these can be fixed or tuned via Optuna in a separate stage).

---

## 5. Per-Model Feature Importance Estimation

For each model \(m \in \{\text{CatBoost}, \text{XGB}, \text{XGB RF}\}\) and MCCV run \(r\):

1. **Train model \(m\) on the run-\(r\) training fold.**

2. **Compute feature importance**

   - Use a consistent importance measure per model, such as:
     - Native tree-based importance (e.g., gain, split count). [web:84][web:92]  
     - **OR** mean absolute SHAP values if you prefer attribution-based importance. [web:29][web:87]

3. **Store importance vector**

   - Denote the importance of feature \(j\) in run \(r\) for model \(m\) as \(I^{(m,r)}_j\).

At the end of this step you have, for each model, 25 importance vectors—one per MCCV run.

---

## 6. Aggregation Across MCCV Runs (Per Model)

For each model \(m\):

1. **Average across runs**

   - Compute the **mean feature importance** over the 25 MCCV runs:
     \[
     \bar{I}^{(m)}_j = \frac{1}{25} \sum_{r=1}^{25} I^{(m,r)}_j
     \]
   - This stabilizes importance estimates against random train/validation splits. [web:80][web:83]

2. **Optional normalization**

   - Optionally normalize \(\bar{I}^{(m)}\) per model (e.g., divide by the sum or max) so different models’ scores are on comparable scales. [web:84]

Result: one mean importance vector per model:
- \(\bar{I}^{(\text{CatBoost})}\)  
- \(\bar{I}^{(\text{XGB})}\)  
- \(\bar{I}^{(\text{XGB RF})}\)

---

## 7. Union-Based Cross-Model Aggregation

1. **Feature union**

   - Consider the union of all features with non-negligible mean importance in at least one model:
     - A feature \(j\) is included if \(\bar{I}^{(\text{CatBoost})}_j > 0\) **or** \(\bar{I}^{(\text{XGB})}_j > 0\) **or** \(\bar{I}^{(\text{XGB RF})}_j > 0\). [web:85][web:86]

2. **Aggregate importance across models**

   - For each feature \(j\) in the union, define an **aggregate importance** score:
     - Simple example (unweighted sum):
       \[
       I^{\text{agg}}_j = \bar{I}^{(\text{CatBoost})}_j + \bar{I}^{(\text{XGB})}_j + \bar{I}^{(\text{XGB RF})}_j
       \]
     - Alternative schemes (e.g., weighted sum, rank aggregation) may be used if desired. [web:86][web:90]

This step yields a single scalar importance \(I^{\text{agg}}_j\) per feature, reflecting evidence from all three models. [web:86]

---

## 8. Positive Aggregate Importance Filter

1. **Filter low-importance features**

   - Remove features with:
     - \(I^{\text{agg}}_j \le 0\), or  
     - Below a very small threshold (to account for numerical noise after normalization).

2. **Rationale**

   - Features that have essentially zero aggregate importance across all models and runs are unlikely to be informative and can be safely removed. [web:84][web:92]

Remaining features form the **candidate signal set** for this cohort.

---

## 9. Ranked Global Feature List

1. **Sort by aggregate importance**

   - Sort remaining features by \(I^{\text{agg}}_j\) in **descending** order.

2. **Output**

   - A **ranked global feature list**:
     - \(f_{(1)}, f_{(2)}, \dots, f_{(K)}\)
     - Where \(f_{(1)}\) has the highest aggregate importance across CatBoost, XGBoost, and XGBoost RF for this cohort.

3. **Reuse across cohorts**

   - For a different target cohort:
     - Redefine the cohort and label (Section 1).
     - Rerun the same pipeline to obtain a **cohort-specific ranked global feature list**.

This ranked list can then be:

- Used directly as a feature pool for downstream modeling.  
- Truncated to the top-\(k\) features for efficiency.  
- Fed into more formal steps (e.g., formal feature attribution, stability selection, DTW, bupar, FPGrowth) as a high-quality starting point. [web:83][web:90]

---

## 10. Notes on Robustness to Target-Encoding Leakage

- No models in this screening pipeline use target encoding; all XGBoost-family models rely on one-hot encoding for categorical variables. [web:34][web:41]  
- Therefore, the **target-encoding leakage mechanism** (using the current row’s label in the encoding mean, causing “time-travel” leakage) does **not apply** here. [web:31][web:34][web:41]  
- CatBoost’s ordered target statistics provide an additional leakage-aware perspective on high-cardinality features, complementing the simpler one-hot-encoded XGBoost and XGBoost RF models. [web:31][web:33][web:34]

---

To reuse this README for a new cohort, you mainly need to change the cohort definition, outcome definition, and date ranges in Section 1; all later sections apply unchanged.
