# IAM User Onboarding

Template source: `C:\Projects\surgical-ed-vr\aws_account_migration`.

## Requested user

| Field | Value |
|---|---|
| IAM username | `srhashimi2` |
| Email | `srhashimi2@vcu.edu` |
| Password delivery | Email temporary password |
| Password reset | Required on first sign-in |
| Access scope | S3 artifacts plus Athena/Glue catalog/query access for CPIC time-to-event only |
| Explicit exclusions | No EC2, Lambda, or unrelated AWS service permissions |

## Recommended provisioning path

Run the helper from the repository root:

```bash
python aws/scripts/provision_iam_user.py --dry-run
```

To create the scoped policy, create/update the user, attach the policy, and send the temporary password email:

```bash
python aws/scripts/provision_iam_user.py \
  --execute \
  --username srhashimi2 \
  --email srhashimi2@vcu.edu \
  --sender verified-sender@example.com
```

The default managed policy is `CpicTimeToEventArtifactAccess`, created from `aws/config/cpic-time-to-event-artifact-access-policy-v2.json` if missing.

## Required AWS permissions

The AWS identity running the script needs permissions for:

- `iam:CreateUser`
- `iam:GetUser`
- `iam:CreateLoginProfile`
- `iam:UpdateLoginProfile`
- `iam:CreatePolicy`
- `iam:GetPolicy`
- `iam:AttachUserPolicy`
- `iam:ListAttachedUserPolicies`
- `sts:GetCallerIdentity`
- `ses:SendEmail` if email delivery is enabled

## Access granted

The default policy grants:

- S3 bucket-list visibility so the user can see available buckets in the console
- S3 folder-list/read access for associated CPIC folders in:
  - `s3://pgxdatalake/gold/cpic_time_to_event/`
  - `s3://mushin-solutions-project-metadata/notebooks/cpic-time-to-event-analysis/`
  - `s3://mushin-solutions-project-metadata/notebooks/create_cohort/`
  - legacy CPIC checkpoint/log prefixes in `s3://pgx-repository/`
- Athena query execution and query-result retrieval
- Athena query-result bucket read/write access for standard Athena result buckets
- Glue Data Catalog read access required by Athena

The policy does not grant EC2, Lambda, CloudFormation, IAM administration for the user, or broad account read-only access outside the listed S3/Athena/Glue scope.

## SES requirements

Email delivery uses Amazon SES. The sender address must be verified in SES unless the account is out of sandbox. If the SES account is still sandboxed, the recipient `srhashimi2@vcu.edu` must also be verified before sending.

Set the sender via environment variable or CLI:

```bash
export AWS_SES_SENDER="verified-sender@example.com"
```

or:

```bash
python aws/scripts/provision_iam_user.py --execute --sender verified-sender@example.com
```

## Notes

- Temporary passwords are printed only in dry-run mode as a placeholder and are never written to disk.
- In execute mode, the generated password is held in memory and emailed once.
- The user is forced to reset the password on first sign-in.
- If an IAM login profile already exists, the script rotates the temporary password and keeps password reset required.
