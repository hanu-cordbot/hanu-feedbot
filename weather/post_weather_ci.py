#!/usr/bin/env python3
"""
CI/CD Weather Posting Script for HANU Feed Bot.
Runs via GitHub Actions to post weather at 5am Vietnam time.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

# Configuration from environment (secrets in GitHub Actions)
WEATHER_CHANNEL_ID = int(os.getenv("WEATHER_CHANNEL_ID", "0"))
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")

# Discord API base
DISCORD_API = "https://discord.com/api/v10"


async def post_weather():
    """Fetch weather and post to Discord via REST API."""
    from weather.weather_service import fetch_weather, generate_title
    from weather.weather_visual import WeatherVisualGenerator

    print(f"[{datetime.now()}] Starting weather post...")

    # Fetch weather data
    print("📡 Fetching weather data from Open-Meteo...")
    weather = await fetch_weather()
    print(f"   Current: {weather.current.temperature}°C, {weather.current.weather_description}")
    print(f"   Today: {weather.today.temp_min:.0f}°-{weather.today.temp_max:.0f}°C")

    # Generate images
    print("🎨 Generating weather images...")
    visual_gen = WeatherVisualGenerator()
    today_image = visual_gen.generate_today_image(weather)
    week_image = visual_gen.generate_week_image(weather)

    # Generate thread title
    title = generate_title(weather)
    date_str = weather.today.date.strftime("%d/%m/%Y") if weather.today else datetime.now().strftime("%d/%m/%Y")
    thread_title = f"☀️ Weather {date_str} — {title}"
    if len(thread_title) > 100:
        thread_title = thread_title[:97] + "..."

    print(f"📝 Thread title: {thread_title}")

    # Post to Discord via REST API
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "User-Agent": "HANU-WeatherBot-CI/1.0"
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Check channel exists and get type
        print(f"🔍 Checking channel {WEATHER_CHANNEL_ID}...")
        channel_resp = await client.get(
            f"{DISCORD_API}/channels/{WEATHER_CHANNEL_ID}",
            headers=headers
        )

        if channel_resp.status_code != 200:
            print(f"❌ Failed to access channel: {channel_resp.status_code}")
            print(f"   Response: {channel_resp.text[:200]}")
            return False

        channel_data = channel_resp.json()
        channel_type = channel_data.get("type", 0)
        channel_name = channel_data.get("name", "unknown")
        print(f"   Channel: #{channel_name} (type {channel_type})")

        thread_id = None
        today_image.seek(0)
        today_bytes = today_image.read()

        # Create thread based on channel type
        if channel_type == 15:  # Forum channel
            print("📌 Creating forum thread...")

            # Forum channels use POST /channels/{id}/threads with multipart
            # The message object must be in payload_json
            payload = {
                "name": thread_title,
                "auto_archive_duration": 1440,
                "message": {
                    "content": f"## 🌤️ Today's Weather — {weather.location}"
                }
            }

            thread_resp = await client.post(
                f"{DISCORD_API}/channels/{WEATHER_CHANNEL_ID}/threads",
                headers=headers,
                data={"payload_json": json.dumps(payload)},
                files={"files[0]": ("weather_today.png", today_bytes, "image/png")}
            )

            if thread_resp.status_code in (200, 201):
                thread_data = thread_resp.json()
                thread_id = thread_data.get("id")
                print(f"   ✅ Forum thread created: {thread_id}")
            else:
                print(f"   ❌ Forum thread failed: {thread_resp.status_code}")
                print(f"   Response: {thread_resp.text[:500]}")
                return False

        else:  # Text channel (type 0)
            print("📌 Creating thread in text channel...")
            thread_resp = await client.post(
                f"{DISCORD_API}/channels/{WEATHER_CHANNEL_ID}/threads",
                headers={**headers, "Content-Type": "application/json"},
                json={
                    "name": thread_title,
                    "type": 11,  # PUBLIC_THREAD
                    "auto_archive_duration": 1440
                }
            )

            if thread_resp.status_code in (200, 201):
                thread_data = thread_resp.json()
                thread_id = thread_data.get("id")
                print(f"   ✅ Thread created: {thread_id}")

                # Post today's image in thread
                print("📤 Posting today's weather...")
                msg_resp = await client.post(
                    f"{DISCORD_API}/channels/{thread_id}/messages",
                    headers=headers,
                    data={"payload_json": json.dumps({"content": f"## 🌤️ Today's Weather — {weather.location}"})},
                    files={"files[0]": ("weather_today.png", today_bytes, "image/png")}
                )

                if msg_resp.status_code not in (200, 201):
                    print(f"   ⚠️ Today message issue: {msg_resp.status_code}")
            else:
                print(f"   ❌ Thread creation failed: {thread_resp.status_code}")
                print(f"   Response: {thread_resp.text[:300]}")
                return False

        if not thread_id:
            print("❌ No thread ID obtained")
            return False

        # Post weekly forecast
        print("📤 Posting 7-day forecast...")
        week_image.seek(0)
        week_bytes = week_image.read()

        week_resp = await client.post(
            f"{DISCORD_API}/channels/{thread_id}/messages",
            headers=headers,
            data={"payload_json": json.dumps({"content": "## 📅 7-Day Forecast"})},
            files={"files[0]": ("weather_week.png", week_bytes, "image/png")}
        )

        if week_resp.status_code in (200, 201):
            print("   ✅ 7-day forecast posted!")
        else:
            print(f"   ⚠️ Week forecast issue: {week_resp.status_code} - {week_resp.text[:200]}")

        # Post footer message
        print("📤 Posting footer...")
        footer = create_footer(weather)
        footer_resp = await client.post(
            f"{DISCORD_API}/channels/{thread_id}/messages",
            headers={**headers, "Content-Type": "application/json"},
            json={"content": footer}
        )

        if footer_resp.status_code in (200, 201):
            print("   ✅ Footer posted!")
        else:
            print(f"   ⚠️ Footer issue: {footer_resp.status_code}")

    print()
    print("=" * 50)
    print(f"✅ Weather posted successfully!")
    print(f"   Thread: {thread_title}")
    print("=" * 50)
    return True


def create_footer(weather) -> str:
    """Create footer message."""
    timestamp = weather.fetched_at.strftime("%H:%M %d/%m/%Y")

    # Calculate day length
    day_length_str = ""
    if weather.today:
        try:
            sunrise_parts = weather.today.sunrise.split(":")
            sunset_parts = weather.today.sunset.split(":")
            sunrise_mins = int(sunrise_parts[0]) * 60 + int(sunrise_parts[1])
            sunset_mins = int(sunset_parts[0]) * 60 + int(sunset_parts[1])
            day_length_mins = sunset_mins - sunrise_mins
            day_hours = day_length_mins // 60
            day_mins = day_length_mins % 60
            day_length_str = f"{day_hours}h {day_mins}m of daylight"
        except Exception:
            pass

    # Build alerts summary
    alerts_text = ""
    if weather.today:
        alerts = weather.today.is_unusual()
        if alerts:
            alerts_text = "\n-# " + " • ".join(alerts[:3])

    lines = [
        f"-# ☀️ {day_length_str}" if day_length_str else "",
        alerts_text,
        f"-# 📍 {weather.location} • Updated {timestamp}",
        f"-# Weather data from [Open-Meteo](https://open-meteo.com/)",
        f"-# posted by HANU Feed Bot (CI/CD)",
    ]

    return "\n".join(line for line in lines if line)


def main():
    """Main entry point."""
    print("=" * 50)
    print("HANU Feed Bot - Weather CI/CD Post")
    print("=" * 50)
    print()

    # Validate config
    if not DISCORD_BOT_TOKEN:
        print("❌ ERROR: DISCORD_BOT_TOKEN secret not set")
        sys.exit(1)

    if not WEATHER_CHANNEL_ID or WEATHER_CHANNEL_ID == 0:
        print("❌ ERROR: WEATHER_CHANNEL_ID secret not set")
        sys.exit(1)

    print(f"✅ Bot token configured (length: {len(DISCORD_BOT_TOKEN)})")
    print(f"✅ Channel ID configured: {WEATHER_CHANNEL_ID}")
    print()

    try:
        success = asyncio.run(post_weather())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
