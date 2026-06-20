# AWS Operations

Project-specific AWS operations for `cpic_time_to_event_analysis`.

## Folders

- `athena/` - Athena table setup and quick QA queries for the project-scoped cohort parquet outputs.
- `iam/` - IAM onboarding runbooks, scoped policies, provisioning scripts, and account status notes.

## Safety

- Do not commit credentials, temporary passwords, AWS CLI profiles, or Athena result files.
- IAM provisioning scripts are dry-run by default and only make AWS changes when `--execute` is passed.
- Athena QA scripts write query results to the configured Athena results bucket; keep result artifacts out of git.
