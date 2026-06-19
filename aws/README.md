# AWS Account Operations

Project-specific AWS account operations for `cpic_time_to_event_analysis`.

This folder follows the structure used in `C:\Projects\surgical-ed-vr\aws_account_migration` but is scoped to this repository.

## IAM onboarding

Default requested user:

- **IAM username:** `srhashimi2`
- **Email:** `srhashimi2@vcu.edu`

Use the IAM runbook in `IAM.md` and the provisioning script in `scripts/provision_iam_user.py`.

## Safety

The provisioning script is dry-run by default. It only creates IAM resources or sends email when `--execute` is passed.

Temporary passwords are generated at runtime and are never written to disk.
