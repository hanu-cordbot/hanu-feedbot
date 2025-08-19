#!/usr/bin/env python3
"""
Quick R2 bucket checker - lists contents of the SEEN_R2_BUCKET
"""
import os
import boto3
from dotenv import load_dotenv

# Load environment
load_dotenv()

def check_r2_bucket():
    """Check what's in the R2 bucket"""
    
    # Get R2 credentials from environment
    access_key = os.environ.get('R2_ACCESS_KEY_ID')
    secret_key = os.environ.get('R2_SECRET_ACCESS_KEY') 
    endpoint = os.environ.get('R2_ENDPOINT')
    bucket_name = os.environ.get('SEEN_R2_BUCKET')
    
    if not all([access_key, secret_key, endpoint, bucket_name]):
        print("❌ Missing R2 credentials. Need: R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT, SEEN_R2_BUCKET")
        return
    
    print(f"🔍 Checking R2 bucket: {bucket_name}")
    print(f"📡 Endpoint: {endpoint}")
    
    try:
        # Create S3 client for R2
        s3 = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=endpoint
        )
        
        # List bucket contents
        response = s3.list_objects_v2(Bucket=bucket_name)
        
        if 'Contents' in response:
            print(f"✅ Bucket contains {len(response['Contents'])} objects:")
            for obj in response['Contents']:
                size_kb = obj['Size'] / 1024
                print(f"  📄 {obj['Key']} ({size_kb:.1f} KB) - {obj['LastModified']}")
                
                # If it's seen.json, try to download and inspect
                if obj['Key'] == 'seen.json':
                    print(f"    🎯 Found seen.json! Downloading...")
                    try:
                        obj_response = s3.get_object(Bucket=bucket_name, Key='seen.json')
                        content = obj_response['Body'].read()
                        
                        # Check if it's gzipped
                        if content.startswith(b'\x1f\x8b'):
                            import gzip
                            content = gzip.decompress(content)
                            print(f"    📦 File is gzipped")
                        
                        # Parse JSON content
                        import json
                        data = json.loads(content.decode('utf-8'))
                        print(f"    📊 Contains {len(data)} seen GUIDs")
                        if data:
                            print(f"    🔍 First few: {data[:3]}")
                    except Exception as e:
                        print(f"    ❌ Error reading seen.json: {e}")
        else:
            print("❌ Bucket is empty")
            
    except Exception as e:
        print(f"❌ Error accessing R2 bucket: {e}")

if __name__ == "__main__":
    check_r2_bucket()
