#!/usr/bin/env python3
import asyncio
import sys
import os
from pathlib import Path

# File lock to prevent overlapping runs
LOCK_FILE = Path("bot.lock")

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


async def main():
    """Main entry point with clean shutdown"""
    lock_fd = acquire_lock()
    try:
        from bot.main import run_bot_job
        print("🤖 Starting standalone bot job...")
        await run_bot_job()
        print("✅ Bot job completed successfully")
    except Exception as e:
        print(f"❌ Bot job failed: {e}")
    finally:
        release_lock(lock_fd)


if __name__ == "__main__":
    asyncio.run(main())
