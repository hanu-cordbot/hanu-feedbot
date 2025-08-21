import os
import io
import boto3
from typing import Optional


def upload_file(file_obj: io.BytesIO, key: str, size: int) -> Optional[str]:
    """Upload file-like object to R2-compatible S3 and return public URL or None."""
    bucket = os.getenv('R2_BUCKET')
    access = os.getenv('R2_ACCESS_KEY_ID')
    secret = os.getenv('R2_SECRET_ACCESS_KEY')
    endpoint = os.getenv('R2_ENDPOINT')
    public_base = os.getenv('R2_PUBLIC_BASE')

    if not (bucket and access and secret and endpoint):
        raise RuntimeError('R2 credentials not configured')

    s3 = boto3.client('s3', aws_access_key_id=access, aws_secret_access_key=secret, endpoint_url=endpoint)

    file_obj.seek(0)
    try:
        s3.upload_fileobj(file_obj, bucket, key, ExtraArgs={'ACL': 'private'})
    except Exception as e:
        print('R2 upload failed:', e)
        return None

    if public_base:
        return f"{public_base}/{key}"
    account_id = os.getenv('R2_ACCOUNT_ID')
    if account_id:
        return f"https://{account_id}.r2.cloudflarestorage.com/{bucket}/{key}"
    return None
