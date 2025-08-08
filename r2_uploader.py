"""Utilities for uploading and managing videos on Cloudflare R2 using the
S3 compatible API.

The functions in this module are intentionally small and rely on
environment variables for configuration:

* ``R2_BUCKET`` – bucket name that stores the objects
* ``R2_ACCOUNT_ID`` – Cloudflare account identifier
* ``R2_ACCESS_KEY_ID`` / ``R2_SECRET_ACCESS_KEY`` – API token
* ``R2_ENDPOINT`` – optional custom endpoint. When unset the default
  AWS S3 endpoint is used which is convenient for tests with ``moto``.
* ``R2_PUBLIC_BASE`` – base URL used to construct public object URLs

The upload helpers automatically switch between single part uploads and
multipart uploads for large files (≥5 MiB) to comply with R2's limits.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import BinaryIO, Dict, List

import boto3
from botocore.exceptions import ClientError

# ---------------------------------------------------------------------------
# client helpers


def _get_client() -> boto3.client:
    """Return an S3 compatible client configured for Cloudflare R2.

    If ``R2_ENDPOINT`` is not provided the default AWS endpoint is used which
    allows the functions to be tested with libraries such as ``moto``.
    """

    kwargs = {
        "aws_access_key_id": os.environ.get("R2_ACCESS_KEY_ID"),
        "aws_secret_access_key": os.environ.get("R2_SECRET_ACCESS_KEY"),
        "region_name": os.environ.get("R2_REGION", "auto"),
    }

    endpoint = os.environ.get("R2_ENDPOINT")
    if endpoint:
        kwargs["endpoint_url"] = endpoint

    session = boto3.session.Session()
    return session.client("s3", **kwargs)


def _public_base(bucket: str) -> str:
    account_id = os.environ.get("R2_ACCOUNT_ID", "")
    return os.environ.get(
        "R2_PUBLIC_BASE",
        f"https://{account_id}.r2.cloudflarestorage.com/{bucket}",
    )


# ---------------------------------------------------------------------------
# upload / metadata helpers


def upload_file(fileobj: BinaryIO, key: str, size: int) -> Dict[str, str]:
    """Upload ``fileobj`` to the configured bucket.

    Chooses a simple ``PutObject`` for small files and a multipart upload for
    larger ones. Returns a dictionary containing basic metadata about the
    created object.
    """

    bucket = os.environ["R2_BUCKET"]
    s3 = _get_client()

    try:
        if size < 5 * 1024 * 1024:
            # single part
            resp = s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=fileobj,
                ContentType="video/mp4",
            )
            etag = resp.get("ETag", "").strip('"')
        else:
            # multipart
            mpu = s3.create_multipart_upload(
                Bucket=bucket, Key=key, ContentType="video/mp4"
            )
            upload_id = mpu["UploadId"]
            parts: List[Dict[str, str]] = []
            part_number = 1
            while True:
                chunk = fileobj.read(5 * 1024 * 1024)
                if not chunk:
                    break
                part = s3.upload_part(
                    Bucket=bucket,
                    Key=key,
                    PartNumber=part_number,
                    UploadId=upload_id,
                    Body=chunk,
                )
                parts.append({"PartNumber": part_number, "ETag": part["ETag"]})
                part_number += 1

            s3.complete_multipart_upload(
                Bucket=bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )
            etag = s3.head_object(Bucket=bucket, Key=key)["ETag"].strip('"')
    except Exception:
        # Attempt to abort multipart uploads on failure
        if size >= 5 * 1024 * 1024 and "upload_id" in locals():
            s3.abort_multipart_upload(
                Bucket=bucket, Key=key, UploadId=upload_id
            )
        raise

    created_at = datetime.now(timezone.utc)
    url = f"{_public_base(bucket)}/{key}"

    return {
        "url": url,
        "key": key,
        "size": size,
        "etag": etag,
        "created_at": created_at.isoformat(),
        "expires_at": None,
    }


def get_metadata(key: str) -> Dict[str, str]:
    bucket = os.environ["R2_BUCKET"]
    s3 = _get_client()
    meta = s3.head_object(Bucket=bucket, Key=key)
    return meta


def delete_object(key: str) -> None:
    bucket = os.environ["R2_BUCKET"]
    s3 = _get_client()
    s3.delete_object(Bucket=bucket, Key=key)


def delete_oldest_if_over_quota(max_total_bytes: int) -> int:
    """Delete the oldest objects until total size is under ``max_total_bytes``.

    Returns the number of deleted objects.
    """

    bucket = os.environ["R2_BUCKET"]
    s3 = _get_client()

    objects: List[Dict[str, str]] = []
    continuation = None
    total = 0
    while True:
        if continuation:
            resp = s3.list_objects_v2(
                Bucket=bucket, ContinuationToken=continuation
            )
        else:
            resp = s3.list_objects_v2(Bucket=bucket)

        for obj in resp.get("Contents", []):
            objects.append(obj)
            total += obj["Size"]

        if not resp.get("IsTruncated"):
            break
        continuation = resp.get("NextContinuationToken")

    if total <= max_total_bytes:
        return 0

    objects.sort(key=lambda o: o["LastModified"])
    deleted = 0
    for obj in objects:
        if total <= max_total_bytes:
            break
        s3.delete_object(Bucket=bucket, Key=obj["Key"])
        total -= obj["Size"]
        deleted += 1

    return deleted


__all__ = [
    "upload_file",
    "get_metadata",
    "delete_object",
    "delete_oldest_if_over_quota",
]

