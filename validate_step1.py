#!/usr/bin/env python3
"""
Validation script for Step 1 of the GitHub Pages migration.
This script checks if the environment is properly configured for standalone execution.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def check_environment():
    """Check if all required environment variables are present"""
    print("🔍 Checking environment variables...")
    
    required_vars = [
        'DISCORD_BOT_TOKEN',
        'GEMINI_API_KEY', 
        'CHANNEL_ID'
    ]
    
    optional_vars = [
        'DISCORD_WEBHOOK_URL',
        'SUMMARY_CHANNEL_ID',
        'MAX_AGE_HOURS',
        'FALLBACK_ENABLED'
    ]
    
    missing_required = []
    missing_optional = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_required.append(var)
        else:
            print(f"  ✅ {var}: {'*' * min(len(os.getenv(var, '')), 10)}...")
    
    for var in optional_vars:
        if not os.getenv(var):
            missing_optional.append(var)
        else:
            print(f"  ✅ {var}: {os.getenv(var)}")
    
    if missing_required:
        print(f"\n❌ Missing required environment variables: {missing_required}")
        return False
    
    if missing_optional:
        print(f"\n⚠️  Missing optional environment variables: {missing_optional}")
        print("   Bot will work with reduced functionality")
    
    print("✅ Environment check passed!")
    return True

def check_dependencies():
    """Check if all required dependencies are installed"""
    print("\n🔍 Checking dependencies...")
    
    required_modules = [
        'discord',
        'feedparser', 
        'requests',
        'pendulum',
        'google.generativeai',
        'dotenv',
        'aiohttp'
    ]
    
    missing = []
    for module in required_modules:
        try:
            __import__(module)
            print(f"  ✅ {module}")
        except ImportError:
            missing.append(module)
            print(f"  ❌ {module}")
    
    if missing:
        print(f"\n❌ Missing dependencies: {missing}")
        print("Run: pip install -r requirements.txt")
        return False
    
    print("✅ All dependencies available!")
    return True

def check_files():
    """Check if required files exist"""
    print("\n🔍 Checking required files...")
    
    required_files = [
        'cron_worker.py',
        'bot/main.py',
        'requirements.txt',
        '.github/workflows/feed-bot.yml'
    ]
    
    missing = []
    for file_path in required_files:
        if Path(file_path).exists():
            print(f"  ✅ {file_path}")
        else:
            missing.append(file_path)
            print(f"  ❌ {file_path}")
    
    if missing:
        print(f"\n❌ Missing files: {missing}")
        return False
    
    print("✅ All required files present!")
    return True

def main():
    """Run all validation checks"""
    print("🚀 STEP 1 VALIDATION: Standalone Worker Creation")
    print("=" * 60)
    
    checks = [
        check_files(),
        check_dependencies(),
        check_environment()
    ]
    
    if all(checks):
        print("\n🎉 All checks passed! Ready for standalone execution.")
        print("\n📝 Next steps:")
        print("1. To test locally: python cron_worker.py")
        print("2. Set up GitHub repository secrets for Actions")
        print("3. Test GitHub Actions workflow manually")
        return 0
    else:
        print("\n❌ Some checks failed. Please fix the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
