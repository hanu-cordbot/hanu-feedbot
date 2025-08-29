#!/usr/bin/env python3
"""
Local test script for R2 video upload logic
Simulates the upload process without actually uploading to debug issues
"""
import os
import sys
import tempfile
import random
from pathlib import Path

# Add the bot module to path so we can import
sys.path.insert(0, str(Path(__file__).parent))

# Set test environment variables
os.environ['R2_BUCKET'] = 'hanu-feedbot-seen'
os.environ['R2_PUBLIC_URL'] = 'https://pub-12350027ec6c427c8f0b83401e0310bb.r2.dev'
os.environ['R2_ACCESS_KEY_ID'] = '6ce69204b897d9e11f39133e5810315c'
os.environ['R2_SECRET_ACCESS_KEY'] = '1af8e2a76c65113220b73819662e5dfb0ebeb0d4ff7d687ebfd51c971b874474'
os.environ['R2_ENDPOINT'] = 'https://fac2cd87940bd85e71170e5cc88fe0b0.r2.cloudflarestorage.com/'

# Import after setting env vars
from bot.r2_video import (
    generate_video_filename,
    should_use_r2_storage,
    get_video_size_limit,
    build_public_url_for_key
)

def test_filename_generation():
    """Test video filename generation"""
    print("🧪 Testing filename generation...")
    filename = generate_video_filename("This content isn't available right now")
    print(f"   Generated filename: {filename}")
    assert filename.startswith("videos/")
    assert "This_content_isnt_available_right_now" in filename
    print("   ✅ Filename generation works")

def test_size_limits():
    """Test size limit logic"""
    print("\n🧪 Testing size limits...")
    limit = get_video_size_limit()
    print(f"   Discord size limit: {limit/1024/1024:.1f}MB")
    
    small_file = 5 * 1024 * 1024  # 5MB
    large_file = 10 * 1024 * 1024  # 10MB
    
    print(f"   5MB file should use R2: {should_use_r2_storage(small_file)} (Expected: False)")
    print(f"   10MB file should use R2: {should_use_r2_storage(large_file)} (Expected: True)")
    
    assert not should_use_r2_storage(small_file)
    assert should_use_r2_storage(large_file)
    print("   ✅ Size limit logic works")

def test_public_url_building():
    """Test public URL building"""
    print("\n🧪 Testing public URL building...")
    test_key = "videos/20250824_Test_Video_12345678.mp4"
    
    # Test with R2_PUBLIC_URL set
    public_url = build_public_url_for_key(test_key)
    expected_url = f"https://pub-12350027ec6c427c8f0b83401e0310bb.r2.dev/{test_key}"
    
    print(f"   Built URL: {public_url}")
    print(f"   Expected:  {expected_url}")
    
    assert public_url == expected_url
    print("   ✅ Public URL building works")

def simulate_upload_decision():
    """Simulate the upload decision logic"""
    print("\n🧪 Simulating upload decision logic...")
    
    # Simulate entry data
    entry = {
        'title': "This content isn't available right now",
        'page_name': 'Test Page',
        'link': 'https://facebook.com/test/post'
    }
    
    # Simulate file sizes
    test_cases = [
        (5 * 1024 * 1024, "5MB file"),
        (10 * 1024 * 1024, "10MB file"),
        (50 * 1024 * 1024, "50MB file")
    ]
    
    for file_size, description in test_cases:
        print(f"\n   Testing {description} ({file_size/1024/1024:.1f}MB):")
        
        if file_size < get_video_size_limit():
            print(f"     → Would upload directly to Discord")
            decision = "discord"
        elif should_use_r2_storage(file_size):
            print(f"     → Would upload to R2")
            # Simulate URL generation
            filename = generate_video_filename(entry['title'])
            public_url = build_public_url_for_key(filename)
            print(f"     → R2 URL: {public_url}")
            decision = "r2"
        else:
            print(f"     → File too large for any storage")
            decision = "skip"
        
        print(f"     → Decision: {decision}")

def test_env_vars():
    """Test environment variable detection"""
    print("\n🧪 Testing environment variables...")
    
    required_vars = ['R2_BUCKET', 'R2_PUBLIC_URL', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_ENDPOINT']
    
    for var in required_vars:
        value = os.getenv(var)
        if value:
            # Mask sensitive values
            if 'SECRET' in var or 'KEY' in var:
                masked = value[:8] + '...' + value[-4:] if len(value) > 12 else '***'
                print(f"   {var}: {masked}")
            else:
                print(f"   {var}: {value}")
        else:
            print(f"   {var}: ❌ NOT SET")
    
    # Test R2_PUBLIC_URL specifically
    r2_public = os.getenv('R2_PUBLIC_URL')
    if r2_public:
        print(f"\n   ✅ R2_PUBLIC_URL is set correctly")
        print(f"   → Videos will use: {r2_public}/videos/...")
    else:
        print(f"\n   ❌ R2_PUBLIC_URL is not set - videos would fail!")

def main():
    """Run all tests"""
    print("🚀 HANU FEEDBOT - R2 VIDEO UPLOAD TEST")
    print("=" * 50)
    
    try:
        test_env_vars()
        test_filename_generation()
        test_size_limits()
        test_public_url_building()
        simulate_upload_decision()
        
        print("\n" + "=" * 50)
        print("🎉 ALL TESTS PASSED!")
        print("\nNext steps:")
        print("1. Ensure R2_PUBLIC_URL is set in your deployment environment")
        print("2. Restart the bot so it picks up the environment variable")
        print("3. Check bot logs for the masked R2_PUBLIC_URL line at startup")
        print("4. Test with a large video to verify R2 upload works")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
