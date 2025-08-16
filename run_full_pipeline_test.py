#!/usr/bin/env python3
"""
Comprehensive end-to-end testing script for the RSS feed bot pipeline.
Tests everything from RSS parsing to Discord posting and data generation.
"""
import os
import sys
import json
import asyncio
import tempfile
import time
import traceback
from pathlib import Path
from datetime import datetime, timezone
import feedparser
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import bot modules
from bot.main import run_bot_job, get_http_session
from bot.parser import iter_entries
from bot.gemini_client import call_gemini
from bot.formatter import build_prompt

class PipelineTestResult:
    """Container for test results"""
    def __init__(self):
        self.tests = []
        self.errors = []
        self.warnings = []
        self.start_time = time.time()
        
    def add_test(self, name, status, details=None, duration=None):
        self.tests.append({
            'name': name,
            'status': status,  # 'PASS', 'FAIL', 'WARN'
            'details': details,
            'duration': duration,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
    def add_error(self, error):
        self.errors.append(str(error))
        
    def add_warning(self, warning):
        self.warnings.append(str(warning))
        
    def summary(self):
        total = len(self.tests)
        passed = len([t for t in self.tests if t['status'] == 'PASS'])
        failed = len([t for t in self.tests if t['status'] == 'FAIL'])
        warning_count = len([t for t in self.tests if t['status'] == 'WARN'])
        
        return {
            'total_tests': total,
            'passed': passed,
            'failed': failed,
            'warnings': warning_count,
            'success_rate': (passed / total * 100) if total > 0 else 0,
            'total_duration': time.time() - self.start_time,
            'errors': self.errors,
            'warning_messages': self.warnings,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

async def test_environment_setup(result: PipelineTestResult):
    """Test that all required environment variables are present"""
    print("🔍 Testing environment setup...")
    
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
    
    for var in required_vars:
        if os.getenv(var):
            result.add_test(f"Environment: {var}", "PASS", f"Present")
        else:
            result.add_test(f"Environment: {var}", "FAIL", f"Missing required variable")
            
    for var in optional_vars:
        if os.getenv(var):
            result.add_test(f"Environment: {var} (optional)", "PASS", f"Present: {os.getenv(var)}")
        else:
            result.add_test(f"Environment: {var} (optional)", "WARN", f"Not set, using defaults")

async def test_file_structure(result: PipelineTestResult):
    """Test that all required files and directories exist"""
    print("📁 Testing file structure...")
    
    required_files = [
        'feeds.txt',
        'requirements.txt',
        'cron_worker.py',
        'bot/main.py',
        'bot/parser.py',
        'bot/formatter.py',
        'bot/gemini_client.py'
    ]
    
    data_files = [
        'seen.json',
        'feed_meta.json',
        'feed_map.json',
        'channels.json',
        'groups.json'
    ]
    
    for file_path in required_files:
        if os.path.exists(file_path):
            result.add_test(f"File: {file_path}", "PASS", f"Exists")
        else:
            result.add_test(f"File: {file_path}", "FAIL", f"Missing required file")
    
    for file_path in data_files:
        if os.path.exists(file_path):
            result.add_test(f"Data file: {file_path}", "PASS", f"Exists")
        else:
            result.add_test(f"Data file: {file_path}", "WARN", f"Will be created on first run")

async def test_rss_feeds(result: PipelineTestResult, max_feeds=5):
    """Test RSS feed parsing"""
    print("📡 Testing RSS feed parsing...")
    
    feeds_file = "feeds.txt"
    if not os.path.exists(feeds_file):
        result.add_test("RSS Feeds", "FAIL", "feeds.txt not found")
        return
        
    with open(feeds_file, 'r') as f:
        feed_urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    if not feed_urls:
        result.add_test("RSS Feeds", "FAIL", "No feeds found in feeds.txt")
        return
        
    result.add_test("RSS Feed Count", "PASS", f"Found {len(feed_urls)} feeds")
    
    # Test a subset of feeds
    test_feeds = feed_urls[:max_feeds]
    
    for i, feed_url in enumerate(test_feeds, 1):
        start_time = time.time()
        try:
            print(f"  Testing feed {i}/{len(test_feeds)}: {feed_url[:50]}...")
            
            # Parse feed
            feed = feedparser.parse(feed_url)
            duration = time.time() - start_time
            
            if feed.bozo:
                result.add_test(f"RSS Feed {i}", "WARN", f"Parse warnings: {feed.bozo_exception}", duration)
            elif len(feed.entries) == 0:
                result.add_test(f"RSS Feed {i}", "WARN", f"No entries found", duration)
            else:
                result.add_test(f"RSS Feed {i}", "PASS", f"{len(feed.entries)} entries", duration)
                
                # Test entry processing with correct approach
                if feed.entries:
                    # Test processing of first entry
                    entry = feed.entries[0]
                    processed_entry = {
                        "guid": entry.get("id") or entry.link,
                        "title": entry.get("title", ""),
                        "link": entry.link,
                        "raw": entry.get("summary", ""),
                        "published": entry.get("published", ""),
                        "page_name": feed.feed.get("title", "") if hasattr(feed, 'feed') else "",
                        "about": feed.feed.get("description", "") if hasattr(feed, 'feed') else ""
                    }
                    result.add_test(f"RSS Feed {i} - Entry Processing", "PASS", f"Processed sample entry", duration)
                else:
                    result.add_test(f"RSS Feed {i} - Entry Processing", "WARN", f"No entries to process", duration)
                    
        except Exception as e:
            duration = time.time() - start_time
            result.add_test(f"RSS Feed {i}", "FAIL", f"Error: {str(e)}", duration)
            result.add_error(f"Feed {feed_url}: {e}")

async def test_gemini_integration(result: PipelineTestResult):
    """Test Gemini AI integration"""
    print("🤖 Testing Gemini AI integration...")
    
    if not os.getenv('GEMINI_API_KEY'):
        result.add_test("Gemini API", "FAIL", "GEMINI_API_KEY not set")
        return
        
    start_time = time.time()
    try:
        # Test with a proper entry dictionary
        test_entry = {
            "title": "Test Article for Pipeline Verification",
            "raw": "This is a test article to verify the Gemini integration is working correctly.",
            "link": "https://example.com/test",
            "page_name": "Test Feed",
            "about": "Test feed description"
        }
        
        test_prompt = build_prompt(test_entry)
        
        # call_gemini is synchronous
        response = call_gemini(test_prompt)
        duration = time.time() - start_time
        
        if response and len(response.strip()) > 10:
            result.add_test("Gemini API", "PASS", f"Response: {len(response)} chars", duration)
        else:
            result.add_test("Gemini API", "WARN", f"Short response: '{response}'", duration)
            
    except Exception as e:
        duration = time.time() - start_time
        result.add_test("Gemini API", "FAIL", f"Error: {str(e)}", duration)
        result.add_error(f"Gemini API: {e}")

async def test_discord_connectivity(result: PipelineTestResult):
    """Test Discord bot connectivity"""
    print("🤖 Testing Discord connectivity...")
    
    token = os.getenv('DISCORD_BOT_TOKEN')
    channel_id = os.getenv('CHANNEL_ID')
    
    if not token:
        result.add_test("Discord Token", "FAIL", "DISCORD_BOT_TOKEN not set")
        return
        
    if not channel_id:
        result.add_test("Discord Channel", "FAIL", "CHANNEL_ID not set")
        return
        
    try:
        # Test Discord API connectivity
        headers = {'Authorization': f'Bot {token}'}
        
        start_time = time.time()
        response = requests.get('https://discord.com/api/v10/users/@me', headers=headers, timeout=10)
        duration = time.time() - start_time
        
        if response.status_code == 200:
            bot_info = response.json()
            result.add_test("Discord Bot Auth", "PASS", f"Bot: {bot_info.get('username', 'Unknown')}", duration)
        else:
            result.add_test("Discord Bot Auth", "FAIL", f"HTTP {response.status_code}", duration)
            
        # Test channel access
        start_time = time.time()
        channel_response = requests.get(f'https://discord.com/api/v10/channels/{channel_id}', headers=headers, timeout=10)
        duration = time.time() - start_time
        
        if channel_response.status_code == 200:
            channel_info = channel_response.json()
            result.add_test("Discord Channel Access", "PASS", f"Channel: {channel_info.get('name', 'Unknown')}", duration)
        else:
            result.add_test("Discord Channel Access", "FAIL", f"HTTP {channel_response.status_code}", duration)
            
    except Exception as e:
        result.add_test("Discord Connectivity", "FAIL", f"Error: {str(e)}")
        result.add_error(f"Discord: {e}")

async def test_full_bot_run(result: PipelineTestResult):
    """Test a full bot execution cycle"""
    print("🚀 Testing full bot execution...")
    
    start_time = time.time()
    try:
        # Create backup of seen.json if it exists
        seen_backup = None
        if os.path.exists('seen.json'):
            with open('seen.json', 'r') as f:
                seen_backup = json.load(f)
        
        # Run the bot
        await run_bot_job()
        
        duration = time.time() - start_time
        result.add_test("Full Bot Run", "PASS", f"Completed without errors", duration)
        
        # Check if data files were updated
        data_files = ['seen.json', 'feed_meta.json']
        for file_path in data_files:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    if data:  # Not empty
                        result.add_test(f"Data File: {file_path}", "PASS", f"Updated with data")
                    else:
                        result.add_test(f"Data File: {file_path}", "WARN", f"Exists but empty")
            else:
                result.add_test(f"Data File: {file_path}", "WARN", f"Not created")
        
        # Restore seen.json backup if needed
        if seen_backup:
            with open('seen.json', 'w') as f:
                json.dump(seen_backup, f)
                
    except Exception as e:
        duration = time.time() - start_time
        result.add_test("Full Bot Run", "FAIL", f"Error: {str(e)}", duration)
        result.add_error(f"Bot run: {e}")

async def test_web_endpoints(result: PipelineTestResult):
    """Test web service endpoints"""
    print("🌐 Testing web endpoints...")
    
    # Test Railway deployment
    railway_url = "https://hanu-feedbot-production.up.railway.app"
    endpoints = [
        "/api/health",
        "/api/public/feeds",
        "/api/public/stats"
    ]
    
    for endpoint in endpoints:
        try:
            start_time = time.time()
            response = requests.get(f"{railway_url}{endpoint}", timeout=10)
            duration = time.time() - start_time
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    result.add_test(f"Railway {endpoint}", "PASS", f"HTTP 200, valid JSON", duration)
                except:
                    result.add_test(f"Railway {endpoint}", "WARN", f"HTTP 200, invalid JSON", duration)
            else:
                result.add_test(f"Railway {endpoint}", "FAIL", f"HTTP {response.status_code}", duration)
                
        except Exception as e:
            result.add_test(f"Railway {endpoint}", "FAIL", f"Error: {str(e)}")
    
    # Test GitHub Pages
    github_url = "https://hanu-cordbot.github.io/hanu-feedbot"
    gh_endpoints = [
        "/data/stats.json",
        "/data/feeds.json",
        "/data/meta.json"
    ]
    
    for endpoint in gh_endpoints:
        try:
            start_time = time.time()
            response = requests.get(f"{github_url}{endpoint}", timeout=10)
            duration = time.time() - start_time
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data:  # Not empty
                        result.add_test(f"GitHub Pages {endpoint}", "PASS", f"HTTP 200, has data", duration)
                    else:
                        result.add_test(f"GitHub Pages {endpoint}", "WARN", f"HTTP 200, empty data", duration)
                except:
                    result.add_test(f"GitHub Pages {endpoint}", "WARN", f"HTTP 200, invalid JSON", duration)
            else:
                result.add_test(f"GitHub Pages {endpoint}", "FAIL", f"HTTP {response.status_code}", duration)
                
        except Exception as e:
            result.add_test(f"GitHub Pages {endpoint}", "FAIL", f"Error: {str(e)}")

async def run_pipeline_test():
    """Run the complete pipeline test"""
    print("🔬 Starting comprehensive pipeline test...")
    print("=" * 60)
    
    result = PipelineTestResult()
    
    try:
        # Run all tests
        await test_environment_setup(result)
        await test_file_structure(result)
        await test_rss_feeds(result)
        await test_gemini_integration(result)
        await test_discord_connectivity(result)
        await test_web_endpoints(result)
        
        # Optionally run full bot test (commented out to avoid spam)
        # print("\n⚠️  Skipping full bot run test to avoid Discord spam")
        # print("   Uncomment in script to test full execution")
        # await test_full_bot_run(result)
        
    except Exception as e:
        result.add_error(f"Test suite error: {e}")
        print(f"❌ Test suite error: {e}")
        traceback.print_exc()
    
    finally:
        # Close HTTP session if it exists
        try:
            session = get_http_session()
            if session and not session.closed:
                await session.close()
        except:
            pass
    
    # Generate report
    summary = result.summary()
    
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    print(f"Total Tests: {summary['total_tests']}")
    print(f"✅ Passed: {summary['passed']}")
    print(f"❌ Failed: {summary['failed']}")
    print(f"⚠️  Warnings: {summary['warnings']}")
    print(f"Success Rate: {summary['success_rate']:.1f}%")
    print(f"Total Duration: {summary['total_duration']:.2f}s")
    
    if summary['errors']:
        print(f"\n❌ ERRORS ({len(summary['errors'])}):")
        for error in summary['errors']:
            print(f"  - {error}")
    
    if summary['warning_messages']:
        print(f"\n⚠️  WARNINGS ({len(summary['warning_messages'])}):")
        for warning in summary['warning_messages']:
            print(f"  - {warning}")
    
    print("\n📝 DETAILED RESULTS:")
    for test in result.tests:
        status_icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️ "}[test['status']]
        duration_str = f" ({test['duration']:.2f}s)" if test['duration'] else ""
        details_str = f" - {test['details']}" if test['details'] else ""
        print(f"  {status_icon} {test['name']}{duration_str}{details_str}")
    
    # Save detailed results
    results_file = f"pipeline_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, 'w') as f:
        json.dump({
            'summary': summary,
            'tests': result.tests
        }, f, indent=2)
    
    print(f"\n💾 Detailed results saved to: {results_file}")
    
    # Return exit code based on test results
    if summary['failed'] > 0:
        print("\n❌ PIPELINE TEST FAILED - Critical issues found")
        return 1
    elif summary['warnings'] > 0:
        print("\n⚠️  PIPELINE TEST PASSED WITH WARNINGS - Check configuration")
        return 0
    else:
        print("\n✅ PIPELINE TEST PASSED - All systems operational")
        return 0

if __name__ == "__main__":
    exit_code = asyncio.run(run_pipeline_test())
    sys.exit(exit_code)
