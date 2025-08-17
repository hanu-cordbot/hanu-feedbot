#!/usr/bin/env python3
"""
Test mode runner that ignores age limits and forces processing of recent entries
"""
import asyncio
import sys
import os
import json
import tempfile
import time
import traceback
from pathlib import Path

# File lock to prevent overlapping runs
LOCK_FILE = Path("bot.lock")
TEMP_FILES_TO_CLEANUP = []
TEMP_DIRS_TO_CLEANUP = []

def acquire_lock():
    """Prevent overlapping runs with file lock"""
    import time
    STALE_THRESHOLD = 3600  # seconds
    if LOCK_FILE.exists():
        age = time.time() - LOCK_FILE.stat().st_mtime
        if age > STALE_THRESHOLD:
            print(f"⚠️ Stale lock detected (age {int(age)}s), removing.")
            LOCK_FILE.unlink(missing_ok=True)
        else:
            force_test = os.getenv('FORCE_TEST_RUN', 'false').lower() == 'true'
            if force_test:
                print("🔓 Force test run - removing existing lock")
                LOCK_FILE.unlink(missing_ok=True)
            else:
                print("❌ Another bot instance is already running")
                sys.exit(1)
    try:
        lock_fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        return lock_fd
    except OSError:
        print("❌ Failed to acquire lock")
        sys.exit(1)

def release_lock(lock_fd):
    """Release the file lock"""
    try:
        os.close(lock_fd)
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass

def setup_test_mode():
    """Configure test mode to process recent entries regardless of seen status"""
    test_entries = int(os.getenv('TEST_ENTRIES_COUNT', '3'))
    
    print(f"🧪 Setting up test mode for {test_entries} entries")
    
    # Load current seen.json
    try:
        with open('seen.json', 'r') as f:
            seen = json.load(f)
        print(f"📊 Current seen entries: {len(seen)}")
    except:
        seen = []
        print("📊 No existing seen entries")
    
    # For test mode, we'll temporarily clear most seen entries
    # Keep only the last few to avoid too much spam
    if len(seen) > 20:
        test_seen = seen[-5:]  # Keep last 5 only
        print(f"🧪 Reduced seen entries from {len(seen)} to {len(test_seen)} for testing")
    else:
        test_seen = []
        print("🧪 Cleared all seen entries for testing")
    
    # Save reduced seen list
    with open('seen.json', 'w') as f:
        json.dump(test_seen, f, indent=2)
    
    # Set environment variables for aggressive testing
    os.environ['MAX_AGE_HOURS'] = '720000'  # Very large number to catch everything
    os.environ['TEST_MODE'] = 'true'
    os.environ['FORCE_IGNORE_AGE'] = 'true'  # Custom flag for test mode
    
    return len(seen), len(test_seen)

async def main():
    print("Initializing test mode configuration...")
    
    # Set up test environment
    original_seen_count, test_seen_count = setup_test_mode()
    
    # Acquire lock
    lock_fd = acquire_lock()
    
    try:
        # Patch temporary file handling
        original_cleanup = tempfile.TemporaryDirectory.__exit__
        def patched_exit(self, exc, value, tb):
            if hasattr(self, 'name') and os.path.exists(self.name):
                TEMP_DIRS_TO_CLEANUP.append(self.name)
            return original_cleanup(self, exc, value, tb)
        tempfile.TemporaryDirectory.__exit__ = patched_exit
        
        # Now run the bot
        from bot.main import run_bot_job
        print("🤖 Starting test bot job...")
        await run_bot_job()
        
        # Check results
        try:
            with open('seen.json', 'r') as f:
                final_seen = json.load(f)
            new_entries = len(final_seen) - test_seen_count
            print(f"✅ Test completed - processed {new_entries} new entries")
            
            if new_entries == 0:
                print("⚠️ No new entries processed. Possible reasons:")
                print("   - All RSS entries are older than 30 days")
                print("   - RSS feeds are empty or not accessible")
                print("   - Network connectivity issues")
                print("   - Feed parsing errors")
        except Exception as e:
            print(f"❌ Could not analyze results: {e}")
        
        print("⏳ Waiting for Discord uploads to complete...")
        await asyncio.sleep(10)
        
        return 0
    except Exception as e:
        print(f"❌ Test bot job failed: {e}")
        traceback.print_exc()
        return 1
    finally:
        # Clean up
        release_lock(lock_fd)

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    print(f"🏁 Test bot job finished with exit code {exit_code}")
    sys.exit(exit_code)
