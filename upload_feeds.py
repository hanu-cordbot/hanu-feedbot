import boto3,os,json,sys
endpoint = os.environ.get('R2_ENDPOINT')
access = os.environ.get('R2_ACCESS_KEY_ID')
secret = os.environ.get('R2_SECRET_ACCESS_KEY')
bucket = os.environ.get('R2_BUCKET') or os.environ.get('FEEDS_R2_BUCKET') or os.environ.get('SEEN_R2_BUCKET') or 'hanu-feedbot-seen'
if not (endpoint and access and secret):
    print('Missing R2 env vars: R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY')
    sys.exit(1)
s3 = boto3.client('s3', aws_access_key_id=access, aws_secret_access_key=secret, endpoint_url=endpoint)
key = 'feeds.txt'
try:
    with open('feeds.txt','rb') as fh:
        s3.upload_fileobj(fh,bucket,key)
    print('Uploaded feeds.txt -> s3://%s/%s' % (bucket,key))
    meta = s3.head_object(Bucket=bucket,Key=key)
    print(json.dumps({'ContentLength':meta.get('ContentLength'),'ContentType':meta.get('ContentType'),'ContentEncoding':meta.get('ContentEncoding'),'LastModified':str(meta.get('LastModified'))},indent=2))
    s3.download_file(bucket,key,'feeds.downloaded.txt')
    print('\nDownloaded file preview:')
    with open('feeds.downloaded.txt','r',encoding='utf-8') as f:
        for i,l in enumerate(f):
            if i>9: break
            print(l.rstrip())
except Exception as e:
    print('ERROR', e)
    sys.exit(2)
