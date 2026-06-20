# Archive

This folder contains repository content that was removed from the active workflow
because it was duplicative, stale, or explicitly marked inactive.

## Active production notebooks

The production notebook workflow is intentionally root-only:

1. `1_cohort_workflow.ipynb`
2. `2_feature_importance.ipynb`
3. `3_model_train_shap_ffa.ipynb`

Use `0_config_and_pipeline.ipynb` only for setup, cleanup/reset, environment
checks, and run instructions.

## Stale docs

- `stale_docs/4_model_data_README_stub.md`: superseded by `4_model_data/README_model_data.md`.
- `stale_docs/3b_feature_importance_eda_README_stub.md`: superseded by `3b_feature_importance_eda/README_feature_importance_eda.md`.
- `stale_docs/3b_feature_importance_eda_1_bupaR_README_bupar_temp.md`: temporary duplicate of `3b_feature_importance_eda/1_bupaR/README_bupaR.md`.

## Inactive notebooks

- `inactive_notebooks/2_create_cohort/cohort_workflow.ipynb`
- `inactive_notebooks/3b_feature_importance_eda/step3b_interactive_analysis_cohort1.ipynb`
- `inactive_notebooks/3b_feature_importance_eda/step3b_interactive_analysis_cohort2.ipynb`
- `inactive_notebooks/3b_feature_importance_eda/step3b_interactive_analysis_cohort3.ipynb`
- `inactive_notebooks/3b_feature_importance_eda/step3b_interactive_analysis_cohort4.ipynb`
- `inactive_notebooks/step3b_interactive_analysis_cohort5.ipynb`
- `inactive_notebooks/step3b_interactive_analysis_cohort6.ipynb`
- `inactive_notebooks/step3b_interactive_analysis_cohort7.ipynb`
- `inactive_notebooks/5_pgx_analysis/pgx_cohort_runner.ipynb`
- `inactive_notebooks/6_final_model/build_train_test_datasets.ipynb`
- `inactive_notebooks/6_final_model/final_model_cohort_runner.ipynb`
- `inactive_notebooks/7_shap_analysis/shap_cohort_runner.ipynb`
- `inactive_notebooks/root/2_feature_importance.ipynb`
- `inactive_notebooks/root/4_analysis_results_visuals.ipynb`

These notebooks are retained for historical reference only. They either
referenced older `non_opioid_ed` / extra-age-band workflows, duplicated steps
now consolidated into the three production notebooks, or were superseded by the
current `falls`/`ed` active cohort matrix.
