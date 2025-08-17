#!/usr/bin/env python3
"""Simple Discord posting test"""

import os
import asyncio
import discord
from dotenv import load_dotenv

load_dotenv()

async def test_discord_connection():
    """Test basic Discord connectivity and posting"""
    
    bot_token = os.getenv('DISCORD_BOT_TOKEN')
    channel_id_str = os.getenv('CHANNEL_ID')
    
    if not bot_token:
        print("❌ No Discord bot token found!")
        return
        
    if not channel_id_str:
        print("❌ No channel ID found!")
        return
    
    channel_id = int(channel_id_str)
    
    print(f"🔧 Testing Discord connection...")
    print(f"  - Channel ID: {channel_id}")
    
    # Create Discord client
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    
    @client.event
    async def on_ready():
        print(f"✅ Logged in as {client.user}")
        
        try:
            # Get the channel
            channel = client.get_channel(channel_id)
            if not channel:
                print(f"❌ Could not find channel with ID {channel_id}")
                await client.close()
                return
            
            channel_name = getattr(channel, 'name', f'Channel-{channel_id}')
            print(f"✅ Found channel: #{channel_name}")
            
            # Test sending a simple message
            try:
                if hasattr(channel, 'send'):
                    message = await channel.send("🤖 Test message from HANU Feed Bot - Local testing!")
                    print(f"✅ Successfully sent message! Message ID: {message.id}")
                    print(f"📝 Message content: {message.content}")
                    
                    # Delete the test message after 5 seconds
                    await asyncio.sleep(5)
                    await message.delete()
                    print(f"🗑️ Test message deleted")
                else:
                    print(f"❌ Channel type {type(channel)} doesn't support sending messages")
                
            except discord.errors.Forbidden:
                print(f"❌ Bot doesn't have permission to send messages in #{channel_name}")
            except Exception as e:
                print(f"❌ Error sending message: {e}")
                
        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            await client.close()
    
    try:
        await client.start(bot_token)
    except Exception as e:
        print(f"❌ Failed to connect to Discord: {e}")

if __name__ == "__main__":
    asyncio.run(test_discord_connection())
