---
description: Notebook output access and indexing rules for cpic_time_to_event_analysis
alwaysApply: true
---

# Notebook Output Access

## Project Notebook Metadata

- Project slug: `cpic-time-to-event-analysis`
- Default notebook metadata bucket: `mushin-solutions-project-metadata`
- Default notebook metadata prefix: `notebooks`
- Full notebook metadata root: `s3://mushin-solutions-project-metadata/notebooks/cpic-time-to-event-analysis/`
- Use `python cursor_setup.py push-outputs <notebook>` and `python cursor_setup.py fetch-outputs <notebook>` without repeating bucket or slug flags unless intentionally overriding these defaults.

This repository contains large workflow notebooks. Do not rely on raw notebook JSON as primary context.

- Prefer paired Python workflow scripts, step modules, helper modules, and project docs when available.
- When asked about notebook results, look for a sidecar `*.outputs.json` pointer next to the notebook.
- Fetch synced outputs with `python cursor_setup.py fetch-outputs <notebook_path>`.
- Use `python cursor_setup.py status` to inventory notebooks and pointer files.
- Do not clear or strip outputs unless the user explicitly asks or a commit workflow requires it.
- Keep `.ipynb` files manually referenced; avoid auto-loading large notebooks into context.
- Do not assume live notebook stdout is synced to the notebook metadata bucket during a running cell.
- For long-running notebook cells that call scripts, put durable progress/log uploads in the invoked script or phase code, not only in notebook output.
- Use `cursor_setup.py push-outputs <notebook>` for completed notebook output snapshots; use pipeline S3 log/checkpoint helpers for mid-run telemetry.

## Notebook Scanning

- Do not run broad whole-repository or whole-notebook scans over `.ipynb` files.
- Inspect one notebook section, header, or small cell range at a time.
- If the first attempt lacks context or an edit fails, fall back to the immediately previous section before expanding the search further.
- Prefer `ReadFile` with narrow offsets/limits or `EditNotebook` for known cells.
- If cell indexes are needed, get them from a small targeted query for one notebook only.
- Avoid parsing large notebooks through shell one-liners unless the query is narrowly scoped and expected to return quickly.
