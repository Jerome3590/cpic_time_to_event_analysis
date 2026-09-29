---
description: EC2 workflow, Spot AZ failover, and local/remote compute guidance for cpic_time_to_event_analysis
alwaysApply: false
---

# EC2 Remote Workflow

- Local Cursor terminals use AWS profile `mushin` from `.vscode/settings.json`; EC2 should normally use its IAM instance profile.
- Long pipeline and notebook runs should execute on EC2 or the configured compute environment, not in the local editor.
- Use project-scoped S3 paths under `s3://pgxdatalake/gold/cpic_time_to_event/`.
- Use project-specific NVMe paths such as `/mnt/nvme/cpic_time_to_event/...` for generated project artifacts.
- Never delete shared NVMe inputs like `/mnt/nvme/gold/medical` or `/mnt/nvme/gold/pharmacy`.
- Use S3 checkpoints and existing project path helpers instead of hard-coded local paths.
- Before enabling the Jupyter post-save hook, verify `python cursor_setup.py status` works in the EC2 checkout.
- For long-running EC2 pipeline phases, add best-effort incremental S3 log checkpoint calls around expensive queries, debug diagnostics, and materialization steps.
- Do not rely on final success/error log uploads alone for multi-minute or multi-hour EC2 phases; upload key diagnostics before the next long operation starts.
- When notebooks invoke EC2 scripts, keep telemetry in the script/phase context with `log_buffer` plus `save_logs_checkpoint` or the established project logging helper.

## Spot capacity / AZ failover

- Default compute is **Spot**. Keep **at least two Spot analysis instances
  in different AZs**. If an AZ is lost or a box is retired, stand up a
  replacement Spot box in another AZ before relying on on-demand.
- On `InsufficientInstanceCapacity` or a Spot capacity fail for the
  primary: try the other-AZ Spot box(es) next. On-demand is last resort
  only. Path: primary Spot --> other-AZ Spot --> on-demand last resort.
- Document this project's instance IDs and failover order in this rule
  when they exist. Do not treat surgical-ed-vr instance IDs as this
  project's primary boxes.
- Never terminate Mushin `i-0c968462d413a1028`.
- ASCII arrows only: `-->`.
