import boto3, os, sys, json
bucket = os.environ.get('R2_BUCKET')
if not bucket:
    print('R2_BUCKET not set in environment')
    sys.exit(1)
endpoint = os.environ.get('R2_ENDPOINT')
access = os.environ.get('R2_ACCESS_KEY_ID')
secret = os.environ.get('R2_SECRET_ACCESS_KEY')
try:
    s3 = boto3.client('s3', aws_access_key_id=access, aws_secret_access_key=secret, endpoint_url=endpoint)
    s3.download_file(bucket, 'feed_map.json', 'feed_map.downloaded.json')
    print(' Downloaded feed_map.json to feed_map.downloaded.json')
except Exception as e:
    print(' Failed to download feed_map.json:', e)
    sys.exit(2)

# Summarize contents
try:
    with open('feed_map.downloaded.json','r',encoding='utf-8') as f:
        m = json.load(f)
    print(f" Loaded {len(m)} mappings (sample up to 10):")
    keys = list(m.keys())[:10]
    for k in keys:
        print(' -', k, '->', m[k])
except Exception as e:
    print(' Could not read/parse feed_map.downloaded.json:', e)
