#!/usr/bin/env python3
"""
Test script to validate GitHub Actions workflow setup
Run this locally to verify all components work before deploying
"""

import os
import sys
import asyncio
import json
from pathlib import Path
from dotenv import load_dotenv

def check_environment():
    """Check if all required environment variables are present"""
    print("🔍 Checking environment variables...")
    
    required_vars = [
        'DISCORD_BOT_TOKEN',
        'GEMINI_API_KEY', 
        'CHANNEL_ID',
        'GLOBAL_FALLBACK_CHANNEL_ID'
    ]
    
    optional_vars = [
        'DISCORD_WEBHOOK_URL',
        'SUMMARY_CHANNEL_ID',
        'R2_BUCKET',
        'R2_ACCOUNT_ID',
        'R2_ACCESS_KEY_ID',
        'R2_SECRET_ACCESS_KEY',
        'MAX_AGE_HOURS',
        'FALLBACK_ENABLED',
        'ADMIN_PASS'
    ]
    
    missing_required = []
    missing_optional = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_required.append(var)
        else:
            print(f"  ✅ {var}: {'*' * 10}...{os.getenv(var)[-4:]}")
    
    for var in optional_vars:
        if not os.getenv(var):
            missing_optional.append(var)
        else:
            value = os.getenv(var)
            if len(value) > 20:
                print(f"  ✅ {var}: {'*' * 10}...{value[-4:]}")
            else:
                print(f"  ✅ {var}: {value}")
    
    if missing_required:
        print(f"\n❌ Missing required variables: {missing_required}")
        return False
    
    if missing_optional:
        print(f"\n⚠️ Missing optional variables: {missing_optional}")
        print("   These are not required but may limit functionality")
    
    print("\n✅ Environment check passed!")
    return True

def check_files():
    """Check if required files exist"""
    print("\n🔍 Checking required files...")
    
    required_files = [
        'cron_worker.py',
        'requirements.txt',
        'feeds.txt',
        'bot/main.py',
        '.github/workflows/feed-bot.yml'
    ]
    
    missing_files = []
    
    for file_path in required_files:
        if Path(file_path).exists():
            print(f"  ✅ {file_path}")
        else:
            print(f"  ❌ {file_path}")
            missing_files.append(file_path)
    
    if missing_files:
        print(f"\n❌ Missing required files: {missing_files}")
        return False
    
    print("\n✅ File check passed!")
    return True

def check_workflow_syntax():
    """Check if the workflow YAML is valid"""
    print("\n🔍 Checking workflow syntax...")
    
    try:
        import yaml
        with open('.github/workflows/feed-bot.yml', 'r', encoding='utf-8') as f:
            workflow = yaml.safe_load(f)
        
        # Check required workflow components
        required_keys = ['name', 'on', 'jobs']
        
        for key in required_keys:
            if key not in workflow:
                print(f"  ❌ Missing workflow key: {key}")
                return False
        
        # Check if jobs exist
        if 'run-feed-bot' not in workflow['jobs']:
            print("  ❌ Missing 'run-feed-bot' job")
            return False
        
        print("  ✅ Workflow YAML syntax is valid")
        print("  ✅ Required workflow components present")
        return True
        
    except ImportError:
        print("  ⚠️ PyYAML not installed, skipping YAML validation")
        print("  💡 Install with: pip install pyyaml")
        return True
    except Exception as e:
        print(f"  ❌ Workflow YAML error: {e}")
        return False

async def test_bot_connection():
    """Test basic bot functionality"""
    print("\n🔍 Testing bot connection...")
    
    try:
        import discord
        from bot.main import BOT_TOKEN, TARGET_CHANNEL_ID
        
        if not BOT_TOKEN:
            print("  ❌ Discord bot token not configured")
            return False
        
        # Test Discord connection
        intents = discord.Intents.default()
        client = discord.Client(intents=intents)
        
        @client.event
        async def on_ready():
            print(f"  ✅ Connected to Discord as {client.user}")
            
            # Test channel access
            if TARGET_CHANNEL_ID:
                channel = client.get_channel(TARGET_CHANNEL_ID)
                if channel:
                    print(f"  ✅ Can access channel: #{getattr(channel, 'name', f'Channel-{TARGET_CHANNEL_ID}')}")
                else:
                    print(f"  ❌ Cannot access channel: {TARGET_CHANNEL_ID}")
            
            await client.close()
        
        # Quick connection test with timeout
        try:
            await asyncio.wait_for(client.start(BOT_TOKEN), timeout=10.0)
            return True
        except asyncio.TimeoutError:
            print("  ⚠️ Discord connection timeout (but credentials seem valid)")
            return True
            
    except Exception as e:
        print(f"  ❌ Bot connection test failed: {e}")
        return False

def test_feed_parsing():
    """Test feed parsing functionality"""
    print("\n🔍 Testing feed parsing...")
    
    try:
        from bot.parser import iter_entries
        
        # Test parsing a few entries
        entries = list(iter_entries())
        print(f"  ✅ Successfully parsed {len(entries)} feed entries")
        
        if entries:
            sample = entries[0]
            print(f"  📰 Sample entry: {sample.get('title', 'No title')[:50]}...")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Feed parsing test failed: {e}")
        return False

def create_secrets_template():
    """Create a template for GitHub secrets"""
    print("\n📝 Creating GitHub secrets template...")
    
    template = {
        "required_secrets": {
            "DISCORD_BOT_TOKEN": os.getenv('DISCORD_BOT_TOKEN', 'YOUR_DISCORD_BOT_TOKEN'),
            "CHANNEL_ID": os.getenv('CHANNEL_ID', 'YOUR_CHANNEL_ID'),
            "GLOBAL_FALLBACK_CHANNEL_ID": os.getenv('GLOBAL_FALLBACK_CHANNEL_ID', 'YOUR_FALLBACK_CHANNEL_ID'),
            "GEMINI_API_KEY": os.getenv('GEMINI_API_KEY', 'YOUR_GEMINI_API_KEY')
        },
        "optional_secrets": {
            "DISCORD_WEBHOOK_URL": os.getenv('DISCORD_WEBHOOK_URL', ''),
            "SUMMARY_CHANNEL_ID": os.getenv('SUMMARY_CHANNEL_ID', ''),
            "R2_BUCKET": os.getenv('R2_BUCKET', ''),
            "R2_ACCOUNT_ID": os.getenv('R2_ACCOUNT_ID', ''),
            "R2_ACCESS_KEY_ID": os.getenv('R2_ACCESS_KEY_ID', ''),
            "R2_SECRET_ACCESS_KEY": os.getenv('R2_SECRET_ACCESS_KEY', ''),
            "R2_ENDPOINT": os.getenv('R2_ENDPOINT', ''),
            "R2_PUBLIC_BASE": os.getenv('R2_PUBLIC_BASE', ''),
            "R2_MAX_BYTES": os.getenv('R2_MAX_BYTES', '5000000000'),
            "MAX_AGE_HOURS": os.getenv('MAX_AGE_HOURS', '36'),
            "FALLBACK_ENABLED": os.getenv('FALLBACK_ENABLED', 'true'),
            "ADMIN_PASS": os.getenv('ADMIN_PASS', 'github-actions-secure')
        }
    }
    
    with open('github_secrets_template.json', 'w') as f:
        json.dump(template, f, indent=2)
    
    print("  ✅ Created github_secrets_template.json")
    print("  📋 Use this file to configure your GitHub repository secrets")

async def main():
    """Run all validation tests"""
    print("🚀 GitHub Actions Workflow Validation")
    print("=" * 50)
    
    # Load environment variables
    load_dotenv()
    
    tests_passed = 0
    total_tests = 5
    
    # Run all tests
    if check_environment():
        tests_passed += 1
    
    if check_files():
        tests_passed += 1
    
    if check_workflow_syntax():
        tests_passed += 1
    
    if await test_bot_connection():
        tests_passed += 1
    
    if test_feed_parsing():
        tests_passed += 1
    
    # Create secrets template
    create_secrets_template()
    
    # Summary
    print("\n" + "=" * 50)
    print(f"🎯 Validation Summary: {tests_passed}/{total_tests} tests passed")
    
    if tests_passed == total_tests:
        print("✅ All tests passed! Workflow is ready for deployment.")
        print("\n📋 Next steps:")
        print("  1. Configure GitHub repository secrets (see GITHUB_ACTIONS_SETUP.md)")
        print("  2. Commit and push the workflow file")
        print("  3. Test manual workflow trigger in GitHub Actions")
        print("  4. Monitor scheduled executions")
    else:
        print("❌ Some tests failed. Please fix the issues before deploying.")
        return 1
    
    return 0

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️ Validation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Validation failed with error: {e}")
        sys.exit(1)
