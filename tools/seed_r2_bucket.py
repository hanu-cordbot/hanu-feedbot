#!/usr/bin/env python3
"""
Seed the R2 bucket with minimal dashboard/data/source JSON files and publish stats.json.

Env vars:
  R2_BUCKET, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT

Behavior:
  - Ensures these keys exist (creates empty defaults if missing):
      dashboard/data/source/feed_map.json -> {}
      dashboard/data/source/channels.json -> []
      dashboard/data/source/groups.json   -> {}
      dashboard/data/source/feeds.txt     -> '' (optional)
  - If docs/data/stats.json exists locally, uploads to dashboard/data/stats.json
"""
import os
import json
import sys

REQUIRED = {
    'dashboard/data/source/feed_map.json': json.dumps({}, indent=2),
    'dashboard/data/source/channels.json': json.dumps([], indent=2),
    'dashboard/data/source/groups.json': json.dumps({}, indent=2),
}

def main():
    bucket = os.getenv('R2_BUCKET') or os.getenv('FEEDS_R2_BUCKET')
    access = os.getenv('R2_ACCESS_KEY_ID')
    secret = os.getenv('R2_SECRET_ACCESS_KEY')
    endpoint = os.getenv('R2_ENDPOINT')
    if not bucket or not access or not secret:
        print('Missing R2 envs (R2_BUCKET/FEEDS_R2_BUCKET, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY).')
        return 1
    try:
        import boto3
    except Exception:
        print('Installing boto3...')
        os.system(f"{sys.executable} -m pip install -q boto3")
        import boto3  # noqa
    s3 = boto3.client('s3', aws_access_key_id=access, aws_secret_access_key=secret, endpoint_url=endpoint)

    # Ensure required JSON files exist
    for key, default in REQUIRED.items():
        try:
            s3.head_object(Bucket=bucket, Key=key)
            print('exists:', key)
        except Exception:
            print('creating:', key)
            s3.put_object(Bucket=bucket, Key=key, Body=default.encode('utf-8'), ContentType='application/json')

    # Optional feeds.txt
    feeds_key = 'dashboard/data/source/feeds.txt'
    try:
        s3.head_object(Bucket=bucket, Key=feeds_key)
        print('exists:', feeds_key)
    except Exception:
        print('creating empty:', feeds_key)
        s3.put_object(Bucket=bucket, Key=feeds_key, Body=b'', ContentType='text/plain')

    # Publish stats.json if available locally
    local_stats = 'docs/data/stats.json'
    if os.path.exists(local_stats):
        with open(local_stats, 'rb') as fh:
            data = fh.read()
        dest = 'dashboard/data/stats.json'
        print('upload:', dest)
        s3.put_object(Bucket=bucket, Key=dest, Body=data, ContentType='application/json')
    else:
        print('local stats.json not found; skipping publish')
    print('Done.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())

