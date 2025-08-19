#!/usr/bin/env python3
"""
Direct upload test for seen.json to R2
This mimics what the bot does when uploading seen.json
"""
import os
import json
import sys
from pathlib import Path

# Add the parent directory to path so we can import bot modules
sys.path.insert(0, str(Path(__file__).parent.parent))

def upload_test_seen():
    """Upload a test seen.json directly to R2"""
    
    # Import bot modules for R2 client
    try:
        from bot.config import r2_client, SEEN_R2_BUCKET
    except Exception as e:
        print(f"❌ Could not import bot config: {e}")
        return False
    
    if not SEEN_R2_BUCKET:
        print("❌ SEEN_R2_BUCKET not configured")
        return False
    
    # Create test seen.json data
    test_guids = [
        f"test-upload-{i}" for i in range(5)
    ]
    
    print(f"🚀 Uploading test seen.json with {len(test_guids)} GUIDs to bucket: {SEEN_R2_BUCKET}")
    
    try:
        client = r2_client()
        if not client:
            print("❌ Could not create R2 client")
            return False
        
        # Upload plain JSON using the same method as the bot (no gzip)
        import io
        buf = io.BytesIO()
        buf.write(json.dumps(test_guids).encode('utf-8'))
        buf.seek(0)

        try:
            client.upload_fileobj(buf, SEEN_R2_BUCKET, 'seen.json')
            print("✅ Upload successful using upload_fileobj")
        except TypeError:
            # Fallback if client.upload_fileobj signature differs
            client.put_object(Bucket=SEEN_R2_BUCKET, Key='seen.json', Body=buf.getvalue())
            print("✅ Upload successful using put_object")
        
        return True
        
    except Exception as e:
        print(f"❌ Upload failed: {e}")
        return False

def download_and_verify():
    """Download and verify the uploaded seen.json"""
    
    try:
        from bot.config import r2_client, SEEN_R2_BUCKET
    except Exception as e:
        print(f"❌ Could not import bot config: {e}")
        return False
    
    try:
        client = r2_client()
        if not client:
            print("❌ Could not create R2 client")
            return False
        
        print(f"📥 Downloading seen.json from bucket: {SEEN_R2_BUCKET}")
        import io
        buf = io.BytesIO()
        client.download_fileobj(SEEN_R2_BUCKET, 'seen.json', buf)
        buf.seek(0)
        guids = json.load(buf)

        print(f"✅ Downloaded seen.json with {len(guids)} GUIDs")
        print(f"📄 Contents: {guids}")
        return True

    except Exception as e:
        print(f"❌ Download failed: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing direct R2 upload/download for seen.json")
    print()
    
    # Test upload
    print("1️⃣ Testing upload...")
    upload_ok = upload_test_seen()
    print()
    
    if upload_ok:
        # Test download
        print("2️⃣ Testing download...")
        download_ok = download_and_verify()
        print()
        
        print("📊 Summary:")
        print(f"  Upload: {'✅' if upload_ok else '❌'}")
        print(f"  Download: {'✅' if download_ok else '❌'}")
        
        if upload_ok and download_ok:
            print("\n🎉 seen.json is now present in R2 bucket!")
        else:
            print("\n❌ Test failed")
    else:
        print("❌ Upload test failed, skipping download test")
