import io
import os
import time

import boto3

# ``mock_aws`` was introduced in newer versions of ``moto``.  Fallback to
# ``mock_s3`` on older releases so the tests run everywhere.
try:  # pragma: no cover - import flexibility
    from moto import mock_aws
except ImportError:  # pragma: no cover
    from moto import mock_s3 as mock_aws

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
import r2_uploader


@mock_aws
def test_upload_and_metadata_single_part():
    os.environ["R2_BUCKET"] = "videos"
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket=os.environ["R2_BUCKET"])

    data = b"a" * (1024 * 1024)  # 1 MiB -> single part
    meta = r2_uploader.upload_file(io.BytesIO(data), "small.mp4", len(data))

    assert meta["key"] == "small.mp4"
    assert meta["size"] == len(data)
    head = r2_uploader.get_metadata("small.mp4")
    assert head["ContentLength"] == len(data)


@mock_aws
def test_retention_manager():
    os.environ["R2_BUCKET"] = "videos"
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket=os.environ["R2_BUCKET"])

    s3.put_object(Bucket=os.environ["R2_BUCKET"], Key="a.mp4", Body=b"a")
    time.sleep(1)
    s3.put_object(Bucket=os.environ["R2_BUCKET"], Key="b.mp4", Body=b"b")

    deleted = r2_uploader.delete_oldest_if_over_quota(1)
    assert deleted == 1
    objs = s3.list_objects_v2(Bucket=os.environ["R2_BUCKET"]).get("Contents", [])
    assert len(objs) == 1
    assert objs[0]["Key"] == "b.mp4"


@mock_aws
def test_upload_path_and_prune(tmp_path):
    os.environ["R2_BUCKET"] = "videos"
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket=os.environ["R2_BUCKET"])

    a = tmp_path / "a.mp4"
    a.write_bytes(b"a")
    b = tmp_path / "b.mp4"
    b.write_bytes(b"b")

    r2_uploader.upload_path_and_prune(str(a), "a.mp4", max_total_bytes=10)
    r2_uploader.upload_path_and_prune(str(b), "b.mp4", max_total_bytes=1)

    objs = s3.list_objects_v2(Bucket=os.environ["R2_BUCKET"]).get("Contents", [])
    assert len(objs) == 1
    assert objs[0]["Key"] == "b.mp4"

