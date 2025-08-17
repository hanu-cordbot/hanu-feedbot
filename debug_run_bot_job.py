#!/usr/bin/env python3
"""Modified bot job to add debug logging"""

import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

async def debug_run_bot_job():
    """Run the bot job with detailed debug logging"""
    
    # Import the actual bot module
    from bot.main import run_bot_job
    
    print("🚀 Starting debug bot job...")
    
    # Add some environment debug
    print(f"🔧 Environment check:")
    print(f"  - MAX_AGE_HOURS: {os.getenv('MAX_AGE_HOURS')}")
    print(f"  - GLOBAL_FALLBACK_CHANNEL_ID: {os.getenv('GLOBAL_FALLBACK_CHANNEL_ID')}")
    print(f"  - CHANNEL_ID: {os.getenv('CHANNEL_ID')}")
    
    try:
        await run_bot_job()
        print("✅ Bot job completed")
    except Exception as e:
        print(f"❌ Bot job failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_run_bot_job())
