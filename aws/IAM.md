# IAM User Onboarding

Template source: `C:\Projects\surgical-ed-vr\aws_account_migration`.

## Requested user

| Field | Value |
|---|---|
| IAM username | `srhashimi2` |
| Email | `srhashimi2@vcu.edu` |
| Password delivery | Email temporary password |
| Password reset | Required on first sign-in |

## Recommended provisioning path

Run the helper from the repository root:

```bash
python aws/scripts/provision_iam_user.py --dry-run
```

To create the user and send the temporary password email:

```bash
python aws/scripts/provision_iam_user.py \
  --execute \
  --username srhashimi2 \
  --email srhashimi2@vcu.edu \
  --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess
```

## Required AWS permissions

The AWS identity running the script needs permissions for:

- `iam:CreateUser`
- `iam:GetUser`
- `iam:CreateLoginProfile`
- `iam:UpdateLoginProfile`
- `iam:AttachUserPolicy`
- `iam:ListAttachedUserPolicies`
- `sts:GetCallerIdentity`
- `ses:SendEmail` if email delivery is enabled

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
