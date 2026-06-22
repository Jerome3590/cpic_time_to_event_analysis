# IAM Lessons Learned

## S3 Console Access Needs Two Kinds of List Permission

When users report that they can sign in but cannot browse S3 buckets or folders in the AWS console, check both bucket discovery and bucket navigation permissions.

Required actions:

- `s3:ListAllMyBuckets` on `*` lets the user see the bucket list in the S3 console.
- `s3:GetBucketLocation` on the relevant buckets lets the console resolve bucket regions.
- `s3:ListBucket` on each relevant bucket lets the user browse prefixes inside that bucket.

Common pitfall:

Scoped `s3:ListBucket` conditions often include only project prefixes such as `gold/cpic_time_to_event/*`. That works for direct CLI/API calls to the exact prefix, but the S3 console often first lists the bucket root with `s3:prefix=""`. If the empty root prefix is missing, users can see the bucket but get access denied before they can navigate to the allowed folder.

Recommended scoped pattern:

```json
{
  "Sid": "ListProjectFolders",
  "Effect": "Allow",
  "Action": "s3:ListBucket",
  "Resource": "arn:aws:s3:::pgxdatalake",
  "Condition": {
    "StringLike": {
      "s3:prefix": [
        "",
        "gold",
        "gold/",
        "gold/cpic_time_to_event",
        "gold/cpic_time_to_event/",
        "gold/cpic_time_to_event/*"
      ]
    }
  }
}
```

## Verification Commands

Use IAM simulation before and after policy changes:

```bash
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::<account-id>:user/<username> \
  --action-names s3:ListAllMyBuckets \
  --resource-arns "*"

aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::<account-id>:user/<username> \
  --action-names s3:ListBucket \
  --resource-arns arn:aws:s3:::pgxdatalake \
  --context-entries ContextKeyName=s3:prefix,ContextKeyType=string,ContextKeyValues=

aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::<account-id>:user/<username> \
  --action-names s3:ListBucket \
  --resource-arns arn:aws:s3:::pgxdatalake \
  --context-entries ContextKeyName=s3:prefix,ContextKeyType=string,ContextKeyValues=gold/cpic_time_to_event
```

Expected decisions:

- `s3:ListAllMyBuckets`: `allowed`
- `s3:ListBucket` with `s3:prefix=""`: `allowed` for buckets the user may navigate in the console
- `s3:ListBucket` with the project prefix: `allowed`

## Syeda Update

For `srhashimi2`, the managed policy `CpicTimeToEventArtifactAccess` was updated to default version `v2` on 2026-06-22. The update added root-prefix list access (`s3:prefix=""`) for:

- `pgxdatalake`
- `mushin-solutions-project-metadata`
- `pgx-repository`

Simulation confirmed `s3:ListAllMyBuckets` and `s3:ListBucket` are allowed for the relevant roots and project prefixes.
