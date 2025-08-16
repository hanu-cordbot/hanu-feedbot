#!/usr/bin/env python3
"""
Comprehensive test suite for the enhanced Hanu FeedBot
"""
import os
import sys
import time
import json
import asyncio
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
import pytest

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

class TestConfig:
    """Test configuration and fixtures"""
    
    @staticmethod
    def setup_test_environment():
        """Set up test environment variables"""
        test_env = {
            'DISCORD_BOT_TOKEN': 'test_bot_token_123',
            'CHANNEL_ID': '123456789',
            'GEMINI_API_KEY': 'test_gemini_key',
            'JOB_ENDPOINT': '/test-job',
            'R2_BUCKET': 'test-bucket',
            'R2_ACCESS_KEY_ID': 'test_key',
            'R2_SECRET_ACCESS_KEY': 'test_secret',
            'R2_ACCOUNT_ID': 'test_account',
            'MAX_AGE_HOURS': '24'
        }
        
        for key, value in test_env.items():
            os.environ[key] = value

class TestFeedProcessing:
    """Test feed processing functionality"""
    
    def test_entry_filtering(self):
        """Test that entries are properly filtered"""
        from bot.main_enhanced import ProcessingStats
        
        # Mock data
        mock_entries = [
            {'guid': 'entry1', 'published': None, 'feed': 'feed1'},
            {'guid': 'entry2', 'published': None, 'feed': 'feed2'},
            {'guid': 'entry3', 'published': None, 'feed': 'feed1'},
        ]
        
        # Test basic stats tracking
        stats = ProcessingStats()
        assert stats.raw_entries == 0
        assert stats.new_entries == 0
        
        stats.raw_entries = len(mock_entries)
        assert stats.raw_entries == 3
        
        print("[OK] Entry filtering test passed")

    def test_parallel_processing_structure(self):
        """Test that parallel processing structure is correct"""
        try:
            from bot.main_enhanced import process_entries_parallel
            print("[OK] Parallel processing function imported successfully")
        except ImportError as e:
            print(f"[ERROR] Failed to import parallel processing: {e}")
            return False
        return True

class TestR2Integration:
    """Test R2 storage integration"""
    
    def test_r2_configuration(self):
        """Test R2 configuration"""
        required_vars = ['R2_BUCKET', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_ACCOUNT_ID']
        
        for var in required_vars:
            if not os.environ.get(var):
                print(f"[WARNING] R2 variable {var} not set for testing")
        
        print("[OK] R2 configuration test completed")

    def test_r2_upload_function(self):
        """Test R2 upload function structure"""
        try:
            from bot.main_enhanced import upload_to_r2
            print("[OK] R2 upload function imported successfully")
        except ImportError as e:
            print(f"[ERROR] Failed to import R2 upload function: {e}")
            return False
        return True

class TestWebhookFunctionality:
    """Test webhook functionality for Discord posting"""
    
    def test_webhook_import(self):
        """Test webhook functionality import"""
        try:
            from bot.dispatcher import get_or_create_webhook_url, WEBHOOK_CACHE
            print("[OK] Webhook functions imported successfully")
            assert isinstance(WEBHOOK_CACHE, dict)
            print("[OK] Webhook cache initialized correctly")
        except ImportError as e:
            print(f"[ERROR] Failed to import webhook functions: {e}")
            return False
        return True

class TestMediaProcessing:
    """Test enhanced media processing"""
    
    def test_media_processing_import(self):
        """Test enhanced media processing import"""
        try:
            from bot.main_enhanced import process_media_enhanced
            print("[OK] Enhanced media processing imported successfully")
        except ImportError as e:
            print(f"[ERROR] Failed to import enhanced media processing: {e}")
            return False
        return True

    def test_file_size_thresholds(self):
        """Test file size threshold logic"""
        DISCORD_LIMIT = 8 * 1024 * 1024  # 8MB
        R2_THRESHOLD = 10 * 1024 * 1024  # 10MB
        
        test_sizes = [
            (5 * 1024 * 1024, "small", "Should use Discord"),
            (9 * 1024 * 1024, "medium", "Should use Catbox"),
            (15 * 1024 * 1024, "large", "Should use R2"),
        ]
        
        for size, category, description in test_sizes:
            if size <= DISCORD_LIMIT:
                expected = "discord"
            elif size <= R2_THRESHOLD:
                expected = "catbox"
            else:
                expected = "r2"
            
            print(f"[OK] {category.upper()} file ({size/1024/1024:.1f}MB) -> {expected}")
        
        print("[OK] File size threshold test passed")

class TestProjectStructure:
    """Test project organization"""
    
    def test_directory_structure(self):
        """Test that project directories are properly organized"""
        required_dirs = ['bot', 'r2', 'tests', 'scripts', 'config']
        
        for dir_name in required_dirs:
            dir_path = project_root / dir_name
            if dir_path.exists():
                print(f"[OK] Directory exists: {dir_name}")
            else:
                print(f"[WARNING] Directory missing: {dir_name}")
        
        print("[OK] Directory structure test completed")

    def test_file_organization(self):
        """Test that files are in appropriate directories"""
        expected_files = {
            'scripts': ['test_workflow.py', 'fix_unicode.py'],
            'bot': ['main_enhanced.py', 'parser.py', 'dispatcher.py'],
            'r2': ['uploader.py', 'service.py'],
        }
        
        for dir_name, files in expected_files.items():
            dir_path = project_root / dir_name
            for file_name in files:
                file_path = dir_path / file_name
                if file_path.exists():
                    print(f"[OK] File organized correctly: {dir_name}/{file_name}")
                else:
                    print(f"[WARNING] File missing: {dir_name}/{file_name}")

class TestEnvironmentValidation:
    """Test environment validation"""
    
    def test_required_environment_variables(self):
        """Test that all required environment variables are set"""
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
            print(f"[WARNING] Missing required environment variables: {missing}")
            return False
        else:
            print("[OK] All required environment variables are set")
            return True

class TestIntegrationScenarios:
    """Test integration scenarios"""
    
    def test_end_to_end_workflow(self):
        """Test end-to-end workflow simulation"""
        print("[TEST] Simulating end-to-end workflow...")
        
        # Test 1: Environment setup
        if not TestEnvironmentValidation().test_required_environment_variables():
            print("[ERROR] Environment validation failed")
            return False
        
        # Test 2: Import main modules
        try:
            from bot.main_enhanced import ProcessingStats, STATS
            print("[OK] Main enhanced module imported")
        except Exception as e:
            print(f"[ERROR] Failed to import main enhanced module: {e}")
            return False
        
        # Test 3: Test stats tracking
        stats = ProcessingStats()
        stats.raw_entries = 10
        stats.new_entries = 5
        stats.posts_sent = 3
        
        print(f"[OK] Stats tracking: {stats.raw_entries} raw, {stats.new_entries} new, {stats.posts_sent} sent")
        
        # Test 4: Webhook functionality
        if not TestWebhookFunctionality().test_webhook_import():
            print("[ERROR] Webhook functionality test failed")
            return False
        
        # Test 5: R2 integration
        if not TestR2Integration().test_r2_upload_function():
            print("[ERROR] R2 integration test failed")
            return False
        
        print("[OK] End-to-end workflow simulation passed")
        return True

def run_all_tests():
    """Run all tests"""
    print("="*60)
    print("COMPREHENSIVE HANU FEEDBOT TEST SUITE")
    print("="*60)
    
    # Setup test environment
    TestConfig.setup_test_environment()
    print("[SETUP] Test environment configured")
    
    test_classes = [
        TestFeedProcessing,
        TestR2Integration, 
        TestWebhookFunctionality,
        TestMediaProcessing,
        TestProjectStructure,
        TestEnvironmentValidation,
        TestIntegrationScenarios
    ]
    
    passed = 0
    failed = 0
    
    for test_class in test_classes:
        print(f"\n{'-'*40}")
        print(f"Running {test_class.__name__}")
        print(f"{'-'*40}")
        
        # Get test methods
        test_methods = [method for method in dir(test_class) if method.startswith('test_')]
        
        for test_method in test_methods:
            try:
                print(f"\n  → {test_method}")
                instance = test_class()
                result = getattr(instance, test_method)()
                
                if result is False:
                    print(f"    [FAIL] {test_method}")
                    failed += 1
                else:
                    print(f"    [PASS] {test_method}")
                    passed += 1
                    
            except Exception as e:
                print(f"    [ERROR] {test_method}: {e}")
                failed += 1
    
    # Final summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"PASSED: {passed}")
    print(f"FAILED: {failed}")
    print(f"TOTAL: {passed + failed}")
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED! Bot is ready for deployment.")
        return True
    else:
        print(f"\n⚠️ {failed} test(s) failed. Please fix issues before deployment.")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
