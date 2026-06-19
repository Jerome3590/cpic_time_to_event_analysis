# AWS Account Operations

Project-specific AWS account operations for `cpic_time_to_event_analysis`.

This folder follows the structure used in `C:\Projects\surgical-ed-vr\aws_account_migration` but is scoped to this repository.

## IAM onboarding

Default requested user:

- **IAM username:** `srhashimi2`
- **Email:** `srhashimi2@vcu.edu`
- **Access:** S3 bucket/folder visibility plus object access for CPIC time-to-event artifacts; Athena/Glue catalog/query access
- **Excluded:** EC2, Lambda, and unrelated AWS services

Use the IAM runbook in `IAM.md`, the scoped policy in `config/cpic-time-to-event-artifact-access-policy-v2.json`, and the provisioning script in `scripts/provision_iam_user.py`.

## Safety

The provisioning script is dry-run by default. It only creates IAM resources or sends email when `--execute` is passed.

Temporary passwords are generated at runtime and are never written to disk.
