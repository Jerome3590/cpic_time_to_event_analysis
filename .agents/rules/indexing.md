---
description: Indexing and context budget rules for cpic_time_to_event_analysis
alwaysApply: true
---

# Indexing and Context Budget

- Open `cpic_time_to_event_analysis` directly rather than the `C:\Projects` parent folder for focused work.
- Keep generated data, logs, model artifacts, notebook checkpoints, and build outputs out of context.
- Prefer docs, Python modules, R helpers, step scripts, and helper modules over large notebook JSON.
- Start a fresh chat when switching between cohort creation, feature importance, final model, SHAP, FFA, and dashboard work.
- Use `.cursorignore` and `.vscode/settings.json` to keep `.ipynb` files out of automatic context while leaving notebooks editable.
