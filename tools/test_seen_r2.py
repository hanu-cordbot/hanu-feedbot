#!/usr/bin/env python3
"""Simple R2 round-trip test for seen.json.

This script does not import bot.main to avoid starting the bot. It exercises the same R2 read/write
path used by the bot: upload a small test seen.json, download and verify, modify and re-upload,
then restore the previous state.

Environment variables required (set these in Actions secrets or locally):
- R2_ACCESS_KEY_ID
- R2_SECRET_ACCESS_KEY
- R2_ENDPOINT
- SEEN_R2_BUCKET

Exit codes: 0 = success, non-zero = failure
"""
import os
import sys
import json
import time
import uuid
from io import BytesIO

try:
    import boto3
except Exception as e:
    print("❌ Missing dependency boto3:", e)
    sys.exit(2)

# Create an S3/R2 client directly from environment variables instead of importing bot.config
def make_r2_client():
    access_key = os.getenv('R2_ACCESS_KEY_ID') or os.getenv('R2_ACCESS_KEY')
    secret = os.getenv('R2_SECRET_ACCESS_KEY') or os.getenv('R2_SECRET')
    endpoint = os.getenv('R2_ENDPOINT')
    if not access_key or not secret or not endpoint:
        return None
    try:
        return boto3.client('s3', aws_access_key_id=access_key, aws_secret_access_key=secret, endpoint_url=endpoint)
    except Exception:
        return None

BUCKET = os.getenv('SEEN_R2_BUCKET')
KEY = 'seen.json'
BACKUP_KEY = f'seen_backup_{int(time.time())}_{uuid.uuid4().hex[:6]}.json'

if not BUCKET:
    print('❌ SEEN_R2_BUCKET not set')
    sys.exit(2)

client = make_r2_client()
if not client:
    print('❌ Could not create R2 client - check credentials')
    sys.exit(2)

def object_exists(key):
    try:
        client.head_object(Bucket=BUCKET, Key=key)
        return True
    except Exception:
        return False

# Backup existing seen.json if present
had_backup = False
try:
    if object_exists(KEY):
        print('📦 Backing up existing seen.json to', BACKUP_KEY)
        client.copy_object(Bucket=BUCKET, CopySource={'Bucket': BUCKET, 'Key': KEY}, Key=BACKUP_KEY)
        had_backup = True
except Exception as e:
    print('⚠️ Failed to backup existing seen.json:', e)
    # continue, we may overwrite

try:
    # 1) Upload initial test seen
    seen1 = [f'ci-test-{uuid.uuid4().hex[:8]}']
    buf = BytesIO()
    buf.write(json.dumps(seen1).encode('utf-8'))
    buf.seek(0)
    client.upload_fileobj(buf, BUCKET, KEY)
    print('✅ Uploaded test seen.json:', seen1)

    # 2) Download and verify
    buf2 = BytesIO()
    client.download_fileobj(BUCKET, KEY, buf2)
    buf2.seek(0)
    got = json.load(buf2)
    if set(got) != set(seen1):
        print('❌ Mismatch after first upload. got=', got)
        raise SystemExit(3)
    print('✅ Verified first upload')

    # 3) Append another guid and re-upload
    got.append(f'ci-test-{uuid.uuid4().hex[:8]}')
    buf3 = BytesIO()
    buf3.write(json.dumps(got).encode('utf-8'))
    buf3.seek(0)
    client.upload_fileobj(buf3, BUCKET, KEY)
    print('✅ Uploaded appended seen.json:', got)

    # 4) Download and verify both present
    buf4 = BytesIO()
    client.download_fileobj(BUCKET, KEY, buf4)
    buf4.seek(0)
    final = json.load(buf4)
    if set(final) != set(got):
        print('❌ Mismatch after second upload. final=', final)
        raise SystemExit(4)
    print('✅ Round-trip verified. final entries:', final)

    result = 0
except Exception as e:
    print('❌ Test failed:', e)
    result = 5

# Restore backup if present, else delete the test key
try:
    if had_backup:
        print('🔁 Restoring backup to seen.json')
        client.copy_object(Bucket=BUCKET, CopySource={'Bucket': BUCKET, 'Key': BACKUP_KEY}, Key=KEY)
        client.delete_object(Bucket=BUCKET, Key=BACKUP_KEY)
    else:
        print('🧹 Deleting test seen.json')
        client.delete_object(Bucket=BUCKET, Key=KEY)
except Exception as e:
    print('⚠️ Failed to restore or delete test key:', e)
    result = result or 6

if result == 0:
    print('✅ R2 seen.json round-trip test passed')
else:
    print('❌ R2 seen.json round-trip test failed with code', result)

sys.exit(result)
