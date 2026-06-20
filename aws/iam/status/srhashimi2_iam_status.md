# IAM Account Status - srhashimi2@vcu.edu

## User

- **IAM username:** `srhashimi2`
- **Email:** `srhashimi2@vcu.edu`
- **Requested access:** S3 artifact visibility/read access plus Athena/Glue catalog/query access for CPIC time-to-event artifacts
- **Excluded access:** EC2, Lambda, and unrelated AWS services

## Current Status

- **AWS account:** `535362115856`
- **IAM user created:** Yes - `arn:aws:iam::535362115856:user/srhashimi2`
- **Scoped IAM policy created:** Yes - `arn:aws:iam::535362115856:policy/CpicTimeToEventArtifactAccess`
- **Policy attached to user:** Yes
- **Console login profile created:** Yes
- **Password reset required:** Yes
- **Temporary password generated live:** Yes - held in process memory only, not written to disk
- **Email sent:** Yes - sent to `srhashimi2@vcu.edu`
- **Provisioned at:** 2026-06-19T22:37Z

## Evidence

Live provisioning command completed successfully:

```bash
python aws/iam/scripts/provision_iam_user.py \
  --execute \
  --username srhashimi2 \
  --email srhashimi2@vcu.edu \
  --sender verified-sender@example.com \
  --region us-east-1
```

Verification commands succeeded:

- `aws iam get-user --user-name srhashimi2`
- `aws iam list-attached-user-policies --user-name srhashimi2`
- `aws iam get-login-profile --user-name srhashimi2`
- `aws iam get-policy --policy-arn arn:aws:iam::535362115856:policy/CpicTimeToEventArtifactAccess`

## Next Live Action Required

Ask `srhashimi2@vcu.edu` to confirm receipt and complete first-login password reset.

## Post-Execution Checklist

- [x] Confirm IAM user exists: `aws iam get-user --user-name srhashimi2`
- [x] Confirm login profile exists: `aws iam get-login-profile --user-name srhashimi2`
- [x] Confirm `CpicTimeToEventArtifactAccess` policy exists
- [x] Confirm policy attached to `srhashimi2`
- [x] Confirm SES send succeeded
- [ ] Confirm recipient received temporary password
- [ ] Confirm first login/password reset completed
