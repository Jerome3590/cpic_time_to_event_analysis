---
description: Enforce idempotent project workflow and notebook edits
alwaysApply: true
---

# Idempotent Workflow

- Workflow notebooks and pipeline scripts must be safe to rerun after a kernel restart, partial run, or S3/local sync.
- Do not require hidden state from earlier cells unless the same cell initializes a safe default with `globals().get(...)` or an equivalent invariant.
- Prefer explicit checkpoints, artifact existence checks, and `--force-*` flags over unconditional recompute.
- A step may skip when complete, rebuild when forced, and fail clearly when required inputs are missing.
- When adding notebook cells, validate that running the cell independently after setup does not raise `NameError` for optional state from earlier phases.
