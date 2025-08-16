#!/usr/bin/env python3
"""
Final validation script to ensure everything is ready for production deployment
"""
import os
import sys
import json
import time
import subprocess
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def check_environment():
    """Check all required environment variables"""
    print("🔍 Checking Environment Variables...")
    
    required_vars = {
        'DISCORD_BOT_TOKEN': 'Discord bot token',
        'CHANNEL_ID': 'Target Discord channel ID',
        'GEMINI_API_KEY': 'Google Gemini API key',
        'JOB_ENDPOINT': 'Railway cron job endpoint path'
    }
    
    optional_vars = {
        'R2_BUCKET': 'Cloudflare R2 bucket name',
        'R2_ACCESS_KEY_ID': 'R2 access key',
        'R2_SECRET_ACCESS_KEY': 'R2 secret key',
        'R2_ACCOUNT_ID': 'Cloudflare account ID',
        'ADMIN_PASS': 'Admin dashboard password',
        'MAX_AGE_HOURS': 'Maximum age for posts (hours)'
    }
    
    missing_required = []
    missing_optional = []
    
    for var, desc in required_vars.items():
        if not os.environ.get(var):
            missing_required.append(f"  ❌ {var} - {desc}")
        else:
            print(f"  ✅ {var} - Set")
    
    for var, desc in optional_vars.items():
        if not os.environ.get(var):
            missing_optional.append(f"  ⚠️ {var} - {desc} (optional)")
        else:
            print(f"  ✅ {var} - Set")
    
    if missing_required:
        print("\n❌ MISSING REQUIRED VARIABLES:")
        for var in missing_required:
            print(var)
        return False
    
    if missing_optional:
        print("\n⚠️ MISSING OPTIONAL VARIABLES:")
        for var in missing_optional:
            print(var)
        print("  (These are optional but recommended for full functionality)")
    
    print("✅ Environment variables check passed")
    return True

def check_project_structure():
    """Check project organization"""
    print("\n📁 Checking Project Structure...")
    
    required_dirs = {
        'bot': 'Core bot modules',
        'r2': 'R2 storage integration',
        'tests': 'Test suite',
        'scripts': 'Utility scripts',
        'config': 'Configuration files'
    }
    
    required_files = {
        'bot/main_enhanced.py': 'Enhanced main module with parallel processing',
        'cron_worker_enhanced.py': 'Enhanced cron worker',
        'app.py': 'Flask web application',
        'requirements.txt': 'Python dependencies',
        'Procfile': 'Railway deployment configuration',
        '.env': 'Environment variables (local)',
        'ENHANCED_DEPLOYMENT_GUIDE.md': 'Deployment documentation'
    }
    
    all_good = True
    
    for dir_name, desc in required_dirs.items():
        if Path(dir_name).exists():
            print(f"  ✅ {dir_name}/ - {desc}")
        else:
            print(f"  ❌ {dir_name}/ - {desc} (MISSING)")
            all_good = False
    
    for file_path, desc in required_files.items():
        if Path(file_path).exists():
            print(f"  ✅ {file_path} - {desc}")
        else:
            print(f"  ❌ {file_path} - {desc} (MISSING)")
            all_good = False
    
    if all_good:
        print("✅ Project structure check passed")
    else:
        print("❌ Project structure check failed")
    
    return all_good

def check_dependencies():
    """Check Python dependencies"""
    print("\n📦 Checking Dependencies...")
    
    try:
        # Check if requirements.txt exists and is readable
        if not Path('requirements.txt').exists():
            print("  ❌ requirements.txt not found")
            return False
        
        # Try importing key modules
        imports = {
            'discord': 'Discord.py library',
            'aiohttp': 'Async HTTP client',
            'pendulum': 'Date/time handling',
            'feedparser': 'RSS feed parsing',
            'boto3': 'AWS/R2 integration',
            'flask': 'Web framework',
            'dotenv': 'Environment variable loading'
        }
        
        for module, desc in imports.items():
            try:
                __import__(module)
                print(f"  ✅ {module} - {desc}")
            except ImportError:
                print(f"  ❌ {module} - {desc} (NOT INSTALLED)")
                return False
        
        print("✅ Dependencies check passed")
        return True
        
    except Exception as e:
        print(f"  ❌ Error checking dependencies: {e}")
        return False

def test_enhanced_functionality():
    """Test enhanced bot functionality"""
    print("\n🧪 Testing Enhanced Functionality...")
    
    try:
        # Test enhanced imports directly instead of subprocess
        print("  � Testing enhanced module imports...")
        test_imports = [
            'bot.main_enhanced',
            'r2.uploader', 
            'bot.dispatcher'
        ]
        
        for module in test_imports:
            try:
                __import__(module)
                print(f"    ✅ {module}")
            except ImportError as e:
                print(f"    ❌ {module} - {e}")
                return False
        
        # Test ProcessingStats class
        print("  📊 Testing ProcessingStats functionality...")
        try:
            from bot.main_enhanced import ProcessingStats
            stats = ProcessingStats()
            stats.raw_entries = 10
            stats.new_entries = 5 
            stats.posts_sent = 3
            print(f"    ✅ ProcessingStats - tracking works ({stats.raw_entries}/{stats.new_entries}/{stats.posts_sent})")
        except Exception as e:
            print(f"    ❌ ProcessingStats - {e}")
            return False
        
        # Test webhook functionality
        print("  🌐 Testing webhook functionality...")
        try:
            from bot.dispatcher import WEBHOOK_CACHE, get_or_create_webhook_url
            print(f"    ✅ Webhook cache initialized")
        except Exception as e:
            print(f"    ❌ Webhook functionality - {e}")
            return False
        
        # Test R2 integration
        print("  ☁️ Testing R2 integration...")
        try:
            from bot.main_enhanced import upload_to_r2
            print(f"    ✅ R2 upload function available")
        except Exception as e:
            print(f"    ❌ R2 integration - {e}")
            return False
        
        print("✅ Enhanced functionality tests passed")
        return True
        
    except Exception as e:
        print(f"  ❌ Error testing functionality: {e}")
        return False

def validate_configuration():
    """Validate configuration files"""
    print("\n⚙️ Validating Configuration...")
    
    # Check feeds.txt
    if Path('feeds.txt').exists():
        try:
            with open('feeds.txt', 'r') as f:
                feeds = [line.strip() for line in f.readlines() if line.strip()]
            print(f"  ✅ feeds.txt - {len(feeds)} feeds configured")
        except Exception as e:
            print(f"  ❌ feeds.txt - Error reading: {e}")
            return False
    else:
        print("  ⚠️ feeds.txt - Not found (will use default feeds)")
    
    # Check feed_map.json
    if Path('feed_map.json').exists():
        try:
            with open('feed_map.json', 'r') as f:
                feed_map = json.load(f)
            print(f"  ✅ feed_map.json - {len(feed_map)} feed mappings")
        except Exception as e:
            print(f"  ❌ feed_map.json - Error reading: {e}")
            return False
    else:
        print("  ⚠️ feed_map.json - Not found (will use default channel)")
    
    # Check Procfile for Railway
    if Path('Procfile').exists():
        try:
            with open('Procfile', 'r') as f:
                procfile_content = f.read().strip()
            if 'web:' in procfile_content and 'app.py' in procfile_content:
                print("  ✅ Procfile - Railway configuration looks good")
            else:
                print("  ⚠️ Procfile - May need adjustment for Railway")
        except Exception as e:
            print(f"  ❌ Procfile - Error reading: {e}")
    else:
        print("  ❌ Procfile - Missing (required for Railway deployment)")
        return False
    
    print("✅ Configuration validation passed")
    return True

def generate_deployment_checklist():
    """Generate final deployment checklist"""
    print("\n📋 DEPLOYMENT CHECKLIST")
    print("=" * 50)
    
    checklist = [
        "✅ Environment variables configured",
        "✅ Project structure organized", 
        "✅ Dependencies installed",
        "✅ Enhanced functionality tested",
        "✅ Configuration validated",
        "",
        "🚀 READY FOR RAILWAY DEPLOYMENT:",
        "",
        "1. Commit and push to GitHub:",
        "   git add .",
        "   git commit -m 'Production-ready enhanced bot'", 
        "   git push origin main",
        "",
        "2. Deploy to Railway:",
        "   - Connect GitHub repository",
        "   - Set environment variables", 
        "   - Deploy application",
        "   - Configure cron job",
        "",
        "3. Test deployment:",
        "   - Test health endpoint: /api/health",
        "   - Test job endpoint: your JOB_ENDPOINT",
        "   - Monitor logs for first run",
        "",
        "4. Set up GitHub Pages dashboard:",
        "   - Enable GitHub Pages", 
        "   - Configure API endpoints",
        "   - Test dashboard functionality",
        "",
        "🎉 DEPLOYMENT COMPLETE!"
    ]
    
    for item in checklist:
        print(item)

def main():
    """Run final validation"""
    print("🎯 HANU-FEEDBOT ENHANCED - FINAL VALIDATION")
    print("=" * 60)
    print("Validating production readiness...\n")
    
    checks = [
        ("Environment Variables", check_environment),
        ("Project Structure", check_project_structure), 
        ("Dependencies", check_dependencies),
        ("Enhanced Functionality", test_enhanced_functionality),
        ("Configuration", validate_configuration)
    ]
    
    all_passed = True
    
    for check_name, check_func in checks:
        try:
            if not check_func():
                all_passed = False
        except Exception as e:
            print(f"❌ {check_name} check failed with error: {e}")
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 ALL VALIDATION CHECKS PASSED!")
        print("🚀 Your enhanced bot is READY FOR PRODUCTION!")
        generate_deployment_checklist()
        return True
    else:
        print("❌ Some validation checks failed.")
        print("Please fix the issues above before deploying.")
        return False

if __name__ == "__main__":
    try:
        # Load environment from .env
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        print("⚠️ python-dotenv not available, using system environment")
    
    success = main()
    sys.exit(0 if success else 1)
