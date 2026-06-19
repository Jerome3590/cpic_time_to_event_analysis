#!/usr/bin/env python3
import argparse
import os
import secrets
import string
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


DEFAULT_USERNAME = "srhashimi2"
DEFAULT_EMAIL = "srhashimi2@vcu.edu"
DEFAULT_POLICY_NAME = "CpicTimeToEventArtifactAccess"
DEFAULT_POLICY_FILE = Path(__file__).resolve().parents[1] / "config" / "cpic-time-to-event-artifact-access-policy-v2.json"
DEFAULT_REGION = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"


def generate_temp_password(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in "!@#$%^&*()-_=+" for c in password)
        ):
            return password


def get_console_url(account_id: str) -> str:
    return f"https://{account_id}.signin.aws.amazon.com/console"


def ensure_user(iam, username: str, execute: bool) -> None:
    if not execute:
        print(f"DRY RUN: would create IAM user if missing: {username}")
        return

    try:
        iam.get_user(UserName=username)
        print(f"IAM user exists: {username}")
        return
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "NoSuchEntity":
            raise

    iam.create_user(UserName=username)
    print(f"Created IAM user: {username}")


def ensure_managed_policy(iam, account_id: str, policy_name: str, policy_file: Path, execute: bool) -> str:
    policy_arn = f"arn:aws:iam::{account_id}:policy/{policy_name}"
    if not execute:
        print(f"DRY RUN: would create or reuse managed policy {policy_arn} from {policy_file}")
        return policy_arn

    try:
        iam.get_policy(PolicyArn=policy_arn)
        print(f"Managed policy exists: {policy_arn}")
        return policy_arn
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "NoSuchEntity":
            raise

    policy_document = policy_file.read_text(encoding="utf-8")
    iam.create_policy(
        PolicyName=policy_name,
        PolicyDocument=policy_document,
        Description="S3 plus Athena/Glue access to CPIC time-to-event artifacts only",
    )
    print(f"Created managed policy: {policy_arn}")
    return policy_arn


def ensure_policy_attached(iam, username: str, policy_arn: str, execute: bool) -> None:
    attached = iam.list_attached_user_policies(UserName=username).get("AttachedPolicies", []) if execute else []
    if any(policy.get("PolicyArn") == policy_arn for policy in attached):
        print(f"Policy already attached: {policy_arn}")
        return

    if not execute:
        print(f"DRY RUN: would attach policy {policy_arn} to {username}")
        return

    iam.attach_user_policy(UserName=username, PolicyArn=policy_arn)
    print(f"Attached policy {policy_arn} to {username}")


def set_login_profile(iam, username: str, password: str, execute: bool) -> None:
    if not execute:
        print(f"DRY RUN: would create or update login profile for {username} with password reset required")
        return

    try:
        iam.create_login_profile(
            UserName=username,
            Password=password,
            PasswordResetRequired=True,
        )
        print(f"Created login profile for {username}")
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "EntityAlreadyExists":
            raise
        iam.update_login_profile(
            UserName=username,
            Password=password,
            PasswordResetRequired=True,
        )
        print(f"Updated login profile for {username}")


def send_temp_password_email(
    ses,
    sender: str,
    recipient: str,
    username: str,
    password: str,
    account_id: str,
    execute: bool,
) -> None:
    subject = "AWS IAM temporary password"
    console_url = get_console_url(account_id)
    body = f"""Hello,

An AWS IAM user has been created for you.

Account ID: {account_id}
Console URL: {console_url}
Username: {username}
Temporary password: {password}

You will be required to reset this password at first sign-in.

If you were not expecting this access, contact the project administrator.
"""

    if not execute:
        print(f"DRY RUN: would send temporary password email to {recipient} from {sender}")
        return

    ses.send_email(
        Source=sender,
        Destination={"ToAddresses": [recipient]},
        Message={
            "Subject": {"Data": subject},
            "Body": {"Text": {"Data": body}},
        },
    )
    print(f"Sent temporary password email to {recipient}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Provision an IAM user and email a temporary password.")
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--policy-arn", default=None, help="Optional existing policy ARN to attach instead of creating the scoped CPIC policy.")
    parser.add_argument("--policy-name", default=DEFAULT_POLICY_NAME)
    parser.add_argument("--policy-file", default=str(DEFAULT_POLICY_FILE))
    parser.add_argument("--sender", default=os.getenv("AWS_SES_SENDER"))
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--execute", action="store_true", help="Create/update IAM resources and send email.")
    parser.add_argument("--dry-run", action="store_true", help="Show intended actions without making changes.")
    parser.add_argument("--skip-email", action="store_true", help="Create/update the IAM user without sending email.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    execute = bool(args.execute and not args.dry_run)

    if not execute:
        print("Running in dry-run mode. Pass --execute to make AWS changes.")

    if execute and not args.skip_email and not args.sender:
        print("ERROR: --sender or AWS_SES_SENDER is required to send email.", file=sys.stderr)
        return 2

    password = generate_temp_password()

    if execute:
        session = boto3.Session(region_name=args.region)
        iam = session.client("iam")
        sts = session.client("sts")
        ses = session.client("ses", region_name=args.region)
        account_id = sts.get_caller_identity()["Account"]
    else:
        iam = None
        ses = None
        account_id = "<aws-account-id>"

    policy_file = Path(args.policy_file).resolve()
    if args.policy_arn:
        policy_arn = args.policy_arn
    else:
        policy_arn = ensure_managed_policy(iam, account_id, args.policy_name, policy_file, execute)

    ensure_user(iam, args.username, execute)
    if execute:
        ensure_policy_attached(iam, args.username, policy_arn, execute)
        set_login_profile(iam, args.username, password, execute)
    else:
        ensure_policy_attached(iam, args.username, policy_arn, execute)
        set_login_profile(iam, args.username, "<generated-temp-password>", execute)

    if args.skip_email:
        print("Email delivery skipped by --skip-email")
    else:
        email_password = password if execute else "<generated-temp-password>"
        send_temp_password_email(
            ses=ses,
            sender=args.sender or "<verified-ses-sender>",
            recipient=args.email,
            username=args.username,
            password=email_password,
            account_id=account_id,
            execute=execute,
        )

    print("Done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
