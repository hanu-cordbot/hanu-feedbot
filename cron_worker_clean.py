#!/usr/bin/env python3
import asyncio
import sys
import os
import tempfile
import time
import traceback
import signal
from pathlib import Path

# File lock to prevent overlapping runs
LOCK_FILE = Path("bot.lock")
# List to track temp files that need cleanup
TEMP_FILES_TO_CLEANUP = []
TEMP_DIRS_TO_CLEANUP = []

# Set up signal handlers for graceful shutdown
def signal_handler(signum, frame):
    print(f"Received signal {signum}, shutting down...")
    cleanup_temp_files()
    release_lock(None)
    sys.exit(1)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def acquire_lock():
    """Prevent overlapping runs with file lock"""
    # Detect stale lock: if exists and older than threshold, remove it
    STALE_THRESHOLD = 600  # 10 minutes (reduced from 1 hour)
    if LOCK_FILE.exists():
        age = time.time() - LOCK_FILE.stat().st_mtime
        if age > STALE_THRESHOLD:
            print(f" Stale lock detected (age {int(age)}s), removing.")
            LOCK_FILE.unlink(missing_ok=True)
        else:
            print(f" Another bot instance is already running (lock age: {int(age)}s)")
            sys.exit(1)
    try:
        lock_fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        print(f" Lock acquired: {LOCK_FILE}")
        return lock_fd
    except OSError:
        print(" Could not acquire lock; another instance may be running")
        sys.exit(1)


def release_lock(lock_fd):
    """Release file lock and cleanup"""
    try:
        if lock_fd is not None:
            os.close(lock_fd)
        LOCK_FILE.unlink(missing_ok=True)
        print(f" Lock released: {LOCK_FILE}")
    except Exception as e:
        print(f" Error releasing lock: {e}")


def cleanup_temp_files():
    """Clean up any remaining temporary files"""
    if not TEMP_FILES_TO_CLEANUP and not TEMP_DIRS_TO_CLEANUP:
        return
        
    print(f" Cleaning up {len(TEMP_FILES_TO_CLEANUP)} files and {len(TEMP_DIRS_TO_CLEANUP)} directories...")
    
    # Wait a bit to ensure Discord is done with the files
    time.sleep(2)
    
    # Try to clean up files
    for file_path in TEMP_FILES_TO_CLEANUP:
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
                print(f" Removed temp file: {file_path}")
        except Exception as e:
            print(f" Could not remove temp file {file_path}: {e}")
    
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
                print(f" Removed temp directory: {dir_path}")
        except Exception as e:
            print(f" Could not remove temp directory {dir_path}: {e}")


async def main():
    """Main entry point with clean shutdown and timeout"""
    start_time = time.time()
    lock_fd = acquire_lock()
    
    try:
        print(f" Starting standalone bot job at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
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
        
        # Set up a timeout for the entire job (8 minutes)
        async def timeout_handler():
            await asyncio.sleep(480)  # 8 minutes
            print(" Job timeout reached, forcing exit...")
            os._exit(1)
        
        # Create timeout task
        timeout_task = asyncio.create_task(timeout_handler())
        
        try:
            # Now run the bot
            from bot.main import run_bot_job
            print(" Importing bot modules...")
            
            # Run the bot job with timeout
            bot_task = asyncio.create_task(run_bot_job())
            
            # Wait for either the bot to finish or timeout
            done, pending = await asyncio.wait(
                [bot_task, timeout_task], 
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            # Check if bot completed successfully
            if bot_task in done:
                await bot_task  # This will raise any exception that occurred
                duration = time.time() - start_time
                print(f" Bot job completed successfully in {duration:.2f} seconds")
            else:
                print(" Bot job was cancelled due to timeout")
                return 1
            
        except Exception as e:
            duration = time.time() - start_time
            print(f" Bot job failed after {duration:.2f} seconds: {e}")
            traceback.print_exc()
            return 1
        
        # Add a delay to ensure uploads complete
        print(" Waiting for pending uploads to complete...")
        await asyncio.sleep(5)  # Reduced from 10 to 5 seconds
        
        duration = time.time() - start_time
        print(f" Job finished successfully in {duration:.2f} seconds")
        return 0
        
    except Exception as e:
        duration = time.time() - start_time
        print(f" Fatal error after {duration:.2f} seconds: {e}")
        traceback.print_exc()
        return 1
    finally:
        # Clean up temp files
        cleanup_temp_files()
        # Release lock
        release_lock(lock_fd)


if __name__ == "__main__":
    print("Starting cron worker...")
    try:
        exit_code = asyncio.run(main())
        print(f"Cron worker finished with exit code {exit_code}")
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("Cron worker interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"Cron worker crashed: {e}")
        traceback.print_exc()
        sys.exit(1)
