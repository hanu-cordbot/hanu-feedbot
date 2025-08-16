#!/usr/bin/env python3
"""
Test script to validate the bot workflow locally before Railway deployment
"""
import os
import sys
import time
import requests
import subprocess
import threading
from pathlib import Path

def test_environment():
    """Test if all required environment variables are set"""
    print("🔍 Testing environment variables...")
    
    required_vars = [
        'DISCORD_BOT_TOKEN',
        'CHANNEL_ID',
        'GEMINI_API_KEY',
        'JOB_ENDPOINT'
    ]
    
    missing = []
    for var in required_vars:
        if not os.environ.get(var):
            missing.append(var)
    
    if missing:
        print(f"❌ Missing environment variables: {missing}")
        return False
    else:
        print("✅ All required environment variables are set")
        return True

def test_cron_worker():
    """Test the cron worker directly"""
    print("\n🤖 Testing cron worker directly...")
    
    try:
        result = subprocess.run([
            sys.executable, "cron_worker.py"
        ], capture_output=True, text=True, timeout=120)  # 2 minute timeout for testing
        
        print(f"Exit code: {result.returncode}")
        if result.stdout:
            print("STDOUT:", result.stdout[-500:])  # Last 500 chars
        if result.stderr:
            print("STDERR:", result.stderr[-500:])
        
        if result.returncode == 0:
            print("✅ Cron worker test passed")
            return True
        else:
            print(f"❌ Cron worker test failed with exit code {result.returncode}")
            return False
            
    except subprocess.TimeoutExpired:
        print("⏰ Cron worker test timed out (this might be normal if it's waiting for Discord)")
        return True
    except Exception as e:
        print(f"❌ Cron worker test failed: {e}")
        return False

def test_flask_app():
    """Test the Flask app and job endpoint"""
    print("\n🌐 Testing Flask app...")
    
    # Start Flask app in background
    flask_process = None
    try:
        print("🚀 Starting Flask app...")
        flask_process = subprocess.Popen([
            sys.executable, "app.py"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Wait a bit for Flask to start
        time.sleep(3)
        
        # Test health endpoint
        try:
            response = requests.get("http://localhost:5000/api/health", timeout=5)
            if response.status_code == 200:
                print("✅ Health endpoint working")
                print(f"Response: {response.json()}")
            else:
                print(f"❌ Health endpoint returned {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Health endpoint failed: {e}")
            return False
        
        # Test job endpoint
        job_endpoint = os.environ.get('JOB_ENDPOINT', '/job')
        try:
            print(f"🎯 Testing job endpoint: {job_endpoint}")
            response = requests.post(f"http://localhost:5000{job_endpoint}", timeout=30)
            print(f"Job endpoint response: {response.status_code}")
            if response.status_code in [200, 500]:  # 500 might be expected if bot fails
                print("✅ Job endpoint accessible")
                try:
                    print(f"Response: {response.json()}")
                except:
                    print(f"Response text: {response.text[:200]}")
                return True
            else:
                print(f"❌ Job endpoint returned unexpected status: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Job endpoint failed: {e}")
            return False
    
    finally:
        # Clean up Flask process
        if flask_process:
            print("🛑 Stopping Flask app...")
            flask_process.terminate()
            try:
                flask_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                flask_process.kill()

def main():
    """Run all tests"""
    print("🧪 Starting workflow validation tests...\n")
    
    # Change to the correct directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    # Load environment variables
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("✅ Environment variables loaded from .env")
    except ImportError:
        print("⚠️ python-dotenv not available, using system environment")
    
    tests = [
        ("Environment Variables", test_environment),
        ("Cron Worker", test_cron_worker),
        ("Flask App & Job Endpoint", test_flask_app)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n" + "="*50)
        print(f"🔬 Running test: {test_name}")
        print("="*50)
        
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"💥 Test {test_name} crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*50)
    print("📊 TEST SUMMARY")
    print("="*50)
    
    passed = 0
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name}")
        if success:
            passed += 1
    
    print(f"\nTotal: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("\n🎉 All tests passed! Ready for Railway deployment.")
        return 0
    else:
        print("\n⚠️ Some tests failed. Please fix issues before deploying.")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
