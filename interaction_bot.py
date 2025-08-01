import os
import json
import asyncio
import pendulum
import discord
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
TARGET_CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
PROCESSED_FILE = "processed_interactions.json"

# Validate configuration
if not BOT_TOKEN or not TARGET_CHANNEL_ID or not WEBHOOK_URL:
    raise RuntimeError("DISCORD_BOT_TOKEN, CHANNEL_ID, and DISCORD_WEBHOOK_URL must be set.")

try:
    WEBHOOK_ID = int(WEBHOOK_URL.split('/')[-2])
except (ValueError, IndexError):
    raise RuntimeError("Could not parse a valid ID from the DISCORD_WEBHOOK_URL.")

FACEBOOK_REACTIONS = ["👍", "❤️", "😆", "😲", "😢", "😡"]

# --- State Management ---
def load_processed_ids():
    """Loads the set of message IDs that have already been processed."""
    try:
        with open(PROCESSED_FILE, 'r') as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_processed_ids(ids):
    """Saves the set of processed message IDs."""
    # To prevent the file from growing indefinitely, we'll only store the last 200 IDs.
    with open(PROCESSED_FILE, 'w') as f:
        json.dump(list(ids)[-200:], f)

# --- Main On-Demand Logic ---
async def interact_with_recent_posts(client: discord.Client):
    """
    Scans recent messages, finds new ones from our webhook, and interacts with them.
    """
    channel = client.get_channel(TARGET_CHANNEL_ID)
    if not channel:
        print(f"🚨 Error: Could not find channel with ID {TARGET_CHANNEL_ID}.")
        return

    print(f"[{pendulum.now('UTC').to_iso8601_string()}] Scanning recent messages for interactions...")
    processed_ids = load_processed_ids()
    
    # Scan the last 15 messages in the channel
    async for message in channel.history(limit=15):
        # Filter for messages from our webhook that we haven't processed yet
        if message.webhook_id == WEBHOOK_ID and message.id not in processed_ids:
            print(f"  -> Found new webhook message {message.id}. Processing...")
            
            is_media_post = bool(message.attachments) or 'catbox.moe' in message.content
            is_tldr_post = '-# tl;dr:' in message.content

            if is_media_post:
                print("     👍 Adding reactions...")
                for reaction in FACEBOOK_REACTIONS:
                    await message.add_reaction(reaction)
                    await asyncio.sleep(0.5)

            if is_tldr_post:
                print("     💬 Creating metadata thread...")
                try:
                    await message.create_thread(name="Post Discussion & Info", auto_archive_duration=60)
                except Exception as e:
                    print(f"     🚨 Could not create thread: {e}")

            # Mark this message as processed
            processed_ids.add(message.id)
    
    save_processed_ids(processed_ids)
    print("Interaction scan complete.")


# --- Bot Entry Point ---
async def main():
    intents = discord.Intents.default()
    intents.messages = True
    intents.message_content = True # Needed to read webhook message content
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f'Logged in as {client.user} to perform interaction job.')
        await interact_with_recent_posts(client)
        print('Job finished. Logging out.')
        await client.close()

    await client.start(BOT_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
