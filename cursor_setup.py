#!/usr/bin/env python3
"""Project-local notebook output sync utility.

The repo used to depend on a shared ``project_utility_scripts/cursor_setup.py``
file. This implementation keeps the commands self-contained so EC2/Jupyter
post-save hooks can upload executed notebook copies without that external
checkout.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import boto3
except ImportError:  # pragma: no cover - environment issue, not logic
    boto3 = None


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_BUCKET = "mushin-solutions-project-metadata"
DEFAULT_PREFIX = "notebooks"
DEFAULT_PROJECT_SLUG = "cpic-time-to-event-analysis"

S3_BUCKET = os.environ.get("S3_BUCKET") or os.environ.get("CPIC_NOTEBOOK_METADATA_BUCKET", DEFAULT_BUCKET)
S3_PREFIX = (os.environ.get("S3_PREFIX") or os.environ.get("CPIC_NOTEBOOK_METADATA_PREFIX", DEFAULT_PREFIX)).strip("/")
PROJECT_SLUG = os.environ.get("PROJECT_SLUG") or os.environ.get("CPIC_NOTEBOOK_PROJECT_SLUG", DEFAULT_PROJECT_SLUG)

_creds = PROJECT_ROOT.parent / "credentials"
if _creds.exists() and not os.environ.get("AWS_SHARED_CREDENTIALS_FILE"):
    os.environ["AWS_SHARED_CREDENTIALS_FILE"] = str(_creds)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _client():
    if boto3 is None:
        raise SystemExit("boto3 is required for notebook output sync.")
    return boto3.client("s3")


def _base_prefix() -> str:
    return f"{S3_PREFIX}/{PROJECT_SLUG}".strip("/")


def _relative_notebook_path(path: Path) -> str:
    path = path.expanduser().resolve()
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.name


def _notebook_key(path: Path) -> str:
    return f"{_base_prefix()}/{_relative_notebook_path(path)}"


def _manifest_key(path: Path) -> str:
    return f"{_base_prefix()}/_manifests/{_relative_notebook_path(path)}.json"


def _iter_objects(s3, bucket: str, prefix: str):
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix.rstrip("/") + "/"):
        yield from page.get("Contents", [])


def command_status(args: argparse.Namespace) -> int:
    s3 = _client()
    prefix = _base_prefix()
    objects = list(_iter_objects(s3, S3_BUCKET, prefix))
    notebooks = [obj for obj in objects if obj["Key"].endswith(".ipynb")]
    manifests = [obj for obj in objects if "/_manifests/" in obj["Key"] and obj["Key"].endswith(".json")]

    print("Notebook output sync status")
    print("=" * 70)
    print(f"Metadata prefix: s3://{S3_BUCKET}/{prefix}/")
    print(f"Objects: {len(objects)}")
    print(f"Notebook copies: {len(notebooks)}")
    print(f"Manifests: {len(manifests)}")
    if objects:
        print("\nLatest objects:")
        for obj in sorted(objects, key=lambda item: item.get("LastModified"), reverse=True)[: args.max_rows]:
            last_modified = obj.get("LastModified")
            ts = last_modified.strftime("%Y-%m-%d %H:%M:%S UTC") if last_modified else "-"
            print(f"  {ts} {obj.get('Size', 0):8d} s3://{S3_BUCKET}/{obj['Key']}")
    return 0


def command_push_outputs(args: argparse.Namespace) -> int:
    s3 = _client()
    notebook = Path(args.notebook)
    if not notebook.exists():
        raise SystemExit(f"Notebook not found: {notebook}")
    if notebook.suffix.lower() != ".ipynb":
        raise SystemExit(f"Expected .ipynb file: {notebook}")

    notebook_key = _notebook_key(notebook)
    manifest_key = _manifest_key(notebook)
    notebook_abs = notebook.expanduser().resolve()
    body = notebook_abs.read_bytes()
    manifest = {
        "project_slug": PROJECT_SLUG,
        "notebook": _relative_notebook_path(notebook_abs),
        "source_path": str(notebook_abs),
        "s3_notebook": f"s3://{S3_BUCKET}/{notebook_key}",
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "size_bytes": len(body),
    }

    if args.dry_run:
        print(f"Would upload notebook: s3://{S3_BUCKET}/{notebook_key}")
        print(f"Would upload manifest: s3://{S3_BUCKET}/{manifest_key}")
        return 0

    s3.put_object(
        Bucket=S3_BUCKET,
        Key=notebook_key,
        Body=body,
        ContentType="application/x-ipynb+json",
    )
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=manifest_key,
        Body=json.dumps(manifest, indent=2).encode("utf-8"),
        ContentType="application/json",
    )
    print(f"Uploaded notebook outputs: s3://{S3_BUCKET}/{notebook_key}")
    print(f"Uploaded manifest: s3://{S3_BUCKET}/{manifest_key}")
    return 0


def command_fetch_outputs(args: argparse.Namespace) -> int:
    s3 = _client()
    notebook = Path(args.notebook)
    key = _notebook_key(notebook)
    destination = Path(args.output) if args.output else notebook
    if destination.exists() and not args.force:
        raise SystemExit(f"Refusing to overwrite existing file without --force: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    response = s3.get_object(Bucket=S3_BUCKET, Key=key)
    destination.write_bytes(response["Body"].read())
    print(f"Fetched notebook outputs: s3://{S3_BUCKET}/{key} -> {destination}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="List notebook output sync objects in S3.")
    p_status.add_argument("--max-rows", type=int, default=20)
    p_status.set_defaults(func=command_status)

    p_push = sub.add_parser("push-outputs", help="Upload an executed notebook copy and manifest to S3.")
    p_push.add_argument("notebook")
    p_push.add_argument("--dry-run", action="store_true")
    p_push.set_defaults(func=command_push_outputs)

    p_fetch = sub.add_parser("fetch-outputs", help="Download a synced notebook copy from S3.")
    p_fetch.add_argument("notebook")
    p_fetch.add_argument("--output", default=None, help="Destination path. Defaults to the notebook path.")
    p_fetch.add_argument("--force", action="store_true", help="Allow overwriting the destination.")
    p_fetch.set_defaults(func=command_fetch_outputs)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
