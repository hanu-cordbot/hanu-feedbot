#!/usr/bin/env python3
import asyncio
import sys
import os
import tempfile
import time
import traceback
from pathlib import Path

# File lock to prevent overlapping runs
LOCK_FILE = Path("bot.lock")
# List to track temp files that need cleanup
TEMP_FILES_TO_CLEANUP = []
TEMP_DIRS_TO_CLEANUP = []

def acquire_lock():
    """Prevent overlapping runs with file lock"""
    # Detect stale lock: if exists and older than threshold, remove it
    import time
    STALE_THRESHOLD = 3600  # seconds
    if LOCK_FILE.exists():
        age = time.time() - LOCK_FILE.stat().st_mtime
        if age > STALE_THRESHOLD:
            print(f"⚠️ Stale lock detected (age {int(age)}s), removing.")
            LOCK_FILE.unlink(missing_ok=True)
        else:
            print("❌ Another bot instance is already running")
            sys.exit(1)
    try:
        lock_fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        return lock_fd
    except OSError:
        print("❌ Could not acquire lock; another instance may be running")
        sys.exit(1)


def release_lock(lock_fd):
    """Release file lock and cleanup"""
    try:
        os.close(lock_fd)
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def cleanup_temp_files():
    """Clean up any remaining temporary files"""
    print(f"🧹 Cleaning up {len(TEMP_FILES_TO_CLEANUP)} temporary files...")
    
    # Wait a bit to ensure Discord is done with the files
    time.sleep(3)
    
    # Try to clean up files
    for file_path in TEMP_FILES_TO_CLEANUP:
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
                print(f"✅ Removed temp file: {file_path}")
        except Exception as e:
            print(f"⚠️ Could not remove temp file {file_path}: {e}")
    
    # Try to clean up directories
    for dir_path in TEMP_DIRS_TO_CLEANUP:
        try:
            if os.path.exists(dir_path):
                # Try to clean contents first
                for root, dirs, files in os.walk(dir_path, topdown=False):
                    for file in files:
                        try:
                            os.unlink(os.path.join(root, file))
                        except:
                            pass
                    for dir in dirs:
                        try:
                            os.rmdir(os.path.join(root, dir))
                        except:
                            pass
                # Then try to remove the directory itself
                os.rmdir(dir_path)
                print(f"✅ Removed temp directory: {dir_path}")
        except Exception as e:
            print(f"⚠️ Could not remove temp directory {dir_path}: {e}")


async def main():
    """Main entry point with clean shutdown"""
    lock_fd = acquire_lock()
    try:
        # Patch the tempfile.TemporaryDirectory class to avoid auto-cleanup
        original_exit = tempfile.TemporaryDirectory.__exit__
        
        def patched_exit(self, exc, value, tb):
            # Skip cleanup on Windows - we'll do it manually
            if os.name == 'nt':
                TEMP_DIRS_TO_CLEANUP.append(self.name)
                return None
            return original_exit(self, exc, value, tb)
            
        # Apply the patch
        tempfile.TemporaryDirectory.__exit__ = patched_exit
        
        # Now run the bot
        from bot.main import run_bot_job
        print("🤖 Starting standalone bot job...")
        await run_bot_job()
        print("✅ Bot job completed successfully")
        
        # Add a delay to ensure uploads complete
        print("⏳ Waiting for pending uploads to complete...")
        await asyncio.sleep(10)
        
        # Exit cleanly on success
        return 0
    except Exception as e:
        print(f"❌ Bot job failed: {e}")
        traceback.print_exc()
        return 1
    finally:
        # Clean up temp files
        cleanup_temp_files()
        # Release lock
        release_lock(lock_fd)


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    print(f"🏁 Bot job finished with exit code {exit_code}")
    sys.exit(exit_code)